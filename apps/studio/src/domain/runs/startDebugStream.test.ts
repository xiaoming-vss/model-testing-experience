import { afterEach, expect, it, vi } from 'vitest'
import { openEventStream } from '@/shared/api/request'
import { startDebugStream } from './startDebugStream'

vi.mock('@/shared/api/request', () => ({ openEventStream: vi.fn() }))
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('buffers a fast final result until the caller has installed its initial state', async () => {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode('event: started\ndata: {"runId":"r","status":"pending"}\n\nevent: finished\ndata: {"runId":"r","status":"success"}\n\n'))
      controller.close()
    },
  })
  vi.mocked(openEventStream).mockResolvedValue(new Response(stream, { status: 200 }))
  const events = vi.fn()
  const handle = await startDebugStream<{ runId: string }>('api-case', 'case', {}, events)
  expect(handle.initial.runId).toBe('r')
  expect(events).not.toHaveBeenCalled()
  handle.activate()
  expect(events).toHaveBeenCalledWith({ type: 'finished', data: { runId: 'r', status: 'success' } })
})

it('reads final debug results when CRLF is split across chunks', async () => {
  const encoder = new TextEncoder()
  const chunks = [
    'event: started\r', '\ndata: {"runId":"r"}\r', '\n\r', '\n',
    'event: finished\r', '\ndata: {"status":"success"}\r', '\n\r', '\n',
  ]
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  vi.mocked(openEventStream).mockResolvedValue(new Response(stream, { status: 200 }))
  const events = vi.fn()
  const handle = await startDebugStream<{ runId: string }>('api-case', 'case', {}, events)
  handle.activate()
  await vi.waitFor(() => expect(events).toHaveBeenCalledWith({ type: 'finished', data: { status: 'success' } }))
})

it('drops pending progress after a debug stream disconnects', async () => {
  vi.useFakeTimers()
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const stream = new ReadableStream<Uint8Array>({
    start(value) {
      controller = value
      value.enqueue(new TextEncoder().encode('event: started\ndata: {"runId":"r"}\n\n'))
    },
  })
  vi.mocked(openEventStream).mockResolvedValue(new Response(stream, { status: 200 }))
  const events = vi.fn()
  const handle = await startDebugStream('api-case', 'case', {}, events)
  handle.activate()
  controller.enqueue(new TextEncoder().encode('event: changed\ndata: {}\n\n'))
  await vi.advanceTimersByTimeAsync(0)
  controller.error(new Error('disconnected'))
  await vi.advanceTimersByTimeAsync(200)
  expect(events).toHaveBeenCalledWith({ type: 'disconnected', data: null })
  expect(events).not.toHaveBeenCalledWith({ type: 'changed', data: null })
  handle.abort()
})

it('delivers the execution outcome before artifacts and suppresses stale progress', async () => {
  vi.useFakeTimers()
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const stream = new ReadableStream<Uint8Array>({
    start(value) {
      controller = value
      value.enqueue(new TextEncoder().encode('event: started\ndata: {"runId":"r"}\n\n'))
    },
  })
  vi.mocked(openEventStream).mockResolvedValue(new Response(stream, { status: 200 }))
  const events = vi.fn()
  const handle = await startDebugStream('ui-case', 'case', {}, events)
  handle.activate()
  controller.enqueue(new TextEncoder().encode(
    'event: changed\ndata: {}\n\nevent: execution_finished\ndata: {"status":"success"}\n\nevent: changed\ndata: {}\n\n',
  ))
  await vi.advanceTimersByTimeAsync(300)
  expect(events).toHaveBeenCalledWith({ type: 'execution_finished', data: { status: 'success' } })
  expect(events).not.toHaveBeenCalledWith({ type: 'changed', data: null })
  controller.enqueue(new TextEncoder().encode('event: finished\ndata: {"status":"success"}\n\n'))
  await vi.advanceTimersByTimeAsync(0)
  expect(events).toHaveBeenCalledWith({ type: 'finished', data: { status: 'success' } })
  handle.abort()
})

it('closes the response when an invalid event prevents further decoding', async () => {
  let signal!: AbortSignal
  vi.mocked(openEventStream).mockImplementation(async (_url, requestSignal) => {
    signal = requestSignal
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('event: started\ndata: {"runId":"r"}\n\nevent: changed\ndata: invalid-json\n\n'))
      },
    })
    return new Response(stream, { status: 200 })
  })
  const events = vi.fn()
  const handle = await startDebugStream('api-case', 'case', {}, events)
  handle.activate()
  await vi.waitFor(() => expect(events).toHaveBeenCalledWith({ type: 'disconnected', data: null }))
  expect(signal.aborted).toBe(true)
  handle.abort()
})

it('reassembles streamed UI artifacts before exposing the final result', async () => {
  const create = vi.fn<(blob: Blob) => string>(() => 'blob:live-shot')
  const revoke = vi.fn()
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = create
    static revokeObjectURL = revoke
  })
  const encoder = new TextEncoder()
  const path = '/v1/files/shot-1/download'
  const frames = [
    'event: started\ndata: {"runId":"r","status":"pending"}',
    `event: artifact\ndata: ${JSON.stringify({ path, media: 'image/png', part: 0, data: 'YWJj' })}`,
    `event: artifact\ndata: ${JSON.stringify({ path, media: 'image/png', part: 1, data: 'ZA==' })}`,
    `event: finished\ndata: ${JSON.stringify({ status: 'success', stepResults: [{ screenshotPath: path }] })}`,
  ]
  const stream = new ReadableStream<Uint8Array>({
    start(controller) { controller.enqueue(encoder.encode(frames.join('\n\n') + '\n\n')); controller.close() },
  })
  vi.mocked(openEventStream).mockResolvedValue(new Response(stream, { status: 200 }))
  const events = vi.fn()
  const handle = await startDebugStream('ui-case', 'case', {}, events)
  handle.activate()
  await vi.waitFor(() => expect(events).toHaveBeenCalled())
  expect(events).toHaveBeenCalledWith({ type: 'finished', data: {
    status: 'success', stepResults: [{ screenshotPath: 'blob:live-shot' }],
  } })
  expect(create.mock.calls[0][0]).toMatchObject({ type: 'image/png', size: 4 })
  handle.abort()
  expect(revoke).toHaveBeenCalledWith('blob:live-shot')
})

it('does not expose an incomplete or out-of-order UI artifact', async () => {
  const path = '/v1/files/shot-1/download'
  const frames = [
    'event: started\ndata: {"runId":"r","status":"pending"}',
    `event: artifact\ndata: ${JSON.stringify({ path, media: 'image/png', part: 1, data: 'YWJj' })}`,
    `event: finished\ndata: ${JSON.stringify({ status: 'success', stepResults: [{ screenshotPath: path }] })}`,
  ]
  const stream = new ReadableStream<Uint8Array>({
    start(controller) { controller.enqueue(new TextEncoder().encode(frames.join('\n\n') + '\n\n')); controller.close() },
  })
  vi.mocked(openEventStream).mockResolvedValue(new Response(stream, { status: 200 }))
  const events = vi.fn()
  const handle = await startDebugStream('ui-case', 'case', {}, events)
  handle.activate()
  await vi.waitFor(() => expect(events).toHaveBeenCalled())
  expect(events).toHaveBeenCalledWith({ type: 'finished', data: {
    status: 'success', stepResults: [{ screenshotPath: '' }], errorMessage: ' 部分临时产物接收失败',
  } })
})

it('releases buffered artifacts when the page never activates the stream', async () => {
  vi.useFakeTimers()
  const revoke = vi.fn()
  let resolveCreated!: () => void
  const created = new Promise<void>(resolve => { resolveCreated = resolve })
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => { resolveCreated(); return 'blob:orphan' })
    static revokeObjectURL = revoke
  })
  const path = '/v1/files/orphan/download'
  const frames = [
    'event: started\ndata: {"runId":"r","status":"pending"}',
    `event: artifact\ndata: ${JSON.stringify({ path, media: 'image/png', part: 0, data: 'YWJj' })}`,
    `event: finished\ndata: ${JSON.stringify({ status: 'success', stepResults: [{ screenshotPath: path }] })}`,
  ]
  const stream = new ReadableStream<Uint8Array>({
    start(controller) { controller.enqueue(new TextEncoder().encode(frames.join('\n\n') + '\n\n')); controller.close() },
  })
  vi.mocked(openEventStream).mockResolvedValue(new Response(stream, { status: 200 }))
  const events = vi.fn()
  await startDebugStream('ui-case', 'case', {}, events)
  await created
  await vi.advanceTimersByTimeAsync(30000)
  expect(events).not.toHaveBeenCalled()
  expect(revoke).toHaveBeenCalledWith('blob:orphan')
})

it('reports a silent broken debug stream without submitting another run', async () => {
  vi.useFakeTimers()
  vi.mocked(openEventStream).mockClear()
  vi.mocked(openEventStream).mockImplementation(async (_url, signal) => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('event: started\ndata: {"runId":"r"}\n\n'))
        signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
      },
    })
    return new Response(stream, { status: 200 })
  })
  const events = vi.fn()
  const handle = await startDebugStream('ui-case', 'case', {}, events)
  handle.activate()
  await vi.advanceTimersByTimeAsync(25_000)
  expect(events).toHaveBeenCalledWith({ type: 'disconnected', data: null })
  expect(openEventStream).toHaveBeenCalledTimes(1)
  handle.abort()
})

it('does not report a disconnection when the page closes the debug stream', async () => {
  vi.mocked(openEventStream).mockImplementation(async (_url, signal) => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('event: started\ndata: {"runId":"r"}\n\n'))
        signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
      },
    })
    return new Response(stream, { status: 200 })
  })
  const events = vi.fn()
  const handle = await startDebugStream('ui-case', 'case', {}, events)
  handle.activate()
  handle.abort()
  await Promise.resolve()
  expect(events).not.toHaveBeenCalled()
})
