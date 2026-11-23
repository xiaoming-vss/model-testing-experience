import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { useSprintRequirementScope } from './useSprintRequirementScope'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const sprints = [
  { sprintId: 'sprint-1', name: '迭代一', status: 'completed' as const, createdAt: '2026-01-01T00:00:00Z' },
  { sprintId: 'sprint-2', name: '迭代二', status: 'running' as const, createdAt: '2026-02-01T00:00:00Z' },
]
const requirementOptions = [
  { requirementId: 'r1', name: '需求一', sprintId: 'sprint-1', sprintName: '迭代一', createdAt: '2026-01-01T00:00:00Z' },
  { requirementId: 'r2', name: '需求二', sprintId: 'sprint-2', sprintName: '迭代二', createdAt: '2026-02-01T00:00:00Z' },
]

function createWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  return { client, wrapper }
}

it('默认选择进行中的最新迭代，并按该迭代查询需求', async () => {
  const { client, wrapper } = createWrapper()
  vi.spyOn(api, 'getSprints').mockResolvedValue(Object.assign([...sprints], { total: 2, items: sprints }))
  const requirements = vi.spyOn(api, 'getRequirements').mockResolvedValue(Object.assign([], { total: 0, items: [] }))
  const { result } = renderHook(() => useSprintRequirementScope({
    activeProjectId: 'project',
    includeAllRequirementOption: true,
  }), { wrapper })

  await waitFor(() => expect(result.current.resolvedSelectedSprintId).toBe('sprint-2'))
  await waitFor(() => expect(requirements).toHaveBeenCalledWith('sprint-2', { page: 1, pageSize: 100 }))
  client.clear()
})

it('切换迭代时清除旧需求选择，并在项目摘要上本地过滤', async () => {
  const { client, wrapper } = createWrapper()
  vi.spyOn(api, 'getSprints').mockResolvedValue(Object.assign([...sprints], { total: 2, items: sprints }))
  const { result } = renderHook(() => useSprintRequirementScope({
    activeProjectId: 'project',
    includeAllRequirementOption: true,
    defaultRequirementSelection: 'all',
    requirementOptions,
  }), { wrapper })

  await waitFor(() => expect(result.current.resolvedSelectedSprintId).toBe('sprint-2'))
  expect(result.current.requirements.map((requirement) => requirement.name)).toEqual(['需求二'])
  expect(result.current.resolvedSelectedRequirementId).toBeUndefined()
  act(() => result.current.selectRequirement('r2'))
  expect(result.current.resolvedSelectedRequirementId).toBe('r2')

  act(() => result.current.selectSprint('sprint-1'))
  expect(result.current.resolvedSelectedSprintId).toBe('sprint-1')
  expect(result.current.resolvedSelectedRequirementId).toBeUndefined()
  expect(result.current.requirements.map((requirement) => requirement.name)).toEqual(['需求一'])
  act(() => result.current.selectRequirement('r1'))
  expect(result.current.resolvedSelectedRequirementId).toBe('r1')
  client.clear()
})

it('选择全部迭代时保留全部项目摘要', async () => {
  const { client, wrapper } = createWrapper()
  vi.spyOn(api, 'getSprints').mockResolvedValue(Object.assign([...sprints], { total: 2, items: sprints }))
  const { result } = renderHook(() => useSprintRequirementScope({
    activeProjectId: 'project',
    includeAllSprintOption: true,
    requirementOptions,
  }), { wrapper })

  await waitFor(() => expect(result.current.resolvedSelectedSprintId).toBe('sprint-2'))
  act(() => result.current.selectSprint('all'))
  expect(result.current.resolvedSelectedSprintId).toBeUndefined()
  expect(result.current.requirements.map((requirement) => requirement.name)).toEqual(['需求一', '需求二'])
  expect(result.current.sprintFilterOptions.map((option) => option.label)).toEqual(['全部迭代', '迭代一', '迭代二'])
  client.clear()
})
