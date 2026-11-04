import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { openEventStream } from '@/shared/api/request'
import { useRunEvents } from './useRunEvents'

vi.mock('@/shared/api/request', () => ({ openEventStream: vi.fn() }))

afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers() })

it('refreshes on subscription and change, and disconnects when the run closes', async () => {
  let streamController!: ReadableStreamDefaultController<Uint8Array>
  const stream = new ReadableStream<Uint8Array>({ start(controller) { streamController = controller } })
  vi.mocked(openEventStream).mockResolvedValue(new Response(stream, { status: 200 }))
  const onChange = vi.fn()
  const { result, unmount } = renderHook(() => useRunEvents('ui-suite', 'run-1', true, onChange))
  await waitFor(() => expect(openEventStream).toHaveBeenCalledTimes(1))
  act(() => { streamController.enqueue(new TextEncoder().encode('event: ready\ndata: {}\n\n')) })
  await waitFor(() => expect(result.current).toBe(true))
  expect(onChange).toHaveBeenCalledTimes(1)
  act(() => { streamController.enqueue(new TextEncoder().encode('event: changed\ndata: {}\n\n')) })
  await waitFor(() => expect(onChange).toHaveBeenCalledTimes(2))
  const signal = vi.mocked(openEventStream).mock.calls[0][1]
  unmount()
  expect(signal.aborted).toBe(true)
  streamController.close()
})

it('recognizes an event when CRLF is split across network chunks', async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const stream = new ReadableStream<Uint8Array>({ start(value) { controller = value } })
  vi.mocked(openEventStream).mockResolvedValue(new Response(stream, { status: 200 }))
  const onChange = vi.fn()
  const { result, unmount } = renderHook(() => useRunEvents('ui-suite', 'run-1', true, onChange))
  const encoder = new TextEncoder()
  await waitFor(() => expect(openEventStream).toHaveBeenCalledTimes(1))
  for (const chunk of ['event: ready\r', '\ndata: {}\r', '\n\r', '\n']) {
    act(() => { controller.enqueue(encoder.encode(chunk)) })
    await Promise.resolve()
  }
  await waitFor(() => expect(result.current).toBe(true))
  expect(onChange).toHaveBeenCalledTimes(1)
  unmount()
  controller.close()
})

it('reconnects and refreshes after an apparently open stream stops sending heartbeats', async () => {
  vi.useFakeTimers()
  const signals: AbortSignal[] = []
  vi.mocked(openEventStream).mockImplementation(async (_url, signal) => {
    signals.push(signal)
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('event: ready\ndata: {}\n\n'))
        signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
      },
    })
    return new Response(stream, { status: 200 })
  })
  const onChange = vi.fn()
  const { result, unmount } = renderHook(() => useRunEvents('ui-suite', 'run-1', true, onChange))
  await act(async () => { await vi.advanceTimersByTimeAsync(0) })
  expect(result.current).toBe(true)
  expect(onChange).toHaveBeenCalledTimes(1)

  await act(async () => { await vi.advanceTimersByTimeAsync(25_000) })
  expect(signals[0].aborted).toBe(true)
  expect(result.current).toBe(false)
  await act(async () => { await vi.advanceTimersByTimeAsync(3_000) })
  expect(signals).toHaveLength(2)
  expect(result.current).toBe(true)
  expect(onChange).toHaveBeenCalledTimes(2)
  unmount()
  expect(signals[1].aborted).toBe(true)
})

it('keeps the stream open when heartbeats arrive', async () => {
  vi.useFakeTimers()
  let streamController!: ReadableStreamDefaultController<Uint8Array>
  let signal!: AbortSignal
  vi.mocked(openEventStream).mockImplementation(async (_url, currentSignal) => {
    signal = currentSignal
    const stream = new ReadableStream<Uint8Array>({ start(controller) { streamController = controller } })
    return new Response(stream, { status: 200 })
  })
  const { unmount } = renderHook(() => useRunEvents('ui-suite', 'run-1', true, vi.fn()))
  await act(async () => { await vi.advanceTimersByTimeAsync(0) })
  act(() => { streamController.enqueue(new TextEncoder().encode('event: ready\ndata: {}\n\n')) })
  await act(async () => { await vi.advanceTimersByTimeAsync(20_000) })
  act(() => { streamController.enqueue(new TextEncoder().encode(': heartbeat\n\n')) })
  await act(async () => { await vi.advanceTimersByTimeAsync(20_000) })
  expect(signal.aborted).toBe(false)
  expect(openEventStream).toHaveBeenCalledTimes(1)
  unmount()
  streamController.close()
})
