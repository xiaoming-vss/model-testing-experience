import { UiTestSuiteCasePage } from '@/features/ui-automation/pages/UiTestSuiteCasePage'
import { api, ApiError } from '@/services/api'
import { TestThemeProvider as ThemeProvider } from '@/test/TestThemeProvider'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

/*
 * UI测试集详情页按设计稿重做（顶栏 + 控制条 + 左步骤编排 / 右执行回放与控制台），
 * 这组测试锁住设计稿要求的结构钩子与三条主链路：运行测试集、切换当前用例、调试运行后在右栏读结果。
 */

vi.mock('@/features/projects/hooks/useProjectAccess', () => ({
  useProjectAccess: () => ({ can: () => true, loading: false, error: null }),
}))
vi.mock('@/shared/utils/feedback', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/utils/feedback')>()),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

const list = <T,>(items: T[]) => Object.assign([...items], { items, total: items.length })

const suite = {
  suiteId: 'suite-1',
  requirementId: 'requirement-1',
  name: 'xiaoming',
  description: '登录链路回放',
  headless: false,
  slowMoMs: 300,
  viewportWidth: 1440,
  viewportHeight: 900,
  defaultStepTimeoutMs: 5000,
  screenshotPolicy: 'after_each_step' as const,
}

const stepsJson = JSON.stringify([
  { orderNo: 1, stepName: '打开登录页', keyword: 'open', operationValue: 'http://localhost:5173/login', enabled: true },
  { orderNo: 2, stepName: '输入用户名', keyword: 'input', locatorType: 'placeholder', locatorValue: '请输入用户名', operationValue: 'admin', enabled: true },
])

const cases = [
  { caseId: 'case-1', suiteId: 'suite-1', name: '登录成功-跳转工作台', enabled: true, orderNo: 1, stepsJson },
  { caseId: 'case-2', suiteId: 'suite-1', name: '登录失败-密码为空', enabled: true, orderNo: 2, stepsJson },
]

const caseRun = {
  runId: 'case-run-1',
  status: 'success' as const,
  success: true,
  durationMs: 1840,
  currentUrl: 'http://localhost:5173/dashboard',
  usedVariables: [
    { name: 'username', value: 'admin', orderNo: 2, secret: false },
    { name: 'password', value: '********', orderNo: 2, secret: true },
  ],
  variableWrites: [
    { name: 'taskId', previousValue: '20', value: '31', orderNo: 1, created: false },
  ],
  stepResults: [
    { orderNo: 1, stepName: '打开登录页', keyword: 'open', status: 'success' as const, success: true, durationMs: 312, startedAt: '2026-09-23T02:42:01.120', screenshotPath: 'http://127.0.0.1:9000/files/step-1.png' },
    { orderNo: 2, stepName: '输入用户名', keyword: 'input', status: 'failed' as const, success: false, durationMs: 45, startedAt: '2026-09-23T02:42:01.442', actualValue: 'admin', errorMessage: '元素未找到', screenshotPath: 'http://127.0.0.1:9000/files/step-2.png' },
  ],
}

function mockDetailApis() {
  vi.spyOn(api, 'getUiTestSuite').mockResolvedValue(suite)
  vi.spyOn(api, 'getUiTestCases').mockResolvedValue(list(cases))
  vi.spyOn(api, 'getUiTestCase').mockImplementation(async (caseId: string) => cases.find((item) => item.caseId === caseId) ?? cases[0])
  vi.spyOn(api, 'getRequirement').mockResolvedValue({ requirementId: 'requirement-1', sprintId: 'sprint-1', name: '安装部署' })
  vi.spyOn(api, 'getSprint').mockResolvedValue({ sprintId: 'sprint-1', projectId: 'project-1', name: 'v1.0.0', status: 'running' })
  vi.spyOn(api, 'getUiTestSuiteRuns').mockResolvedValue(list([{ suiteRunId: 'suite-run-1', suiteId: 'suite-1', status: 'success', startedAt: new Date().toISOString(), totalCount: 2, successCount: 2 }]))
  vi.spyOn(api, 'getUiTestCaseRun').mockResolvedValue(caseRun)
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(
    list([{ environmentId: 'env-ui-1', kind: 'ui', name: 'UI 环境', baseUrl: 'http://127.0.0.1:5173', isDefault: true }]),
  )
  vi.spyOn(api, 'getApiEnvironmentVars').mockResolvedValue(
    list([
      { envVarId: 'var-1', environmentId: 'env-ui-1', varKey: 'token', value: 'abc' },
      { envVarId: 'var-2', environmentId: 'env-ui-1', varKey: 'userId', value: '42' },
    ]),
  )
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <MemoryRouter initialEntries={['/ui-automation/suites/suite-1']}>
          <Routes>
            <Route path="/ui-automation/suites/:suiteId" element={<UiTestSuiteCasePage />} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  )
  return { ...view, client }
}

beforeEach(() => {
  mockDetailApis()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('顶栏给出测试集、需求、迭代、就绪结论与上次运行，运行测试集提交运行配置', async () => {
  const run = vi.spyOn(api, 'runUiTestSuite').mockResolvedValue({ suiteRunId: 'suite-run-2', status: 'running' })
  const { container, client } = renderPage()

  await screen.findByText('UI测试集详情')
  const toolbar = within(container.querySelector('.ui-wb-toolbar') as HTMLElement)
  // 测试集 / 需求 / 迭代跟在标题后面，需求与迭代随各自查询到达
  const title = container.querySelector('.ui-wb-toolbar-title') as HTMLElement
  await waitFor(() => expect(title).toHaveTextContent('xiaoming'))
  await waitFor(() => expect(title).toHaveTextContent('安装部署'))
  // 就绪结论与「上次运行」都取自最近一次测试集运行
  expect(toolbar.getByText('就绪 (Ready)')).toBeInTheDocument()
  expect(await toolbar.findByText(/上次运行/)).toBeInTheDocument()
  expect(toolbar.getByRole('button', { name: /运行记录/ })).toHaveTextContent('运行记录 (1)')

  await userEvent.setup().click(toolbar.getByRole('button', { name: /运行测试集/ }))
  await waitFor(() =>
    expect(run).toHaveBeenCalledWith('suite-1', {
      environmentId: 'env-ui-1',
      headless: false,
      slowMoMs: 300,
      viewportWidth: 1440,
      viewportHeight: 900,
      defaultStepTimeoutMs: 5000,
    }),
  )
  client.clear()
})

it('运行结束后自动补取最终报告，报告明细正常显示', async () => {
  let status = 'running'
  const summary = () => ({ suiteRunId: 'suite-run-2', suiteId: 'suite-1', status, totalCount: 1, successCount: status === 'success' ? 1 : 0 })
  vi.spyOn(api, 'runUiTestSuite').mockImplementation(async () => summary())
  vi.spyOn(api, 'getUiTestSuiteRun').mockImplementation(async () => summary())
  const report = vi.spyOn(api, 'getUiTestSuiteRunReport').mockImplementation(async () => ({
    ...summary(),
    items: status === 'success' ? [{ caseId: 'case-1', caseName: '最终完成用例', status: 'success' }] : [],
  }))
  const { client } = renderPage()
  await screen.findByText('UI测试集详情')
  const runButton = screen.getByRole('button', { name: '运行测试集' })
  await waitFor(() => expect(runButton).toBeEnabled())
  await userEvent.setup().click(runButton)
  await waitFor(() => expect(report).toHaveBeenCalled())
  status = 'success'
  client.setQueryData(['uiTestSuiteRun', 'suite-run-2'], summary())
  await screen.findByText('最终完成用例')
  expect(report.mock.calls.length).toBeGreaterThanOrEqual(2)
  client.clear()
})

it('关闭运行中的报告后摘要继续更新，结束时顶栏就绪且不下载关闭的报告', async () => {
  const running = { suiteRunId: 'suite-run-2', suiteId: 'suite-1', status: 'running', createdAt: new Date().toISOString() }
  vi.spyOn(api, 'runUiTestSuite').mockResolvedValue(running)
  vi.spyOn(api, 'getUiTestSuiteRun').mockResolvedValue(running)
  const report = vi.spyOn(api, 'getUiTestSuiteRunReport').mockResolvedValue({ ...running, items: [] })
  const { container, client } = renderPage()
  await screen.findByText('UI测试集详情')
  const user = userEvent.setup()
  const runButton = screen.getByRole('button', { name: '运行测试集' })
  await waitFor(() => expect(runButton).toBeEnabled())
  await user.click(runButton)
  await waitFor(() => expect(report).toHaveBeenCalled())
  await user.click(screen.getByRole('button', { name: 'Close' }))
  const callsAfterClose = report.mock.calls.length
  client.setQueryData(['uiTestSuiteRun', 'suite-run-2'], { ...running, status: 'success', totalCount: 1, successCount: 1 })
  const toolbar = within(container.querySelector('.ui-wb-toolbar') as HTMLElement)
  await toolbar.findByText('就绪 (Ready)')
  expect(report.mock.calls.length).toBe(callsAfterClose)
  client.clear()
})

it('控制条与两栏工作区按设计稿结构渲染，步骤行上带运行结论徽标', async () => {
  const { container, client } = renderPage()

  await screen.findByText('UI测试集详情')
  // 控制条：用例下拉 + 计数 + 视图切换 + 运行环境
  const ribbon = within(container.querySelector('.ui-wb-ribbon') as HTMLElement)
  expect(ribbon.getByText('选择用例')).toBeInTheDocument()
  expect(ribbon.getByText('2 个用例')).toBeInTheDocument()
  expect(ribbon.getByText(/可视模式 · 1440 x 900/)).toBeInTheDocument()
  // 工作区只有「左步骤编排 + 右回放与控制台」一种排布，没有视图切换
  expect(container.querySelector('.ui-wb-ribbon-views')).toBeNull()

  // 左栏：用例信息条 + 步骤编辑器
  await waitFor(() => expect(screen.getByLabelText('用例名称')).toHaveValue('登录成功-跳转工作台'))
  expect(container.querySelector('.ui-wb-case-serial')).toHaveTextContent('CASE-01')
  const caseMeta = within(container.querySelector('.ui-wb-case-meta') as HTMLElement)
  expect(caseMeta.getByText('包含 2 个步骤')).toBeInTheDocument()
  const pipeline = within(container.querySelector('.ui-wb-pipeline') as HTMLElement)
  expect(pipeline.getByText('步骤编辑器')).toBeInTheDocument()
  // 还没有运行记录时步骤行不编造结论
  expect(container.querySelector('.ui-wb-step-status')).toBeNull()

  // 右栏三张卡片同时在位
  expect(container.querySelector('.ui-wb-replay')).toBeTruthy()
  expect(container.querySelector('.ui-wb-strip')).toBeTruthy()
  expect(container.querySelector('.ui-wb-console')).toBeTruthy()
  client.clear()
})

it('切换当前用例走控制条的前后按钮与用例顺序弹层', async () => {
  const { client } = renderPage()

  await waitFor(() => expect(screen.getByLabelText('用例名称')).toHaveValue('登录成功-跳转工作台'))

  await userEvent.setup().click(screen.getByLabelText('后一个用例'))
  await waitFor(() => expect(screen.getByLabelText('用例名称')).toHaveValue('登录失败-密码为空'))
  // 顺序弹层里保留重排与删除入口
  await userEvent.setup().click(screen.getByRole('button', { name: /用例顺序/ }))
  const panel = await waitFor(() => {
    const node = document.querySelector('.ui-wb-order-panel')
    expect(node).toBeTruthy()
    return within(node as HTMLElement)
  })
  expect(panel.getByText('拖拽调整执行顺序')).toBeInTheDocument()
  expect(panel.getAllByLabelText('删除 UI测试用例')).toHaveLength(2)
  // 选中的那一条是当前用例
  expect(panel.getByText('登录失败-密码为空')).toBeInTheDocument()
  // 弹层挂在 body 下，不在 render 的 container 里
  expect(document.querySelector('.ui-wb-order-item.selected')).toHaveTextContent('登录失败-密码为空')
  client.clear()
})

it('调试运行后右栏给出截图回放、关键帧与控制台日志', async () => {
  vi.spyOn(api, 'debugRunUiTestCase').mockResolvedValue({ runId: 'case-run-1', status: 'success' })
  const { container, client } = renderPage()

  await waitFor(() => expect(screen.getByLabelText('用例名称')).toHaveValue('登录成功-跳转工作台'))
  const toolbar = within(container.querySelector('.ui-wb-toolbar') as HTMLElement)
  await userEvent.setup().click(toolbar.getByRole('button', { name: /调试运行/ }))

  await waitFor(() => expect(container.querySelector('.ui-wb-replay-overlay')).toBeTruthy())
  const replay = within(container.querySelector('.ui-wb-replay') as HTMLElement)
  // 浏览器外壳显示运行时的地址与状态，舞台叠加当前步骤
  expect(replay.getByText('http://localhost:5173/dashboard')).toBeInTheDocument()
  expect(replay.getByText('AUT DONE')).toBeInTheDocument()
  expect(replay.getByText('Step 1: open（打开登录页）')).toBeInTheDocument()
  expect(replay.getByText('1 / 2')).toBeInTheDocument()

  // 关键帧：只有带截图的步骤进入缩略图条，且全部渲染在同一个横向滚动条里
  const strip = within(container.querySelector('.ui-wb-strip') as HTMLElement)
  expect(strip.getByText('2 / 2 步有截图')).toBeInTheDocument()
  expect(container.querySelectorAll('.ui-wb-strip-list > .ui-wb-strip-item')).toHaveLength(2)
  // 关键帧角标是「#序号 + 相对本次运行起点的耗时」
  expect(strip.getByText('#1 0.0s')).toBeInTheDocument()
  expect(strip.getByText('#2 0.3s')).toBeInTheDocument()

  // 控制台：逐步骤日志 + 汇总结论 + 真实指标
  const consoleCard = within(container.querySelector('.ui-wb-console') as HTMLElement)
  expect(consoleCard.getByText('open("打开登录页")')).toBeInTheDocument()
  expect(consoleCard.getByText(/成功 · 312ms/)).toBeInTheDocument()
  expect(consoleCard.getByText(/元素未找到/)).toBeInTheDocument()
  expect(consoleCard.getByText(/测试用例执行完成，共 2 步，通过 1 步，失败 1 步，总耗时 1840 ms/)).toBeInTheDocument()
  expect(consoleCard.getByText('运行耗时').parentElement).toHaveTextContent('1840 ms')
  expect(consoleCard.getByText('失败步骤').parentElement).toHaveTextContent('1')

  // 过滤按日志级别走，汇总行始终保留
  await userEvent.setup().click(consoleCard.getByRole('button', { name: /过滤/ }))
  await userEvent.setup().click(await screen.findByRole('menuitem', { name: 'error' }))
  await waitFor(() => expect(consoleCard.queryByText('open("打开登录页")')).toBeNull())
  expect(consoleCard.getByText('input("输入用户名")')).toBeInTheDocument()
  expect(consoleCard.getByText(/测试用例执行完成/)).toBeInTheDocument()

  // 运行变量汇总：私密值打码，写回记录展示旧值→新值
  await userEvent.setup().click(consoleCard.getByRole('button', { name: /运行变量/ }))
  expect(await consoleCard.findByText('username')).toBeInTheDocument()
  expect(consoleCard.getByText('********')).toBeInTheDocument()
  expect(consoleCard.getByText('20 → 31')).toBeInTheDocument()
  client.clear()
})

it('运行前缺变量时弹窗内联补齐，保存后自动重新提交运行', async () => {
  const error = new ApiError('运行前缺少变量', 3008, 400, {
    missingVariables: [
      { caseId: 'case-1', caseName: '登录成功-跳转工作台', stepName: '输入用户名', field: 'operationValue', name: 'username', kind: 'environment' },
      { caseId: 'case-1', caseName: '登录成功-跳转工作台', stepName: '输入用户名', field: 'operationValue', name: 'password', kind: 'environment' },
    ],
  })
  const run = vi
    .spyOn(api, 'runUiTestSuite')
    .mockRejectedValueOnce(error)
    .mockResolvedValue({ suiteRunId: 'suite-run-2', status: 'running' })
  const createVar = vi
    .spyOn(api, 'createApiEnvironmentVar')
    .mockResolvedValue({ varKey: 'username', value: 'admin' })
  const { client } = renderPage()

  await screen.findByText('UI测试集详情')
  const runButton = screen.getByRole('button', { name: '运行测试集' })
  await waitFor(() => expect(runButton).toBeEnabled())
  await userEvent.setup().click(runButton)

  // 一次列全缺失的变量，而不是逐个报错
  await screen.findByText('运行前缺少变量')
  const modal = within(document.querySelector('.ant-modal') as HTMLElement)
  expect(modal.getByText('username')).toBeInTheDocument()
  expect(modal.getByText('password')).toBeInTheDocument()

  const user = userEvent.setup()
  await user.type(modal.getByPlaceholderText('请输入 username 的值'), 'admin')
  await user.type(modal.getByPlaceholderText('请输入 password 的值'), 'secret')
  await user.click(modal.getByRole('button', { name: '保存并重新运行' }))

  await waitFor(() =>
    expect(createVar).toHaveBeenCalledWith('env-ui-1', { varKey: 'username', value: 'admin' }),
  )
  expect(createVar).toHaveBeenCalledWith('env-ui-1', { varKey: 'password', value: 'secret' })
  await waitFor(() => expect(run).toHaveBeenCalledTimes(2))
  client.clear()
})

it('从插入动态值弹窗把环境变量插入当前输入框', async () => {
  const { container, client } = renderPage()

  await waitFor(() => expect(screen.getByLabelText('用例名称')).toHaveValue('登录成功-跳转工作台'))
  const cards = container.querySelectorAll('.ui-test-case-step-card')
  const stepCard = cards[1] as HTMLElement
  const user = userEvent.setup()
  await user.click(within(stepCard).getByRole('button', { name: '展开步骤' }))

  // 定位值在前、操作值在后；这里插入到「输入用户名」的输入值。
  const insertButtons = within(stepCard).getAllByRole('button', { name: /插入变量/ })
  expect(insertButtons).toHaveLength(2)
  await user.click(insertButtons[1])

  const modal = within(await waitFor(() => {
    const node = document.querySelector('.api-env-var-picker-modal')
    expect(node).toBeTruthy()
    return node as HTMLElement
  }))
  expect(modal.getByText('插入动态值')).toBeInTheDocument()
  // 环境变量来自当前选中的 UI 环境，列表默认选中第一个
  expect((await modal.findAllByText('baseUrl')).length).toBeGreaterThan(0)
  expect(modal.getByText('userId')).toBeInTheDocument()
  await user.click(modal.getByRole('button', { name: /token/ }))
  expect(modal.getByText('{{token}}')).toBeInTheDocument()

  await user.click(modal.getByRole('button', { name: '插入变量' }))
  await waitFor(() => expect(within(stepCard).getByDisplayValue(/\{\{token\}\}/)).toBeInTheDocument())
  client.clear()
})
