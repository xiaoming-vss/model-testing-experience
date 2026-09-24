import { seedOwnerProject } from '@/test/projectAccess'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { formatTime } from '@/utils/format'
import { ApiAutomationPage } from './ApiAutomationPage'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/features/projects/hooks/useActiveSprint', () => ({
  useActiveSprint: () => ({
    activeSprintId: 'sprint-1',
    sprints: [{ sprintId: 'sprint-1', name: 'V1.0.0 迭代' }],
    sprintsQuery: { isLoading: false, error: null },
    selectSprint: vi.fn(),
    sprintSelectorOptions: [
      { label: '全部迭代', value: 'all' },
      { label: 'V1.0.0 迭代', value: 'sprint-1' },
    ],
  }),
}))
vi.mock('@/features/projects/hooks/useSprintRequirementScope', () => ({
  useSprintRequirementScope: () => ({
    currentSprintSelection: null,
    currentRequirementSelection: null,
    resolvedSelectedSprintId: 'sprint-1',
    resolvedSelectedRequirementId: undefined,
    sprints: [{ sprintId: 'sprint-1', name: 'V1.0.0 迭代' }],
    sprintsQuery: { isLoading: false, error: null },
    requirementsQuery: { data: [], isLoading: false, error: null },
    sprintFilterOptions: [
      { label: '全部迭代', value: 'all' },
      { label: 'V1.0.0 迭代', value: 'sprint-1' },
    ],
    requirementFilterOptions: [{ label: '全部需求', value: 'all' }],
    selectRequirement: vi.fn(),
    selectSprint: vi.fn(),
  }),
}))
vi.mock('@/features/projects/hooks/useProjectRequirements', () => ({
  useProjectRequirements: () => ({
    allRequirements: [{ requirementId: 'req-1', name: '安装部署', sprintId: 'sprint-1' }],
    allRequirementsQuery: { isLoading: false, error: null },
    requirementNameMap: new Map([['req-1', '安装部署']]),
    requirementSprintMap: new Map([['req-1', 'sprint-1']]),
    sprintNameMap: new Map([['sprint-1', 'V1.0.0 迭代']]),
  }),
}))

const collection = {
  collectionId: 'collection-1',
  requirementId: 'req-1',
  name: 'dev-a',
  description: '转换链路接口集',
  createdAt: '2026-08-05T11:03:24',
  updatedAt: '2026-08-05T11:03:24',
}

const environment = {
  environmentId: 'environment-1',
  projectId: 'project-1',
  name: 'dev',
  baseUrl: 'http://127.0.0.1:9000',
  isDefault: true,
  updatedAt: '2026-07-29T14:54:52',
}

const envVars = [
  { envVarId: 'var-1', environmentId: 'environment-1', varKey: 'TOKEN', value: 'x' },
  { envVarId: 'var-2', environmentId: 'environment-1', varKey: 'HOST', value: 'y' },
]

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ApiAutomationPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function buildClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  return client
}

/** 图标按钮没有文字，只能按 aria-label 取。 */
function iconButton(label: string, scope: ParentNode = document) {
  const node = scope.querySelector(`[aria-label="${label}"]`)
  if (!node) throw new Error(`找不到图标按钮：${label}`)
  return node as HTMLButtonElement
}

beforeEach(() => {
  useWorkbenchStore.setState({ activeProjectId: 'project-1', activeSprintId: 'sprint-1' })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('列出测试集，并在头部卡片里展示当前环境信息', async () => {
  vi.spyOn(api, 'getApiCollections').mockImplementation(async () => listResponse([collection]))
  const environments = vi
    .spyOn(api, 'getApiEnvironments')
    .mockImplementation(async () => listResponse([environment]))
  const vars = vi
    .spyOn(api, 'getApiEnvironmentVars')
    .mockImplementation(async () => listResponse(envVars))
  const client = buildClient()
  renderPage(client)

  await screen.findByText('dev-a')
  expect(screen.getByText('V1.0.0 迭代 / 安装部署')).toBeInTheDocument()
  expect(screen.getByText('转换链路接口集')).toBeInTheDocument()
  // 创建时间与最近更新都是等宽时间格，文案走共用的 formatTime（会换算到时区）
  const timeCells = document.querySelectorAll('.api-test-time-cell')
  expect(timeCells).toHaveLength(2)
  expect(timeCells[0]).toHaveTextContent(formatTime(collection.createdAt))
  expect(timeCells[1]).toHaveTextContent(formatTime(collection.updatedAt))

  expect(environments.mock.calls[0][0]).toBe('project-1')
  expect(vars).not.toHaveBeenCalled()
  client.clear()
})

it('搜索按名称与描述在本地过滤，清空后恢复', async () => {
  const other = { ...collection, collectionId: 'collection-2', name: 'smoke-b', description: '' }
  vi.spyOn(api, 'getApiCollections').mockImplementation(async () =>
    listResponse([collection, other]),
  )
  vi.spyOn(api, 'getApiEnvironments').mockImplementation(async () => listResponse([environment]))
  vi.spyOn(api, 'getApiEnvironmentVars').mockImplementation(async () => listResponse(envVars))
  const client = buildClient()
  renderPage(client)

  await screen.findByText('dev-a')
  const user = userEvent.setup()
  const search = screen.getByPlaceholderText('搜索测试集名称 / 描述')

  // 描述命中
  await user.type(search, '转换链路')
  await waitFor(() => expect(screen.queryByText('smoke-b')).toBeNull())
  expect(screen.getByText('dev-a')).toBeInTheDocument()

  await user.clear(search)
  await waitFor(() => expect(screen.getByText('smoke-b')).toBeInTheDocument())
  client.clear()
})

it('搜索无结果时空态给出清空入口，而不是新建入口', async () => {
  vi.spyOn(api, 'getApiCollections').mockImplementation(async () => listResponse([collection]))
  vi.spyOn(api, 'getApiEnvironments').mockImplementation(async () => listResponse([environment]))
  vi.spyOn(api, 'getApiEnvironmentVars').mockImplementation(async () => listResponse(envVars))
  const client = buildClient()
  renderPage(client)

  await screen.findByText('dev-a')
  await userEvent.setup().type(screen.getByPlaceholderText('搜索测试集名称 / 描述'), '不存在的东西')

  expect(await screen.findByText('没有符合搜索条件的API测试集')).toBeInTheDocument()
  // 空态里给的是清空搜索，不是新建入口（工具栏上的新建按钮仍在，这里只看表格卡片内）
  const card = within(document.querySelector('.api-test-table-card') as HTMLElement)
  expect(card.queryByText('新建API测试集')).toBeNull()

  await userEvent.setup().click(screen.getByText('清空搜索'))
  await waitFor(() => expect(screen.getByText('dev-a')).toBeInTheDocument())
  client.clear()
})

it('有环境时行内运行按钮提交当前环境，没有环境时不可用', async () => {
  vi.spyOn(api, 'getApiCollections').mockImplementation(async () => listResponse([collection]))
  const run = vi
    .spyOn(api, 'runApiCollection')
    .mockImplementation(async () => ({ status: 'success' }))
  const environments = vi
    .spyOn(api, 'getApiEnvironments')
    .mockImplementation(async () => listResponse([environment]))
  vi.spyOn(api, 'getApiEnvironmentVars').mockImplementation(async () => listResponse(envVars))
  const client = buildClient()
  const { container } = renderPage(client)

  await screen.findByText('dev-a')
  await waitFor(() => expect(iconButton('运行API测试集', container)).toBeEnabled())
  await userEvent.setup().click(iconButton('运行API测试集', container))

  await waitFor(() =>
    expect(run).toHaveBeenCalledWith('collection-1', { environmentId: 'environment-1' }),
  )
  client.clear()

  // 没有环境可选时，运行按钮禁用（而不是点了才提示）
  cleanup()
  environments.mockImplementation(async () => listResponse([]))
  const clientWithoutEnv = buildClient()
  const second = renderPage(clientWithoutEnv)
  await screen.findByText('dev-a')
  expect(iconButton('运行API测试集', second.container)).toBeDisabled()
  clientWithoutEnv.clear()
})
