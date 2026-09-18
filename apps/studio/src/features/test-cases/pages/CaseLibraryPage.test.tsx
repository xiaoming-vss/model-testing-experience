import { seedOwnerProject } from '@/test/projectAccess'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { CaseLibraryPage } from './CaseLibraryPage'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/features/projects/hooks/useActiveSprint', () => ({
  useActiveSprint: () => ({ activeSprintId: 'sprint-1', selectSprint: vi.fn() }),
}))
const scopeSpies = vi.hoisted(() => ({ selectSprint: vi.fn(), selectRequirement: vi.fn() }))
vi.mock('@/features/projects/hooks/useSprintRequirementScope', () => ({
  useSprintRequirementScope: () => ({
    currentSprintSelection: null,
    currentRequirementSelection: null,
    resolvedSelectedSprintId: 'sprint-1',
    resolvedSelectedRequirementId: undefined,
    sprints: [{ sprintId: 'sprint-1', name: 'V2.3 迭代' }],
    sprintsQuery: { isLoading: false, error: null },
    requirementsQuery: { data: [], isLoading: false, error: null },
    sprintFilterOptions: [
      { label: '全部迭代', value: 'all' },
      { label: 'V2.3 迭代', value: 'sprint-1' },
    ],
    requirementFilterOptions: [{ label: '全部需求', value: 'all' }],
    selectRequirement: scopeSpies.selectRequirement,
    selectSprint: scopeSpies.selectSprint,
  }),
}))
vi.mock('@/features/projects/hooks/useProjectRequirements', () => ({
  useProjectRequirements: () => ({
    allRequirements: [],
    allRequirementsQuery: { isLoading: false, error: null },
    requirementNameMap: new Map(),
    requirementSprintMap: new Map(),
    sprintNameMap: new Map(),
  }),
}))

const loginCase = {
  caseId: 'case-1',
  suiteId: 'suite-1',
  title: '手机号+验证码登录成功',
  module: '登录',
  priority: 'P0',
  caseType: '功能测试',
  suiteName: '登录与鉴权',
  requirementName: '用户登录支持短信验证',
  sprintName: 'V2.3 迭代',
  content: {
    preconditions: ['已注册手机号'],
    steps: [{ action: '输入验证码后点击登录', expected: '登录成功并跳转首页' }],
  },
}

function renderPage(client: QueryClient, onLeaveToFunctional?: () => void) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CaseLibraryPage onLeaveToFunctional={onLeaveToFunctional} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

beforeEach(() => {
  useWorkbenchStore.setState({ activeProjectId: 'project-1', activeSprintId: null })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('按项目请求用例并展示所属迭代/需求/测试集', async () => {
  const cases = vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  const suites = vi
    .spyOn(api, 'getProjectFunctionTestSuites')
    .mockImplementation(async () => listResponse([{ suiteId: 'suite-1', name: '登录与鉴权' }]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByText('手机号+验证码登录成功')
  expect(screen.getByText('登录与鉴权')).toBeInTheDocument()
  expect(screen.getByText('用户登录支持短信验证')).toBeInTheDocument()
  expect(screen.getByText('P0')).toBeInTheDocument()
  expect(screen.getByText('显示第 1 条 - 第 1 条，共 1 条')).toBeInTheDocument()

  expect(cases).toHaveBeenCalledTimes(1)
  expect(cases.mock.calls[0][0]).toBe('project-1')
  expect(cases.mock.calls[0][1]).toMatchObject({ sprintId: 'sprint-1', page: 1, pageSize: 20 })
  expect(suites.mock.calls[0][1]).toMatchObject({ sprintId: 'sprint-1' })
  client.clear()
})

it('点击行打开只读抽屉，展示前置条件与步骤，且不提供编辑与加入测试单', async () => {
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  const user = userEvent.setup()
  await user.click(await screen.findByText('手机号+验证码登录成功'))

  expect(await screen.findByText('用例详情')).toBeInTheDocument()
  expect(screen.getByText('前置条件')).toBeInTheDocument()
  expect(screen.getByText('已注册手机号')).toBeInTheDocument()
  expect(screen.getByText('输入验证码后点击登录')).toBeInTheDocument()
  expect(screen.getByText('预期：登录成功并跳转首页')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '加入测试单' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '在所属测试集中打开' })).toBeEnabled()
  client.clear()
})

it('无用例且无筛选时，空态提供去功能测试创建用例的主操作', async () => {
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([]))
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([]))
  const onLeaveToFunctional = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client, onLeaveToFunctional)

  const user = userEvent.setup()
  const action = await screen.findByRole('button', { name: '去功能测试创建用例' })
  await user.click(action)
  expect(onLeaveToFunctional).toHaveBeenCalledTimes(1)
  client.clear()
})

it('关键字输入后按关键字重新检索并回到第一页', async () => {
  const cases = vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  const user = userEvent.setup()
  await screen.findByText('手机号+验证码登录成功')
  await user.type(screen.getByPlaceholderText('搜索用例名称 / 模块'), '登录')

  await waitFor(() =>
    expect(cases.mock.calls.some((call) => (call[1] as { keyword?: string }).keyword === '登录')).toBe(true),
  )
  const lastCall = cases.mock.calls.at(-1)?.[1] as { keyword?: string; page?: number }
  expect(lastCall).toMatchObject({ keyword: '登录', page: 1 })
  client.clear()
})
