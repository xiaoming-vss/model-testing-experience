import { useEffect, useRef, useState } from 'react'
import { openEventStream } from '@/shared/api/request'

type RunKind = 'api-case' | 'api-collection' | 'ui-case' | 'ui-suite'
const STREAM_SILENCE_TIMEOUT = 25_000

/** Subscribe to changes; reconnecting re-reads the authoritative snapshot. */
export function useRunEvents(kind: RunKind, runId: string, enabled: boolean, onChange: () => void) {
  const [connectedKey, setConnectedKey] = useState('')
  const onChangeRef = useRef(onChange)
  useEffect(() => { onChangeRef.current = onChange }, [onChange])

  useEffect(() => {
    if (!enabled || !runId) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    let changeTimer: ReturnType<typeof setTimeout> | undefined
    let stopped = false
    let retryMs = 3000

    async function connect() {
      const connection = new AbortController()
      const abortConnection = () => connection.abort()
      controller.signal.addEventListener('abort', abortConnection, { once: true })
      let silenceTimer: ReturnType<typeof setTimeout> | undefined
      const expectHeartbeat = () => {
        if (silenceTimer) clearTimeout(silenceTimer)
        silenceTimer = setTimeout(abortConnection, STREAM_SILENCE_TIMEOUT)
      }
      try {
        expectHeartbeat()
        const response = await openEventStream(
          `/v1/test-run-events/${kind}/${encodeURIComponent(runId)}`, connection.signal,
        )
        if (!response.ok || !response.body) throw new Error('stream unavailable')
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        try {
          while (!stopped) {
            const { value, done } = await reader.read()
            if (done) break
            expectHeartbeat()
            buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n')
            let separator = buffer.indexOf('\n\n')
            while (separator >= 0) {
              const event = buffer.slice(0, separator)
              buffer = buffer.slice(separator + 2)
              if (event.includes('event: ready')) {
                retryMs = 3000
                setConnectedKey(`${kind}:${runId}`)
                onChangeRef.current()
              } else if (event.includes('event: changed') && !changeTimer) {
                changeTimer = setTimeout(() => {
                  changeTimer = undefined
                  onChangeRef.current()
                }, 200)
              }
              separator = buffer.indexOf('\n\n')
            }
          }
        } finally {
          reader.releaseLock()
        }
      } catch {
        // A low-frequency query remains active while reconnecting.
      } finally {
        if (silenceTimer) clearTimeout(silenceTimer)
        controller.signal.removeEventListener('abort', abortConnection)
        if (!stopped) {
          setConnectedKey('')
          timer = setTimeout(() => { void connect() }, retryMs)
          retryMs = Math.min(retryMs * 2, 30000)
        }
      }
    }

    void connect()
    return () => {
      stopped = true
      setConnectedKey('')
      controller.abort()
      if (timer) clearTimeout(timer)
      if (changeTimer) clearTimeout(changeTimer)
    }
  }, [enabled, kind, runId])

  return enabled && Boolean(runId) && connectedKey === `${kind}:${runId}`
}
