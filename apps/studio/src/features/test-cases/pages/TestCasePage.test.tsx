import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { TestCasePage } from './TestCasePage'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/features/projects/hooks/useActiveSprint', () => ({
  useActiveSprint: () => ({ activeSprintId: 'sprint-1', selectSprint: vi.fn() }),
}))
vi.mock('@/features/projects/hooks/useSprintRequirementScope', () => ({
  useSprintRequirementScope: () => ({
    sprints: [], sprintsQuery: { isLoading: false }, requirementsQuery: { data: [] },
    sprintFilterOptions: [], requirementFilterOptions: [],
    selectRequirement: vi.fn(), selectSprint: vi.fn(),
  }),
}))
vi.mock('@/features/projects/hooks/useProjectRequirements', () => ({
  useProjectRequirements: () => ({
    allRequirements: [], allRequirementsQuery: { isLoading: false },
    requirementNameMap: new Map(), requirementSprintMap: new Map(), sprintNameMap: new Map(),
  }),
}))

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('删除功能测试集后重新请求当前列表并更新行和总数', async () => {
  const suite = { suiteId: 'suite-1', name: '待删除测试集', requirementId: 'req-1' }
  let deleted = false
  const getSuites = vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => {
    const items = deleted ? [] : [suite]
    return Object.assign([...items], { items, total: items.length })
  })
  const deleteSuite = vi.spyOn(api, 'deleteFunctionTestSuite').mockImplementation(async () => {
    deleted = true
    return {}
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  render(<QueryClientProvider client={client}><MemoryRouter>
    <TestCasePage scope={{ projectId: 'project-1', sprintId: 'sprint-1', requirementId: 'req-1' }} />
  </MemoryRouter></QueryClientProvider>)
  const user = userEvent.setup()
  await screen.findByText('待删除测试集')
  await user.click(screen.getByRole('button', { name: '删除功能测试集' }))
  await user.click(await screen.findByRole('button', { name: /OK|确\s*定/ }))
  await waitFor(() => expect(deleteSuite).toHaveBeenCalledWith('suite-1'))
  await waitFor(() => expect(screen.queryByText('待删除测试集')).not.toBeInTheDocument())
  expect(getSuites.mock.calls.length).toBeGreaterThan(1)
  expect(screen.getByText('显示第 0 条 - 第 0 条，共 0 条')).toBeInTheDocument()
  client.clear()
})
