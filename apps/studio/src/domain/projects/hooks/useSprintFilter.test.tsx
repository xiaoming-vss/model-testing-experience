import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { useSprintFilter } from './useSprintFilter'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const sprints = [
  { sprintId: 'planned-new', name: '新规划', status: 'planned' as const, createdAt: '2026-03-01T00:00:00Z' },
  { sprintId: 'running-old', name: '进行中', status: 'running' as const, createdAt: '2026-01-01T00:00:00Z' },
  { sprintId: 'completed', name: '已完成', status: 'completed' as const, createdAt: '2026-02-01T00:00:00Z' },
]

function setup(projectId = 'project') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  vi.spyOn(api, 'getSprints').mockResolvedValue(Object.assign([...sprints], { total: 3, items: sprints }))
  return { client, wrapper, projectId }
}

it('默认优先选择进行中的迭代', async () => {
  const { client, wrapper, projectId } = setup()
  const { result } = renderHook(() => useSprintFilter(projectId), { wrapper })
  await waitFor(() => expect(result.current.selectedSprintId).toBe('running-old'))
  expect(result.current.selectValue).toBe('running-old')
  expect(result.current.filterOptions.map((option) => option.value)).toEqual(['planned-new', 'running-old', 'completed'])
  client.clear()
})

it('没有进行中的迭代时选择最新创建的一个', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const planned = sprints.filter((sprint) => sprint.status !== 'running')
  vi.spyOn(api, 'getSprints').mockResolvedValue(Object.assign([...planned], { total: planned.length, items: planned }))
  const { result } = renderHook(() => useSprintFilter('project'), { wrapper })
  await waitFor(() => expect(result.current.selectedSprintId).toBe('planned-new'))
  client.clear()
})

it('提供全部迭代时可切回全部，切换项目恢复默认范围', async () => {
  const { client, wrapper, projectId } = setup()
  const { result } = renderHook(() => useSprintFilter(projectId, { allowAll: true }), { wrapper })
  await waitFor(() => expect(result.current.selectedSprintId).toBe('running-old'))
  act(() => result.current.selectSprint('all'))
  expect(result.current.selectedSprintId).toBeUndefined()
  expect(result.current.selectValue).toBe('all')
  act(() => result.current.selectSprint('completed'))
  expect(result.current.selectedSprintId).toBe('completed')
  client.clear()
})

it('受控模式把选择交给页面，并校验无效值回落到默认迭代', async () => {
  const { client, wrapper } = setup()
  const onChange = vi.fn()
  const { result, rerender } = renderHook(
    ({ value }: { value?: string }) => useSprintFilter('project', { controller: { value, onChange } }),
    { wrapper, initialProps: { value: 'missing' as string | undefined } },
  )
  await waitFor(() => expect(result.current.selectedSprintId).toBe('running-old'))
  rerender({ value: 'completed' })
  expect(result.current.selectedSprintId).toBe('completed')
  act(() => result.current.selectSprint('planned-new'))
  expect(onChange).toHaveBeenCalledWith('planned-new')
  client.clear()
})
