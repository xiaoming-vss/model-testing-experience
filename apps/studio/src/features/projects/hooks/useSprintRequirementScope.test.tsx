import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { useSprintRequirementScope } from './useSprintRequirementScope'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('顶部迭代变化时不沿用旧需求筛选，并查询新迭代', async () => {
  vi.spyOn(api, 'getSprints').mockResolvedValue(Object.assign([], { items: [], total: 0 }))
  const requirements = vi.spyOn(api, 'getRequirements').mockResolvedValue(Object.assign([], { items: [], total: 0 }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result, rerender, unmount } = renderHook(({ sprintId }: { sprintId?: string }) => useSprintRequirementScope({
    activeProjectId: 'project', includeAllRequirementOption: true, defaultToAllWhenIncluded: true,
    sprintScope: { value: sprintId },
  }), { wrapper, initialProps: { sprintId: 'first' as string | undefined } })
  act(() => result.current.selectRequirement('old-requirement'))
  expect(result.current.resolvedSelectedRequirementId).toBe('old-requirement')
  rerender({ sprintId: 'second' })
  expect(result.current.resolvedSelectedRequirementId).toBeUndefined()
  expect(result.current.resolvedSelectedSprintId).toBe('second')
  await waitFor(() =>
    expect(requirements).toHaveBeenCalledWith('second', { page: 1, pageSize: 100 }),
  )
  act(() => result.current.selectRequirement('second-requirement'))
  rerender({ sprintId: undefined })
  expect(result.current.resolvedSelectedRequirementId).toBeUndefined()
  expect(result.current.resolvedSelectedSprintId).toBeUndefined()
  unmount(); client.clear()
})


it('传入项目级摘要时按迭代本地过滤，不再请求 sprint 全量列表', async () => {
  vi.spyOn(api, 'getSprints').mockResolvedValue(Object.assign([], { items: [], total: 0 }))
  const sprintRequirements = vi.spyOn(api, 'getRequirements').mockResolvedValue(Object.assign([], { items: [], total: 0 }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(() => useSprintRequirementScope({
    activeProjectId: 'project',
    includeAllRequirementOption: true,
    sprintScope: { value: 'sprint-2' },
    requirementOptions: [
      { requirementId: 'r1', name: '需求一', sprintId: 'sprint-1', sprintName: '迭代一', createdAt: '2026-01-01T00:00:00Z' },
      { requirementId: 'r2', name: '需求二', sprintId: 'sprint-2', sprintName: '迭代二', createdAt: '2026-02-01T00:00:00Z' },
    ],
  }), { wrapper })

  expect(result.current.requirements.map((requirement) => requirement.name)).toEqual(['需求二'])
  expect(result.current.requirementFilterOptions.map((option) => option.label)).toEqual(['全部需求', '需求二'])
  expect(result.current.resolvedSelectedRequirementId).toBe('r2')
  expect(sprintRequirements).not.toHaveBeenCalled()
  client.clear()
})


it('全部迭代时保留全部项目摘要', () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(() => useSprintRequirementScope({
    activeProjectId: 'project',
    includeAllSprintOption: true,
    sprintScope: { value: null },
    requirementOptions: [
      { requirementId: 'r1', name: '需求一', sprintId: 'sprint-1', sprintName: '迭代一' },
      { requirementId: 'r2', name: '需求二', sprintId: 'sprint-2', sprintName: '迭代二' },
    ],
  }), { wrapper })

  expect(result.current.requirements.map((requirement) => requirement.name)).toEqual(['需求一', '需求二'])
  client.clear()
})
