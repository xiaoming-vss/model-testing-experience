import { QueryClient, QueryObserver } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { ApiError } from '@/shared/api/request'
import { refreshRunQuery } from './refreshRunQuery'

it('refreshes after the first in-flight snapshot and coalesces repeated events', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let resolveInitial!: (result: { status: string }) => void
  const initial = new Promise<{ status: string }>((resolve) => { resolveInitial = resolve })
  const queryFn = vi.fn()
    .mockReturnValueOnce(initial)
    .mockResolvedValue({ status: 'success' })
  const key = ['uiTestSuiteRunReport', 'run-1'] as const
  const observer = new QueryObserver(client, { queryKey: key, queryFn })
  const unsubscribe = observer.subscribe(() => {})
  expect(queryFn).toHaveBeenCalledTimes(1)

  const first = refreshRunQuery(client, key)
  const second = refreshRunQuery(client, key)
  expect(second).toBe(first)
  expect(queryFn).toHaveBeenCalledTimes(1)
  resolveInitial({ status: 'running' })
  await Promise.all([first, second])

  expect(queryFn).toHaveBeenCalledTimes(2)
  expect(observer.getCurrentResult().data).toEqual({ status: 'success' })
  unsubscribe()
  client.clear()
})

it('retries the snapshot after an initial query fails', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let rejectInitial!: (reason: Error) => void
  const initial = new Promise<never>((_resolve, reject) => { rejectInitial = reject })
  const queryFn = vi.fn().mockReturnValueOnce(initial).mockResolvedValue({ status: 'success' })
  const key = ['apiCollectionRun', 'run-1'] as const
  const observer = new QueryObserver(client, { queryKey: key, queryFn })
  const unsubscribe = observer.subscribe(() => {})

  const refresh = refreshRunQuery(client, key)
  rejectInitial(new Error('temporary failure'))
  await refresh
  expect(queryFn).toHaveBeenCalledTimes(2)
  expect(observer.getCurrentResult().data).toEqual({ status: 'success' })
  unsubscribe()
  client.clear()
})

it('does not cancel repeated in-flight report fetches when events keep arriving', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const key = ['apiCollectionRunReport', 'run-1'] as const
  client.setQueryData(key, { status: 'running', completed: 1 })
  let finish!: (result: { status: string; completed: number }) => void
  let firstSignal!: AbortSignal
  const request = new Promise<{ status: string; completed: number }>((resolve) => { finish = resolve })
  const queryFn = vi.fn(({ signal }: { signal: AbortSignal }) => {
    if (queryFn.mock.calls.length === 1) { firstSignal = signal; return request }
    return Promise.resolve({ status: 'running', completed: 3 })
  })
  const observer = new QueryObserver(client, { queryKey: key, queryFn })
  const unsubscribe = observer.subscribe(() => {})
  const events = Array.from({ length: 10 }, () => refreshRunQuery(client, key))
  expect(events.every((event) => event === events[0])).toBe(true)
  expect(queryFn).toHaveBeenCalledTimes(1)
  expect(firstSignal.aborted).toBe(false)
  finish({ status: 'running', completed: 2 })
  await Promise.all(events)
  expect(queryFn).toHaveBeenCalledTimes(2)
  expect(observer.getCurrentResult().data).toEqual({ status: 'running', completed: 3 })
  unsubscribe()
  client.clear()
})

it('fetches again when a change arrives during the coalesced refresh', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const key = ['apiCollectionRunReport', 'run-race'] as const
  let finishInitial!: (value: number) => void
  let finishRefresh!: (value: number) => void
  const initial = new Promise<number>(resolve => { finishInitial = resolve })
  const refreshing = new Promise<number>(resolve => { finishRefresh = resolve })
  const queryFn = vi.fn().mockReturnValueOnce(initial).mockReturnValueOnce(refreshing).mockResolvedValue(3)
  const observer = new QueryObserver(client, { queryKey: key, queryFn })
  const unsubscribe = observer.subscribe(() => {})
  try {
    const first = refreshRunQuery(client, key)
    finishInitial(1)
    await vi.waitFor(() => expect(queryFn).toHaveBeenCalledTimes(2))
    const later = refreshRunQuery(client, key)
    expect(later).toBe(first)
    finishRefresh(2)
    await first
    expect(queryFn).toHaveBeenCalledTimes(3)
    expect(observer.getCurrentResult().data).toBe(3)
  } finally {
    unsubscribe()
    client.clear()
  }
})

it('aborts a stuck initial request before fetching the latest snapshot', async () => {
  vi.useFakeTimers()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const signals: AbortSignal[] = []
  const queryFn = vi.fn(({ signal }: { signal: AbortSignal }) => {
    signals.push(signal)
    if (signals.length > 1) return Promise.resolve({ status: 'success' })
    return new Promise<{ status: string }>((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true })
    })
  })
  const key = ['uiTestSuiteRun', 'stuck-run'] as const
  const observer = new QueryObserver(client, { queryKey: key, queryFn })
  const unsubscribe = observer.subscribe(() => {})
  try {
    const first = refreshRunQuery(client, key)
    const repeated = refreshRunQuery(client, key)
    await vi.advanceTimersByTimeAsync(5_000)
    await Promise.all([first, repeated])
    expect(signals[0].aborted).toBe(true)
    expect(queryFn).toHaveBeenCalledTimes(2)
    expect(observer.getCurrentResult().data).toEqual({ status: 'success' })
  } finally {
    unsubscribe()
    client.clear()
    vi.useRealTimers()
  }
})

it('recovers when its own refresh stalls and another change arrives', async () => {
  vi.useFakeTimers()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const key = ['apiCollectionRunReport', 'stuck-refresh'] as const
  const signals: AbortSignal[] = []
  const queryFn = vi.fn(({ signal }: { signal: AbortSignal }) => {
    signals.push(signal)
    if (signals.length !== 2) return Promise.resolve(signals.length)
    return new Promise<number>((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true })
    })
  })
  const observer = new QueryObserver(client, { queryKey: key, queryFn })
  const unsubscribe = observer.subscribe(() => {})
  try {
    await vi.waitFor(() => expect(observer.getCurrentResult().data).toBe(1))
    const first = refreshRunQuery(client, key)
    const later = refreshRunQuery(client, key)
    await vi.advanceTimersByTimeAsync(5_000)
    await Promise.all([first, later])
    expect(signals[1].aborted).toBe(true)
    expect(observer.getCurrentResult().data).toBe(3)
  } finally {
    unsubscribe()
    client.clear()
    vi.useRealTimers()
  }
})

it('retries a stalled refresh without needing another event and backs off if it stalls again', async () => {
  vi.useFakeTimers()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const key = ['apiCollectionRunReport', 'recover-without-event'] as const
  client.setQueryData(key, 0)
  const queryFn = vi.fn(({ signal }: { signal: AbortSignal }) => {
    if (queryFn.mock.calls.length > 2) return Promise.resolve(3)
    return new Promise<number>((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true })
    })
  })
  const observer = new QueryObserver(client, { queryKey: key, queryFn, staleTime: Infinity })
  const unsubscribe = observer.subscribe(() => {})
  try {
    const refresh = refreshRunQuery(client, key)
    await vi.advanceTimersByTimeAsync(10_000)
    await refresh
    expect(queryFn).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(29_999)
    expect(queryFn).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(queryFn).toHaveBeenCalledTimes(3)
    expect(observer.getCurrentResult().data).toBe(3)
  } finally {
    unsubscribe()
    client.clear()
    vi.useRealTimers()
  }
})

it('does not run a delayed recovery after the report is closed', async () => {
  vi.useFakeTimers()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const key = ['uiTestSuiteRunReport', 'closed'] as const
  client.setQueryData(key, 0)
  const queryFn = vi.fn(({ signal }: { signal: AbortSignal }) => new Promise<number>((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true })
  }))
  const observer = new QueryObserver(client, { queryKey: key, queryFn, staleTime: Infinity })
  const unsubscribe = observer.subscribe(() => {})
  try {
    const refresh = refreshRunQuery(client, key)
    await vi.advanceTimersByTimeAsync(10_000)
    await refresh
    expect(queryFn).toHaveBeenCalledTimes(2)
    unsubscribe()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(queryFn).toHaveBeenCalledTimes(2)
  } finally {
    unsubscribe()
    client.clear()
    vi.useRealTimers()
  }
})

it('recovers transient HTTP failures without requiring another notification', async () => {
  vi.useFakeTimers()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const key = ['apiCollectionRun', 'temporary-error'] as const
  client.setQueryData(key, 0)
  const queryFn = vi.fn().mockRejectedValueOnce(new ApiError('temporary', 500, 500))
    .mockRejectedValueOnce(new ApiError('temporary', 500, 500)).mockResolvedValue(3)
  const observer = new QueryObserver(client, { queryKey: key, queryFn, staleTime: Infinity })
  const unsubscribe = observer.subscribe(() => {})
  try {
    await refreshRunQuery(client, key)
    expect(queryFn).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(30_000)
    expect(queryFn).toHaveBeenCalledTimes(3)
    expect(observer.getCurrentResult().data).toBe(3)
  } finally {
    unsubscribe()
    client.clear()
    vi.useRealTimers()
  }
})

it('does not retry an authorization failure in the background', async () => {
  vi.useFakeTimers()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const key = ['apiCollectionRun', 'forbidden'] as const
  client.setQueryData(key, 0)
  const queryFn = vi.fn().mockRejectedValue(new ApiError('forbidden', 403, 403))
  const observer = new QueryObserver(client, { queryKey: key, queryFn, staleTime: Infinity })
  const unsubscribe = observer.subscribe(() => {})
  try {
    await refreshRunQuery(client, key)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(queryFn).toHaveBeenCalledTimes(1)
  } finally {
    unsubscribe()
    client.clear()
    vi.useRealTimers()
  }
})

it('skips delayed recovery if a newer snapshot has already arrived', async () => {
  vi.useFakeTimers()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const key = ['uiTestSuiteRun', 'recovered-elsewhere'] as const
  client.setQueryData(key, 0)
  const queryFn = vi.fn().mockRejectedValue(new Error('network error'))
  const observer = new QueryObserver(client, { queryKey: key, queryFn, staleTime: Infinity })
  const unsubscribe = observer.subscribe(() => {})
  try {
    await refreshRunQuery(client, key)
    expect(queryFn).toHaveBeenCalledTimes(2)
    client.setQueryData(key, 1)
    await vi.advanceTimersByTimeAsync(30_000)
    expect(queryFn).toHaveBeenCalledTimes(2)
    expect(observer.getCurrentResult().data).toBe(1)
  } finally {
    unsubscribe()
    client.clear()
    vi.useRealTimers()
  }
})
