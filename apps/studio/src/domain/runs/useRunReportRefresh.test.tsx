import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { refreshRunQuery } from './refreshRunQuery'
import { useRunReportRefresh } from './useRunReportRefresh'

vi.mock('./refreshRunQuery', () => ({ refreshRunQuery: vi.fn() }))

afterEach(() => { vi.clearAllMocks(); vi.useRealTimers() })

it('retries a stale terminal report a bounded number of times', async () => {
  vi.useFakeTimers()
  vi.mocked(refreshRunQuery).mockResolvedValue()
  const client = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { unmount } = renderHook(() => useRunReportRefresh({
    queryKey: 'report', runId: 'run', open: true, status: 'success', reportStatus: 'running',
  }), { wrapper })
  await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
  expect(refreshRunQuery).toHaveBeenCalledTimes(3)
  unmount()
  client.clear()
})

it('stops retrying when the report reaches its terminal state', async () => {
  vi.useFakeTimers()
  vi.mocked(refreshRunQuery).mockResolvedValue()
  const client = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { rerender, unmount } = renderHook(({ reportStatus }) => useRunReportRefresh({
    queryKey: 'report', runId: 'run', open: true, status: 'success', reportStatus,
  }), { wrapper, initialProps: { reportStatus: 'running' } })
  await act(async () => { await vi.advanceTimersByTimeAsync(0) })
  expect(refreshRunQuery).toHaveBeenCalledTimes(1)
  rerender({ reportStatus: 'success' })
  await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
  expect(refreshRunQuery).toHaveBeenCalledTimes(1)
  unmount()
  client.clear()
})
