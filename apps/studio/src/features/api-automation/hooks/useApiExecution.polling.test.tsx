import type { PropsWithChildren } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type ApiCollectionRunSummary } from '@/services/api'
import { useApiExecution } from './useApiExecution'

vi.mock('@/shared/utils/feedback', () => ({
  message: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

const list = (items: ApiCollectionRunSummary[]) => Object.assign([...items], { items: [...items], total: items.length })
const clients: QueryClient[] = []
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
  clients.push(client)
  const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  return { client, ...renderHook(() => useApiExecution({ collectionId: 'collection-1' }), { wrapper }) }
}

async function tick(ms = 1) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms) })
}

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => {
  cleanup()
  clients.splice(0).forEach((client) => client.clear())
  vi.useRealTimers()
  vi.restoreAllMocks()
})

it('队列用例低频刷新，执行后加快，终态停止请求并保留结果', async () => {
  let status: 'pending' | 'running' | 'success' = 'pending'
  vi.spyOn(api, 'getApiCollectionRuns').mockResolvedValue(list([]))
  const detail = vi.spyOn(api, 'getApiCaseRun').mockImplementation(async () => ({ runId: 'case-run-1', status }))
  const { result } = setup()
  await tick()
  act(() => { result.current.setActiveApiCaseRunId('case-run-1') })
  await tick()
  expect(detail).toHaveBeenCalledTimes(1)
  await tick(5000)
  expect(detail).toHaveBeenCalledTimes(1)
  status = 'running'
  await tick(10_000)
  expect(detail).toHaveBeenCalledTimes(2)
  status = 'success'
  await tick(5000)
  expect(detail).toHaveBeenCalledTimes(3)
  expect(result.current.runResult?.status).toBe('success')
  await tick(60_000)
  expect(detail).toHaveBeenCalledTimes(3)
})

it('详情负责轮询，历史关闭时静止，打开的报告只在结束后补取一次', async () => {
  let summary: ApiCollectionRunSummary = { collectionRunId: 'run-1', status: 'running', successCount: 0 }
  const history = vi.spyOn(api, 'getApiCollectionRuns').mockImplementation(async () => list([summary]))
  const detail = vi.spyOn(api, 'getApiCollectionRun').mockImplementation(async () => ({ ...summary }))
  const report = vi.spyOn(api, 'getApiCollectionRunReport').mockImplementation(async () => ({ ...summary, items: [] }))
  const { result, client } = setup()
  await tick()
  act(() => {
    result.current.setActivePollingCollectionRunId('run-1')
    result.current.setSelectedCollectionRunId('run-1')
    result.current.setCollectionRunReportOpen(true)
  })
  await tick()
  expect(detail).toHaveBeenCalledTimes(1)
  expect(report).toHaveBeenCalledTimes(1)
  await tick(10_000)
  expect(detail).toHaveBeenCalledTimes(3)
  expect(report).toHaveBeenCalledTimes(1)
  expect(history).toHaveBeenCalledTimes(1)
  summary = { ...summary, status: 'success', successCount: 2 }
  await tick(5000)
  expect(report).toHaveBeenCalledTimes(2)
  expect(result.current.collectionRunReportQuery.data?.successCount).toBe(2)
  expect(client.getQueryData<ApiCollectionRunSummary[]>(['apiCollectionRuns', 'collection-1'])?.[0].status).toBe('success')
  const calls = { detail: detail.mock.calls.length, history: history.mock.calls.length }
  await tick(60_000)
  expect(detail).toHaveBeenCalledTimes(calls.detail)
  expect(history).toHaveBeenCalledTimes(calls.history)
  expect(report).toHaveBeenCalledTimes(2)
})

it('历史每三十秒发现他人新运行，关闭后停止，重新打开立即更新', async () => {
  let rows: ApiCollectionRunSummary[] = []
  const history = vi.spyOn(api, 'getApiCollectionRuns').mockImplementation(async () => list(rows))
  const { result } = setup()
  await tick()
  expect(history).toHaveBeenCalledTimes(1)
  act(() => { result.current.setCollectionRunHistoryOpen(true) })
  await tick()
  expect(history).toHaveBeenCalledTimes(2)
  rows = [{ collectionRunId: 'other-users-run', status: 'pending' }]
  await tick(29_000)
  expect(history).toHaveBeenCalledTimes(2)
  await tick(1000)
  expect(history).toHaveBeenCalledTimes(3)
  expect(result.current.collectionRunHistoryQuery.data?.[0].collectionRunId).toBe('other-users-run')
  act(() => { result.current.setCollectionRunHistoryOpen(false) })
  await tick(60_000)
  expect(history).toHaveBeenCalledTimes(3)
  act(() => { result.current.setCollectionRunHistoryOpen(true) })
  await tick()
  expect(history).toHaveBeenCalledTimes(4)
})

it('报告关闭时，运行结束不下载报告；之后打开直接加载最终结果', async () => {
  let status: 'running' | 'success' = 'running'
  vi.spyOn(api, 'getApiCollectionRuns').mockImplementation(async () => list([{ collectionRunId: 'run-1', status }]))
  vi.spyOn(api, 'getApiCollectionRun').mockImplementation(async () => ({ collectionRunId: 'run-1', status }))
  const report = vi.spyOn(api, 'getApiCollectionRunReport').mockImplementation(async () => ({ collectionRunId: 'run-1', status, items: [] }))
  const { result } = setup()
  await tick()
  act(() => { result.current.setActivePollingCollectionRunId('run-1') })
  await tick()
  status = 'success'
  await tick(5000)
  expect(report).not.toHaveBeenCalled()
  act(() => {
    result.current.setSelectedCollectionRunId('run-1')
    result.current.setCollectionRunReportOpen(true)
  })
  await tick()
  expect(report).toHaveBeenCalledTimes(1)
  expect(result.current.collectionRunReportQuery.data?.status).toBe('success')
})
