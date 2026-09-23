import { seedOwnerProject } from '@/test/projectAccess'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { formatTime } from '@/utils/format'
import { UiAutomationPage } from './UiAutomationPage'

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

const suite = {
  suiteId: 'suite-1',
  requirementId: 'req-1',
  name: 'xiaoming',
  description: '登录链路回放',
  headless: false,
  slowMoMs: 300,
  viewportWidth: 1440,
  viewportHeight: 900,
  defaultStepTimeoutMs: 5000,
  screenshotPolicy: 'on_failure' as const,
  createdAt: '2026-07-29T14:55:42',
  updatedAt: '2026-07-30T13:24:46',
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <UiAutomationPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function buildClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  return client
}

beforeEach(() => {
  useWorkbenchStore.setState({ activeProjectId: 'project-1', activeSprintId: 'sprint-1' })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('列出测试集，头部信息条与行内徽标展示默认运行配置', async () => {
  vi.spyOn(api, 'getUiTestSuites').mockImplementation(async () => listResponse([suite]))
  const client = buildClient()
  renderPage(client)

  await screen.findByText('xiaoming')

  // 信息条：标题、副标题与三项遥测（视口 / 超时取自默认运行配置）
  const banner = within(document.querySelector('.ui-suite-list-banner') as HTMLElement)
  expect(banner.getByText('UI自动化测试集')).toBeInTheDocument()
  expect(banner.getByText('跨浏览器 Playwright / Chromium 无头及可视化回放执行引擎')).toBeInTheDocument()
  expect(banner.getByText('默认可视模式')).toBeInTheDocument()
  expect(banner.getByText('1440 × 900')).toBeInTheDocument()
  expect(banner.getByText('5000ms')).toBeInTheDocument()

  // 所属迭代 / 需求：迭代是等宽色块，需求是普通文字
  expect(screen.getByText('V1.0.0 迭代')).toBeInTheDocument()
  expect(screen.getByText('安装部署')).toBeInTheDocument()

  // 运行配置徽标：可视 / 视口 / 超时 + 截图策略
  expect(screen.getByText('可视')).toBeInTheDocument()
  expect(screen.getByText('5000ms / 失败时截图')).toBeInTheDocument()

  expect(screen.getByText('登录链路回放')).toBeInTheDocument()

  // 创建时间与最近更新都是等宽时间格，文案走共用的 formatTime（会换算到时区）
  const timeCells = document.querySelectorAll('.ui-suite-list-time-cell')
  expect(timeCells).toHaveLength(2)
  expect(timeCells[0]).toHaveTextContent(formatTime(suite.createdAt))
  expect(timeCells[1]).toHaveTextContent(formatTime(suite.updatedAt))

  client.clear()
})

it('搜索按名称与描述在本地过滤，清空后恢复', async () => {
  const other = { ...suite, suiteId: 'suite-2', name: 'xm-test', description: '' }
  vi.spyOn(api, 'getUiTestSuites').mockImplementation(async () => listResponse([suite, other]))
  const client = buildClient()
  renderPage(client)

  await screen.findByText('xiaoming')
  const user = userEvent.setup()
  const search = screen.getByPlaceholderText('搜索UI测试集名称 / 描述')

  // 描述命中
  await user.type(search, '登录链路')
  await waitFor(() => expect(screen.queryByText('xm-test')).toBeNull())
  expect(screen.getByText('xiaoming')).toBeInTheDocument()

  await user.clear(search)
  await waitFor(() => expect(screen.getByText('xm-test')).toBeInTheDocument())
  client.clear()
})

it('搜索无结果时空态给出清空入口，而不是新建入口', async () => {
  vi.spyOn(api, 'getUiTestSuites').mockImplementation(async () => listResponse([suite]))
  const client = buildClient()
  renderPage(client)

  await screen.findByText('xiaoming')
  await userEvent.setup().type(screen.getByPlaceholderText('搜索UI测试集名称 / 描述'), '不存在的东西')

  expect(await screen.findByText('没有符合搜索条件的 UI测试集')).toBeInTheDocument()
  // 空态里给的是清空搜索，不是新建入口（工具栏上的新建按钮仍在，这里只看表格卡片内）
  const card = within(document.querySelector('.ui-suite-list-table-card') as HTMLElement)
  expect(card.queryByText('新建测试集')).toBeNull()

  await userEvent.setup().click(screen.getByText('清空搜索'))
  await waitFor(() => expect(screen.getByText('xiaoming')).toBeInTheDocument())
  client.clear()
})

it('工具栏的刷新按钮重新拉取测试集列表', async () => {
  const list = vi.spyOn(api, 'getUiTestSuites').mockImplementation(async () => listResponse([suite]))
  const client = buildClient()
  renderPage(client)

  await screen.findByText('xiaoming')
  await waitFor(() => expect(list).toHaveBeenCalledTimes(1))

  await userEvent.setup().click(screen.getByLabelText('刷新测试集列表'))
  await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
  client.clear()
})
