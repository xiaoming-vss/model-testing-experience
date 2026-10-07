import type { PropsWithChildren } from 'react'
import { QueryClient, QueryClientProvider, focusManager, useQuery } from '@tanstack/react-query'
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getRunPollingInterval, RUN_HISTORY_POLL_INTERVAL } from '@/domain/runs/polling'
import type { ListResponse } from '@/shared/api/request'
import { useTaskRunHistorySync } from './useTaskRunHistorySync'

type Run = { runId: string; status: string; updatedAt: string; reviewStatus?: string; resultYaml?: string }
const list = (items: Run[]) => Object.assign([...items], { items: [...items], total: items.length })
const clients: QueryClient[] = []

function setup(getRun: () => Run) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity, refetchOnWindowFocus: false } } })
  clients.push(client)
  const fetchHistory = vi.fn(async () => list([getRun()]))
  const fetchDetail = vi.fn(async () => ({ ...getRun() }))
  const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const view = renderHook(() => {
    const history = useQuery({ queryKey: ['runs', 'task-1'], queryFn: fetchHistory, refetchInterval: RUN_HISTORY_POLL_INTERVAL })
    const detail = useQuery({ queryKey: ['run', 'run-1'], queryFn: fetchDetail, refetchInterval: (query) => getRunPollingInterval(query.state.data?.status) })
    useTaskRunHistorySync({ historyKey: 'runs', detailKey: 'run', taskId: 'task-1', selectedRunId: 'run-1', history: history.data, detail: detail.data })
    return { history: history.data, detail: detail.data }
  }, { wrapper })
  return { client, fetchHistory, fetchDetail, ...view }
}

async function tick(ms = 1) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms) })
}

beforeEach(() => {
  vi.useFakeTimers()
  focusManager.setFocused(true)
})
afterEach(() => {
  cleanup()
  clients.splice(0).forEach((client) => client.clear())
  focusManager.setFocused(undefined)
  vi.useRealTimers()
})

it('等待审核仍能继续推进，详情将最终结果同步到历史，无需高频请求历史', async () => {
  let run: Run = { runId: 'run-1', status: 'waiting_review', updatedAt: '2026-10-04T00:00:00Z' }
  const { fetchHistory, fetchDetail, result } = setup(() => run)
  await tick()
  await tick(5000)
  expect(fetchDetail).toHaveBeenCalledTimes(1)
  run = { ...run, status: 'running', updatedAt: '2026-10-04T00:00:10Z' }
  await tick(10_000)
  expect(fetchDetail).toHaveBeenCalledTimes(2)
  run = { ...run, status: 'success', resultYaml: 'cases: []', updatedAt: '2026-10-04T00:00:20Z' }
  await tick(5000)
  expect(fetchDetail).toHaveBeenCalledTimes(3)
  expect(fetchHistory).toHaveBeenCalledTimes(1)
  await tick()
  expect(result.current.history?.items[0].status).toBe('success')
  expect(result.current.detail?.resultYaml).toBe('cases: []')
  await tick(60_000)
  expect(fetchDetail).toHaveBeenCalledTimes(3)
})

it('已完成的详情停止轮询，历史发现他人的审核变化后重新获取一次详情', async () => {
  let run: Run = { runId: 'run-1', status: 'success', reviewStatus: 'pending', updatedAt: '2026-10-04T00:00:00Z', resultYaml: 'old' }
  const { fetchDetail, fetchHistory, result } = setup(() => run)
  await tick()
  await tick(29_000)
  expect(fetchDetail).toHaveBeenCalledTimes(1)
  expect(fetchHistory).toHaveBeenCalledTimes(1)
  run = { ...run, reviewStatus: 'approved', updatedAt: '2026-10-04T00:00:30Z', resultYaml: 'edited by another user' }
  await tick(1000)
  expect(fetchDetail).toHaveBeenCalledTimes(2)
  await tick()
  expect(result.current.detail?.reviewStatus).toBe('approved')
  expect(result.current.detail?.resultYaml).toBe('edited by another user')
  await tick(60_000)
  expect(fetchDetail).toHaveBeenCalledTimes(2)
})

it('后台标签页不执行历史或详情轮询，恢复前台后继续获取状态', async () => {
  const run: Run = { runId: 'run-1', status: 'running', updatedAt: '2026-10-04T00:00:00Z' }
  const { fetchDetail, fetchHistory } = setup(() => run)
  await tick()
  focusManager.setFocused(false)
  await tick(60_000)
  expect(fetchDetail).toHaveBeenCalledTimes(1)
  expect(fetchHistory).toHaveBeenCalledTimes(1)
  focusManager.setFocused(true)
  await tick(5000)
  expect(fetchDetail).toHaveBeenCalledTimes(2)
})

it('较旧的历史响应不会把新详情恢复成执行中', async () => {
  let run: Run = { runId: 'run-1', status: 'success', updatedAt: '2026-10-04T00:00:30Z' }
  const { fetchDetail, result } = setup(() => run)
  await tick()
  run = { ...run, status: 'running', updatedAt: '2026-10-04T00:00:00Z' }
  await tick(30_000)
  expect(fetchDetail).toHaveBeenCalledTimes(1)
  expect(result.current.detail?.status).toBe('success')
})

it('缓存同步保留列表数量与规范化 items，不能改动其他运行', async () => {
  const run: Run = { runId: 'run-1', status: 'running', updatedAt: '2026-10-04T00:00:00Z' }
  const { client } = setup(() => run)
  await tick()
  const other = { ...run, runId: 'run-2' }
  act(() => {
    client.setQueryData<ListResponse<Run>>(['runs', 'task-1'], Object.assign([run, other], { items: [run, other], total: 10 }))
    client.setQueryData(['run', 'run-1'], { ...run, status: 'success', updatedAt: '2026-10-04T00:00:10Z' })
  })
  await tick()
  const rows = client.getQueryData<ListResponse<Run>>(['runs', 'task-1'])!
  expect(rows.total).toBe(10)
  expect(rows.items[0].status).toBe('success')
  expect(rows[0].status).toBe('success')
  expect(rows.items[1]).toEqual(other)
})


it('详情更新跨页摘要与统计，旧页面仍用全局最新运行约束发起操作', async () => {
  const run: Run = { runId: 'run-1', status: 'running', updatedAt: '2026-10-04T00:00:00Z' }
  const { client } = setup(() => run)
  await tick()
  const other = { ...run, runId: 'older', status: 'success' }
  act(() => {
    client.setQueryData(['runs', 'task-1', 1, 20], Object.assign([run], { items: [run], total: 21,
      statusCounts: { running: 1, success: 20 }, latestRun: run }))
    client.setQueryData(['runs', 'task-1', 2, 20], Object.assign([other], { items: [other], total: 21,
      statusCounts: { running: 1, success: 20 }, latestRun: run }))
    client.setQueryData(['run', 'run-1'], { ...run, status: 'success', updatedAt: '2026-10-04T00:00:10Z' })
  })
  await tick()
  const page = client.getQueryData<ListResponse<Run> & { statusCounts: Record<string, number>; latestRun: Run }>(['runs', 'task-1', 2, 20])!
  expect(page.items).toEqual([other])
  expect(page.latestRun.status).toBe('success')
  expect(page.statusCounts).toEqual({ running: 0, success: 21 })
  expect(page.total).toBe(21)
})
