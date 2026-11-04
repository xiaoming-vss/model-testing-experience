import { openEventStream } from '@/shared/api/request'
import { createLiveArtifactUrl, revokeLiveArtifactUrl } from '@/shared/utils/liveArtifactUrls'

type DebugKind = 'api-case' | 'ui-case'
type Event = { type: string; data: unknown }
type Artifact = { media: 'image/png' | 'application/zip'; chunks: Uint8Array<ArrayBuffer>[]; valid: boolean; padded: boolean }
const STREAM_SILENCE_TIMEOUT = 25_000

export class DebugStreamUnavailable extends Error {}

/** Establish the subscription before submitting, then buffer events until the caller is ready. */
export async function startDebugStream<T>(
  kind: DebugKind,
  caseId: string,
  body: object,
  onEvent: (event: Event) => void,
): Promise<{ initial: T; activate: () => void; abort: () => void }> {
  const controller = new AbortController()
  const initialTimer = setTimeout(() => controller.abort(), 30000)
  let response: Response
  try {
    response = await openEventStream(
      `/v1/test-debug-stream/${kind}/${encodeURIComponent(caseId)}`,
      controller.signal,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
    )
  } catch (error) {
    clearTimeout(initialTimer)
    throw error
  }
  if (!response.ok || !response.body) {
    clearTimeout(initialTimer)
    controller.abort()
    if (response.status === 503) throw new DebugStreamUnavailable('实时连接不可用')
    const payload = await response.json().catch(() => ({})) as { message?: string }
    throw new Error(payload.message || '无法建立实时调试连接，请稍后重试')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let active = false
  let ended = false
  let stopped = false
  let silenceExpired = false
  let silenceTimer: ReturnType<typeof setTimeout> | undefined
  let changeTimer: ReturnType<typeof setTimeout> | undefined
  let executionFinished = false
  const queued: Event[] = []
  let resolveInitial!: (value: T) => void
  let rejectInitial!: (reason: Error) => void
  const started = new Promise<T>((resolve, reject) => { resolveInitial = resolve; rejectInitial = reject })
  let hasInitial = false
  const artifacts = new Map<string, Artifact>()
  const objectUrls: string[] = []

  function expectHeartbeat() {
    if (silenceTimer) clearTimeout(silenceTimer)
    silenceTimer = setTimeout(() => {
      silenceExpired = true
      controller.abort()
    }, STREAM_SILENCE_TIMEOUT)
  }

  function collectArtifact(value: unknown) {
    if (!value || typeof value !== 'object') return
    const { path, media, part, data } = value as Record<string, unknown>
    if (typeof path !== 'string' || !/^\/v1\/files\/[a-zA-Z0-9-]+\/download$/.test(path)) return
    if (media !== 'image/png' && media !== 'application/zip') return
    const entry = artifacts.get(path) ?? { media, chunks: [], valid: true, padded: false }
    if (media !== entry.media || part !== entry.chunks.length || typeof data !== 'string'
      || data.length > 262144 || data.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(data)
      || entry.padded) {
      entry.valid = false
    } else {
      try {
        const binary = atob(data)
        const bytes = new Uint8Array(binary.length)
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
        entry.chunks.push(bytes)
        entry.padded = data.endsWith('=')
      } catch {
        entry.valid = false
      }
    }
    artifacts.set(path, entry)
  }

  function attachArtifacts(value: unknown): unknown {
    if (kind !== 'ui-case' || !value || typeof value !== 'object') return value
    const result = { ...value } as Record<string, unknown>
    const resolved = new Map<string, string>()
    let missing = false
    const resolve = (path: unknown) => {
      if (typeof path !== 'string' || !path.startsWith('/v1/files/')) return path
      const existing = resolved.get(path)
      if (existing) return existing
      const entry = artifacts.get(path)
      if (!entry?.valid || !entry.chunks.length) { missing = true; return '' }
      const url = createLiveArtifactUrl(entry.chunks, entry.media)
      objectUrls.push(url)
      resolved.set(path, url)
      return url
    }
    if ('tracePath' in result) result.tracePath = resolve(result.tracePath)
    if (Array.isArray(result.stepResults)) {
      result.stepResults = result.stepResults.map(step => step && typeof step === 'object'
        ? { ...step, screenshotPath: resolve(step.screenshotPath) } : step)
    }
    if (missing) result.errorMessage = `${result.errorMessage || ''} 部分临时产物接收失败`
    artifacts.clear()
    return result
  }

  function deliver(event: Event) {
    if (stopped) return
    if (active) onEvent(event)
    else queued.push(event)
  }
  void (async () => {
    try {
      expectHeartbeat()
      while (!ended && !stopped) {
        const { value, done } = await reader.read()
        if (done) break
        if (stopped) break
        expectHeartbeat()
        buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n')
        let separator = buffer.indexOf('\n\n')
        while (separator >= 0) {
          const frame = buffer.slice(0, separator)
          buffer = buffer.slice(separator + 2)
          const type = frame.split('\n').find(line => line.startsWith('event: '))?.slice(7)
          const data = frame.split('\n').find(line => line.startsWith('data: '))?.slice(6)
          if (type && data) {
            const parsed: unknown = JSON.parse(data)
            if (type === 'started' && !hasInitial) {
              hasInitial = true
              resolveInitial(parsed as T)
            } else if (type === 'artifact') {
              collectArtifact(parsed)
            } else if (type === 'changed') {
              if (!executionFinished && !changeTimer) changeTimer = setTimeout(() => {
                changeTimer = undefined
                deliver({ type: 'changed', data: null })
              }, 200)
            } else {
              if (type === 'execution_finished') {
                executionFinished = true
                if (changeTimer) clearTimeout(changeTimer)
                changeTimer = undefined
              }
              if (type === 'finished') {
                ended = true
                if (changeTimer) clearTimeout(changeTimer)
                changeTimer = undefined
              }
              deliver({ type, data: type === 'finished' ? attachArtifacts(parsed) : parsed })
            }
          }
          separator = buffer.indexOf('\n\n')
        }
      }
      if (!hasInitial) rejectInitial(new Error('调试连接已断开，未收到运行记录'))
      else if (!ended && (!controller.signal.aborted || silenceExpired)) {
        artifacts.clear()
        deliver({ type: 'disconnected', data: null })
      }
    } catch {
      artifacts.clear()
      objectUrls.splice(0).forEach(revokeLiveArtifactUrl)
      if (!hasInitial) rejectInitial(new Error('调试连接已断开，未收到运行记录'))
      else if (!controller.signal.aborted || silenceExpired) deliver({ type: 'disconnected', data: null })
    } finally {
      if (silenceTimer) clearTimeout(silenceTimer)
      if (changeTimer) clearTimeout(changeTimer)
      if (!ended && !controller.signal.aborted) controller.abort()
      reader.releaseLock()
    }
  })()
  let initial: T
  try {
    initial = await started
  } finally {
    clearTimeout(initialTimer)
  }
  const abort = () => {
    stopped = true
    active = false
    if (changeTimer) clearTimeout(changeTimer)
    if (silenceTimer) clearTimeout(silenceTimer)
    if (activationTimer) clearTimeout(activationTimer)
    artifacts.clear()
    queued.length = 0
    objectUrls.splice(0).forEach(revokeLiveArtifactUrl)
    controller.abort()
  }
  // A page can unmount while the initial response is in flight. In that case
  // its mutation callback never activates the handle, so release the stream.
  const activationTimer = setTimeout(() => { if (!active) abort() }, 30000)
  return {
    initial,
    activate: () => {
      if (stopped) return
      active = true
      if (activationTimer) clearTimeout(activationTimer)
      queued.splice(0).forEach(event => onEvent(event))
    },
    abort,
  }
}
