import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import type { RequirementOption } from '@/features/requirements/types'
import { useProjectRequirementOptions } from './useProjectRequirementOptions'

const optionItems: RequirementOption[] = [
  { requirementId: 'r1', name: '需求一', sprintId: 's1', sprintName: '迭代一', documentFilename: 'a.docx' },
  { requirementId: 'r2', name: '需求二', sprintId: 's2', sprintName: '迭代二', createdAt: '2026-02-01T00:00:00Z' },
]
const options = Object.assign([...optionItems], { items: optionItems, total: optionItems.length })

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('多个消费者共享一次项目级摘要请求，并提供名称/迭代映射', async () => {
  const getOptions = vi.spyOn(api, 'getProjectRequirementOptions').mockResolvedValue(options)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(() => ({
    first: useProjectRequirementOptions({ activeProjectId: 'project-1' }),
    second: useProjectRequirementOptions({ activeProjectId: 'project-1' }),
  }), { wrapper })

  await waitFor(() => expect(result.current.first.allRequirements).toHaveLength(2))
  expect(getOptions).toHaveBeenCalledTimes(1)
  expect(getOptions).toHaveBeenCalledWith('project-1')
  expect(result.current.first.requirementNameMap.get('r2')).toBe('需求二')
  expect(result.current.first.requirementSprintMap.get('r2')).toBe('s2')
  expect(result.current.first.sprintNameMap.get('s2')).toBe('迭代二')
  await act(async () => {
    await client.invalidateQueries({ queryKey: ['requirementsPool', 'project-1'] })
  })
  expect(getOptions).toHaveBeenCalledTimes(2)
  client.clear()
})
