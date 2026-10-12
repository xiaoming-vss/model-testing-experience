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
  await waitFor(() => expect(requirements).toHaveBeenCalledWith('second'))
  act(() => result.current.selectRequirement('second-requirement'))
  rerender({ sprintId: undefined })
  expect(result.current.resolvedSelectedRequirementId).toBeUndefined()
  expect(result.current.resolvedSelectedSprintId).toBeUndefined()
  unmount(); client.clear()
})
