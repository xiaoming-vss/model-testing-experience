import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type Sprint } from '@/services/api'
import { useWorkbenchStore } from '../store/workbench.store'
import { useActiveSprint } from './useActiveSprint'

const clients: QueryClient[] = []
const sprints: Sprint[] = [
  { sprintId: 'old', name: '旧迭代', status: 'completed', createdAt: '2026-08-01T00:00:00Z' },
  { sprintId: 'latest', name: '最新迭代', status: 'running', created_at: '2026-09-01T00:00:00Z' },
  { sprintId: 'undated', name: '无日期', status: 'planned' },
]

afterEach(() => {
  cleanup()
  clients.forEach(client => client.clear())
  clients.length = 0
  vi.restoreAllMocks()
  useWorkbenchStore.getState().setActiveProjectId(undefined)
})

function list<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function setup(items = sprints) {
  vi.spyOn(api, 'getProjects').mockResolvedValue(list([
    { projectId: 'project', name: '项目' }, { projectId: 'other', name: '其他项目' },
  ]))
  vi.spyOn(api, 'getSprints').mockResolvedValue(list(items))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  clients.push(client)
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  return { ...renderHook(() => useActiveSprint(), { wrapper }), client }
}

it('首次进入选择创建时间最新的迭代，不依赖接口排序', async () => {
  const { result } = setup()
  await waitFor(() => expect(result.current.activeSprintId).toBe('latest'))
  expect(useWorkbenchStore.getState().activeSprintId).toBe('latest')
})

it.each(['old', 'all'])('手动选择 %s 后刷新数据和重新挂载仍保留选择，重置会话后恢复最新', async selection => {
  const { result, client, unmount } = setup()
  await waitFor(() => expect(result.current.activeSprintId).toBe('latest'))
  act(() => result.current.selectSprint(selection))
  await act(async () => { await client.invalidateQueries({ queryKey: ['sprints'] }) })
  expect(result.current.activeSprintId).toBe(selection === 'all' ? undefined : selection)
  unmount()
  const next = renderHook(() => useActiveSprint(), {
    wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  })
  expect(next.result.current.activeSprintId).toBe(selection === 'all' ? undefined : selection)
  act(() => useWorkbenchStore.getState().setActiveProjectId('project'))
  await waitFor(() => expect(next.result.current.activeSprintId).toBe('latest'))
})

it('切换项目后选择新项目最新迭代', async () => {
  const { result } = setup()
  await waitFor(() => expect(result.current.activeSprintId).toBe('latest'))
  vi.mocked(api.getSprints).mockResolvedValue(list<Sprint>([{ sprintId: 'other-latest', name: '新项目迭代', status: 'planned' }]))
  act(() => useWorkbenchStore.getState().setActiveProjectId('other'))
  await waitFor(() => expect(result.current.activeSprintId).toBe('other-latest'))
})

it('没有迭代时显示全部迭代，后续加载到迭代后选择最新', async () => {
  const { result, client } = setup([])
  await waitFor(() => expect(result.current.sprintsQuery.isSuccess).toBe(true))
  expect(result.current.activeSprintId).toBeUndefined()
  vi.mocked(api.getSprints).mockResolvedValue(list(sprints))
  await act(async () => { await client.invalidateQueries({ queryKey: ['sprints'] }) })
  await waitFor(() => expect(result.current.activeSprintId).toBe('latest'))
})
