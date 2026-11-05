import { UiTestSuiteCasePage } from '@/features/ui-automation/pages/UiTestSuiteCasePage'
import * as debugStream from '@/domain/runs/startDebugStream'
import { api, ApiError } from '@/services/api'
import { TestThemeProvider as ThemeProvider } from '@/test/TestThemeProvider'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

// 进入用例改由测试集流程画布上的卡片完成；点击卡片即进入该用例的步骤画布。
// React Flow 的拖拽层在 jsdom 下没有可用的 document，用 click 事件避免触发 d3-drag。
async function openCase(name: string) {
  const user = userEvent.setup()
  await waitFor(() => {
    const canvas = document.querySelector('.ui-flow-canvas')
    expect(canvas).toBeTruthy()
    expect(within(canvas as HTMLElement).getByText(name)).toBeInTheDocument()
  })
  // 用例查询返回后流程图会按 key 重建，重新取当前画布再点击。
  fireEvent.click(within(document.querySelector('.ui-flow-canvas') as HTMLElement).getByText(name))
  await waitFor(() => expect(screen.getByLabelText('用例名称')).toHaveValue(name))
  return user
}

it('顶栏给出测试集、需求、迭代、就绪结论与上次运行，运行测试集提交运行配置', async () => {
  const run = vi.spyOn(api, 'runUiTestSuite').mockResolvedValue({ suiteRunId: 'suite-run-2', status: 'running' })
  const { container, client } = renderPage()

  await screen.findByText('UI测试集详情')
  const toolbar = within(container.querySelector('.ui-wb-toolbar') as HTMLElement)
  // 测试集 / 需求 / 迭代收进同一条面包屑，需求与迭代随各自查询到达
  const crumbs = container.querySelector('.ui-wb-crumbs') as HTMLElement
  await waitFor(() => expect(crumbs).toHaveTextContent('xiaoming'))
  await waitFor(() => expect(crumbs).toHaveTextContent('安装部署'))
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

it('进入用例直接用列表里的步骤渲染，不再请求详情', async () => {
  const detail = vi.mocked(api.getUiTestCase)
  detail.mockClear()

  const { container } = renderPage()
  await openCase('登录成功-跳转工作台')

  expect(detail).not.toHaveBeenCalled()
  expect(container.querySelector('.ui-flow-loading')).not.toBeInTheDocument()
  expect(screen.queryByText('未找到对应的 UI测试用例')).not.toBeInTheDocument()
})

it('进入步骤很多的用例时只挂载当前步骤的编辑控件', async () => {
  const manySteps = JSON.stringify(Array.from({ length: 32 }, (_, index) => ({
    orderNo: index + 1,
    stepName: `步骤 ${index + 1}`,
    keyword: 'click',
    locatorType: 'css',
    locatorValue: '#submit',
    enabled: true,
  })))
  vi.spyOn(api, 'getUiTestCases').mockResolvedValue(list([
    { caseId: 'case-32', suiteId: 'suite-1', name: '32 步用例', enabled: true, orderNo: 1, stepsJson: manySteps },
  ]))

  const { container } = renderPage()
  await openCase('32 步用例')

  expect(container.querySelectorAll('.ui-test-case-step-card')).toHaveLength(32)
  const editor = container.querySelector('.ui-step-details-body') as HTMLElement
  expect(editor).toBeTruthy()
  // 32 个步骤里只有当前步骤挂载控件，其余步骤只注册字段，保存时仍参与校验。
  expect(editor.querySelectorAll('.ant-select')).toHaveLength(3)
  expect(editor.querySelectorAll('.ant-input')).toHaveLength(3)
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
  // 测试集流程画布：用例卡片 + 末尾添加用例卡片，不再有用例管理弹层
  await waitFor(() => expect(container.querySelector('.ui-flow-canvas')).toBeTruthy())
  expect(screen.queryByRole('button', { name: '用例管理' })).not.toBeInTheDocument()
  expect(screen.getByText('添加用例')).toBeInTheDocument()
  expect(screen.getByText('登录成功-跳转工作台')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '删除连线' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '还原连线' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '应用顺序' })).not.toBeInTheDocument()
  expect(within(container.querySelector('.ui-wb-toolbar') as HTMLElement).getByRole('button', { name: /保存/ })).toBeEnabled()
  expect(within(container.querySelector('.ui-wb-toolbar') as HTMLElement).getByRole('button', { name: /导入用例/ })).toBeEnabled()
  // 工作区只有「左步骤编排 + 右回放与控制台」一种排布，没有视图切换
  expect(container.querySelector('.ui-wb-ribbon-views')).toBeNull()

  // 外层用例卡片承载管理动作：删除在卡片菜单里，不进入步骤页
  const caseCanvas = await waitFor(() => container.querySelector('.ui-flow-canvas') as HTMLElement)
  const caseActions = await within(caseCanvas).findByRole('button', { name: '登录成功-跳转工作台 更多操作' })
  fireEvent.click(caseActions)
  expect(await screen.findByText('删除用例')).toBeInTheDocument()
  expect(screen.getByText('打开用例')).toBeInTheDocument()
  fireEvent.click(caseActions)

  // 左栏：用例信息并入顶栏面包屑 + 步骤编辑器
  await openCase('登录成功-跳转工作台')
  const pageToolbar = within(container.querySelector('.ui-wb-toolbar') as HTMLElement)
  const crumbs = within(container.querySelector('.ui-wb-crumbs') as HTMLElement)
  // 测试集名就是返回测试集流程的入口，不再单独占一个“测试集流程”层级
  expect(crumbs.getByRole('button', { name: /测试集流程/ })).toHaveTextContent('xiaoming')
  expect(crumbs.queryByText('步骤流程')).not.toBeInTheDocument()
  expect(container.querySelector('.ui-wb-crumb-case')).toHaveAttribute('aria-current', 'page')
  await waitFor(() => expect(container.querySelector('.ui-wb-case-meta')).toBeTruthy())
  expect(container.querySelector('.ui-wb-case-serial')).toHaveTextContent('CASE-01')
  expect(pageToolbar.getByRole('button', { name: /调试运行/ })).toBeInTheDocument()
  // 测试集级动作（运行记录 / 导入用例 / 运行测试集）都留在测试集流程
  expect(pageToolbar.queryByRole('button', { name: /运行记录/ })).not.toBeInTheDocument()
  expect(pageToolbar.queryByRole('button', { name: /导入用例/ })).not.toBeInTheDocument()
  expect(pageToolbar.queryByRole('button', { name: /运行测试集/ })).not.toBeInTheDocument()
  const caseMeta = within(container.querySelector('.ui-wb-case-meta') as HTMLElement)
  expect(caseMeta.getByText('2 个步骤')).toBeInTheDocument()
  expect(caseMeta.getByRole('switch', { name: '启用当前用例' })).toBeChecked()
  expect(caseMeta.queryByRole('button', { name: /更多操作/ })).not.toBeInTheDocument()
  expect(caseMeta.queryByRole('button', { name: '用例导入' })).not.toBeInTheDocument()
  expect(caseMeta.queryByRole('button', { name: '删除用例' })).not.toBeInTheDocument()
  // 用例信息与测试集动作同处一行，不再有第二条用例工具栏
  expect(container.querySelector('.ui-flow-case-toolbar')).toBeNull()
  const pipelineElement = container.querySelector('.ui-inspector-step-host .ui-wb-pipeline') as HTMLElement
  expect(pipelineElement).toBeVisible()
  expect(container.querySelector('.ui-flow-editor .ui-wb-pipeline')).toBeNull()
  const pipeline = within(pipelineElement)
  expect(pipeline.getByText('步骤配置')).toBeInTheDocument()
  // 还没有运行记录时步骤行不编造结论
  expect(container.querySelector('.ui-wb-step-status')).toBeNull()

  // 回放、快照和控制台位于同一面板中
  expect(container.querySelector('.ui-wb-inspector.ui-wb-inspector-unified')).toBeTruthy()
  // 右栏功能同时在位
  expect(container.querySelector('.ui-wb-replay')).toBeTruthy()
  expect(container.querySelector('.ui-wb-strip')).toBeNull()
  expect(screen.getByRole('tab', { name: '运行变量' })).toBeInTheDocument()
  expect(container.querySelector('.ui-wb-console')).toBeTruthy()
  client.clear()
})

it('步骤流程隐藏测试集级动作，回到测试集流程后恢复', async () => {
  const { container, client } = renderPage()
  const user = await openCase('登录成功-跳转工作台')
  const toolbar = () => within(container.querySelector('.ui-wb-toolbar') as HTMLElement)

  expect(toolbar().queryByRole('button', { name: /运行记录/ })).not.toBeInTheDocument()
  expect(toolbar().queryByRole('button', { name: /导入用例/ })).not.toBeInTheDocument()
  expect(toolbar().queryByRole('button', { name: /运行测试集/ })).not.toBeInTheDocument()
  expect(toolbar().getByRole('button', { name: /调试运行/ })).toBeInTheDocument()

  await user.click(toolbar().getByRole('button', { name: /测试集流程/ }))
  await waitFor(() => expect(toolbar().getByRole('button', { name: /运行测试集/ })).toBeInTheDocument())
  expect(toolbar().getByRole('button', { name: /运行记录/ })).toBeInTheDocument()
  expect(toolbar().getByRole('button', { name: /导入用例/ })).toBeInTheDocument()
  expect(toolbar().queryByRole('button', { name: /调试运行/ })).not.toBeInTheDocument()
  client.clear()
})

it('顶栏面包屑内直接切换当前用例的启用状态', async () => {
  const { container, client } = renderPage()
  const user = await openCase('登录成功-跳转工作台')
  const enabledSwitch = screen.getByRole('switch', { name: '启用当前用例' })

  expect(enabledSwitch).toBeChecked()
  await user.click(enabledSwitch)
  expect(enabledSwitch).not.toBeChecked()
  expect(screen.getByText('已停用')).toBeInTheDocument()

  await user.click(enabledSwitch)
  expect(enabledSwitch).toBeChecked()
  expect(container.querySelector('.ui-wb-case-status')).toHaveTextContent('● 已启用')
  client.clear()
})

it('编辑用例后保存按钮高亮，保存成功后恢复', async () => {
  const save = vi.spyOn(api, 'updateUiTestCase').mockResolvedValue(cases[0])
  const { container, client } = renderPage()
  const user = await openCase('登录成功-跳转工作台')
  const toolbar = within(container.querySelector('.ui-wb-toolbar') as HTMLElement)
  const saveButton = toolbar.getByRole('button', { name: /保存/ })

  expect(saveButton).not.toHaveClass('is-dirty')
  const nameInput = screen.getByLabelText('用例名称')
  await user.clear(nameInput)
  await user.type(nameInput, '登录成功-跳转工作台改')
  expect(saveButton).toHaveClass('is-dirty')
  expect(toolbar.getByText('未保存')).toBeInTheDocument()

  await user.click(saveButton)
  await waitFor(() => expect(save).toHaveBeenCalled())
  await waitFor(() => expect(saveButton).not.toHaveClass('is-dirty'))
  expect(toolbar.queryByText('未保存')).not.toBeInTheDocument()
  client.clear()
})

it('用例切换与新建都走测试集流程卡片', async () => {
  const { container, client } = renderPage()

  await waitFor(() => expect(screen.getByText('登录成功-跳转工作台')).toBeInTheDocument())
  const user = await openCase('登录成功-跳转工作台')
  // 返回测试集流程后点击另一张用例卡片即可切换
  await user.click(screen.getByRole('button', { name: /测试集流程/ }))
  const canvas = await waitFor(() => container.querySelector('.ui-flow-canvas') as HTMLElement)
  fireEvent.click(await within(canvas).findByText('登录失败-密码为空'))
  await waitFor(() => expect(screen.getByLabelText('用例名称')).toHaveValue('登录失败-密码为空'))
  expect(screen.getByLabelText('用例名称')).toHaveValue('登录失败-密码为空')

  // 流程末尾的「+ 添加用例」先产生草稿卡片，再进入该用例的步骤画布
  await user.click(screen.getByRole('button', { name: /测试集流程/ }))
  await waitFor(() => expect(container.querySelector('.ui-flow-canvas')).toBeTruthy())
  fireEvent.click(screen.getByText('添加用例'))
  await waitFor(() => expect(screen.getByLabelText('用例名称')).toHaveValue(''))
  expect(screen.getByLabelText('用例名称')).toHaveAttribute('placeholder', '例如：登录成功验证')
  // 返回后草稿卡片仍在测试集流程末尾
  await user.click(screen.getByRole('button', { name: /测试集流程/ }))
  await waitFor(() => expect(screen.getByText('未保存用例')).toBeInTheDocument())
  expect(screen.getByText('0 个步骤 · 未保存草稿')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '用例管理' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /用例顺序/ })).not.toBeInTheDocument()
  client.clear()
})

it('流程末尾的添加步骤卡片追加步骤并在侧栏编辑', async () => {
  const { container, client } = renderPage()
  await openCase('登录成功-跳转工作台')

  fireEvent.click(screen.getByText('添加步骤'))
  await waitFor(() => expect(screen.getByText('#3 / 3')).toBeInTheDocument())
  const caseMeta = within(container.querySelector('.ui-wb-case-meta') as HTMLElement)
  expect(caseMeta.getByText('3 个步骤')).toBeInTheDocument()
  const third = container.querySelector('[data-step-index="2"]') as HTMLElement
  expect(third).toBeVisible()
  expect(third).toHaveClass('is-detail')
  expect(within(third).getByPlaceholderText('点击输入步骤名称')).toHaveValue('')

  // 新用例没有步骤时，末尾仍有添加入口，第一次添加即落到 #1
  fireEvent.click(screen.getByRole('button', { name: /测试集流程/ }))
  await waitFor(() => expect(container.querySelector('.ui-flow-canvas')).toBeTruthy())
  fireEvent.click(screen.getByText('添加用例'))
  await waitFor(() => expect(screen.getByLabelText('用例名称')).toHaveValue(''))
  fireEvent.click(screen.getByText('添加步骤'))
  await waitFor(() => expect(screen.getByText('#1 / 1')).toBeInTheDocument())
  client.clear()
})

it('调试运行后右栏给出截图回放、关键帧与控制台日志', async () => {
  vi.spyOn(debugStream, 'startDebugStream').mockResolvedValue({ initial: caseRun, activate: vi.fn(), abort: vi.fn() })
  const { container, client } = renderPage()

  const user = await openCase('登录成功-跳转工作台')
  const pageToolbar = within(container.querySelector('.ui-wb-toolbar') as HTMLElement)
  await user.click(pageToolbar.getByRole('button', { name: /调试运行/ }))

  await waitFor(() => expect(container.querySelector('.ui-wb-replay-overlay')).toBeTruthy())
  const replay = within(container.querySelector('.ui-wb-replay') as HTMLElement)
  expect(container.querySelector('.ui-wb-replay-canvas')).toHaveStyle({ aspectRatio: '1440 / 900' })
  // 浏览器外壳显示运行时的地址与状态，舞台叠加当前步骤
  expect(replay.getByText('http://localhost:5173/dashboard')).toBeInTheDocument()
  expect(replay.getByText('AUT DONE')).toBeInTheDocument()
  expect(replay.getByText('Step 1: open（打开登录页）')).toBeInTheDocument()
  expect(replay.getByText('1 / 2')).toBeInTheDocument()

  // 回放保留按步骤切换的控制。
  expect(replay.getByRole('button', { name: '跳转到第 2 步 输入用户名' })).toBeInTheDocument()

  await userEvent.click(screen.getByRole('tab', { name: '执行日志' }))
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
  await userEvent.click(screen.getByRole('tab', { name: '运行变量' }))
  const variables = within(container.querySelector('.ui-wb-run-variables') as HTMLElement)
  expect(await variables.findByText('username')).toBeInTheDocument()
  expect(variables.getByText('********')).toBeInTheDocument()
  expect(variables.getByText('20 → 31')).toBeInTheDocument()
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

  const user = await openCase('登录成功-跳转工作台')
  await user.click(screen.getByRole('button', { name: '下一个步骤' }))
  const cards = container.querySelectorAll('.ui-test-case-step-card')
  const stepCard = cards[1] as HTMLElement
  expect(stepCard).toBeVisible()

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

it('快速完成的 UI 调试直接展示实时推送的步骤结果', async () => {
  vi.spyOn(debugStream, 'startDebugStream').mockImplementation(async (_kind, _case, _body, onEvent) => ({
    initial: { runId: 'case-run-live', status: 'pending' },
    abort: vi.fn(),
    activate: () => onEvent({ type: 'finished', data: { ...caseRun, runId: 'case-run-live' } }),
  }))
  const { container, client } = renderPage()
  vi.spyOn(api, 'getUiTestCaseRun').mockRejectedValue(new Error('record already removed'))
  const user = await openCase('登录成功-跳转工作台')
  const pageToolbar = within(container.querySelector('.ui-wb-toolbar') as HTMLElement)
  await user.click(pageToolbar.getByRole('button', { name: /调试运行/ }))
  await waitFor(() => expect(container.querySelector('.ui-wb-replay-overlay')).toHaveTextContent('打开登录页'))
  client.clear()
})

it('最终调试结果不会被较早发出的查询覆盖', async () => {
  let emit!: (event: { type: string; data: unknown }) => void
  let resolveQuery!: (value: { runId: string; status: 'running' }) => void
  const pendingQuery = new Promise<{ runId: string; status: 'running' }>((resolve) => { resolveQuery = resolve })
  vi.spyOn(debugStream, 'startDebugStream').mockImplementation(async (_kind, _case, _body, onEvent) => {
    emit = onEvent
    return { initial: { runId: 'case-run-live', status: 'pending' }, abort: vi.fn(), activate: vi.fn() }
  })
  const getRun = vi.spyOn(api, 'getUiTestCaseRun').mockReturnValue(pendingQuery)
  const { container, client } = renderPage()
  const user = await openCase('登录成功-跳转工作台')
  const pageToolbar = within(container.querySelector('.ui-wb-toolbar') as HTMLElement)
  await user.click(pageToolbar.getByRole('button', { name: /调试运行/ }))
  await waitFor(() => expect(getRun).toHaveBeenCalledWith('case-run-live', expect.any(AbortSignal)))

  act(() => { emit({ type: 'finished', data: { ...caseRun, runId: 'case-run-live' } }) })
  await waitFor(() => expect(client.getQueryData<{ status: string }>(['uiTestCaseRun', 'case-run-live'])?.status).toBe('success'))
  await act(async () => { resolveQuery({ runId: 'case-run-live', status: 'running' }); await pendingQuery })
  expect(client.getQueryData<{ status: string }>(['uiTestCaseRun', 'case-run-live'])?.status).toBe('success')
  client.clear()
})

it('截图接收期间先显示执行结果，旧查询不会覆盖该状态', async () => {
  let emit!: (event: { type: string; data: unknown }) => void
  let resolveQuery!: (value: { runId: string; status: 'running' }) => void
  const pendingQuery = new Promise<{ runId: string; status: 'running' }>((resolve) => { resolveQuery = resolve })
  vi.spyOn(debugStream, 'startDebugStream').mockImplementation(async (_kind, _case, _body, onEvent) => {
    emit = onEvent
    return { initial: { runId: 'case-run-live', status: 'pending' }, abort: vi.fn(), activate: vi.fn() }
  })
  vi.spyOn(api, 'getUiTestCaseRun').mockReturnValue(pendingQuery)
  const { container, client } = renderPage()
  const user = await openCase('登录成功-跳转工作台')
  await user.click(within(container.querySelector('.ui-wb-toolbar') as HTMLElement).getByRole('button', { name: /调试运行/ }))
  act(() => { emit({ type: 'execution_finished', data: { status: 'success' } }) })
  await userEvent.click(screen.getByRole('tab', { name: '执行日志' }))
  await waitFor(() => expect(screen.getByText('执行已结束，正在接收截图等临时产物')).toBeInTheDocument())
  await act(async () => { resolveQuery({ runId: 'case-run-live', status: 'running' }); await pendingQuery })
  expect(client.getQueryData<{ status: string }>(['uiTestCaseRun', 'case-run-live'])?.status).toBe('success')
  act(() => { emit({ type: 'finished', data: { ...caseRun, runId: 'case-run-live' } }) })
  await waitFor(() => expect(screen.queryByText('执行已结束，正在接收截图等临时产物')).not.toBeInTheDocument())
  client.clear()
})

it('底部切换步骤时保留其他步骤的修改并一起保存', async () => {
  const save = vi.spyOn(api, 'updateUiTestCase').mockResolvedValue(cases[0])
  const { container, client } = renderPage()
  const user = await openCase('登录成功-跳转工作台')
  const first = container.querySelector('[data-step-index="0"]') as HTMLElement
  const second = container.querySelector('[data-step-index="1"]') as HTMLElement
  expect(first).toBeVisible()
  expect(container.querySelector('.ui-step-details-body .ui-test-case-step-add-row')).not.toBeInTheDocument()
  expect(first).toHaveClass('is-detail')
  expect(within(first).queryByRole('button', { name: '折叠步骤' })).not.toBeInTheDocument()
  expect(first.querySelector('.ui-test-case-step-body')).toBeVisible()
  expect(second).not.toBeVisible()
  await user.click(screen.getByRole('switch', { name: '失败后继续' }))
  await user.click(within(first).getByRole('tab', { name: '后置提取' }))
  expect(within(first).getByText('当前没有提取规则')).toBeVisible()
  await user.click(within(first).getByRole('tab', { name: '基础配置' }))
  const firstName = within(first).getByPlaceholderText('点击输入步骤名称')
  await user.clear(firstName)
  await user.type(firstName, '新的打开页面步骤')
  expect(screen.queryByRole('button', { name: '折叠步骤配置' })).not.toBeInTheDocument()
  expect(firstName).toHaveValue('新的打开页面步骤')
  await user.click(screen.getByRole('button', { name: '下一个步骤' }))
  expect(first).not.toBeVisible()
  expect(second).toBeVisible()
  expect(screen.getByRole('switch', { name: '失败后继续' })).not.toBeChecked()
  const secondName = within(second).getByPlaceholderText('点击输入步骤名称')
  await user.clear(secondName)
  await user.type(secondName, '新的用户名步骤')
  const pageToolbar = within(container.querySelector('.ui-wb-toolbar') as HTMLElement)
  await user.click(pageToolbar.getByRole('button', { name: /保存/ }))
  await waitFor(() => expect(save).toHaveBeenCalled())
  const payload = save.mock.calls[0][1]
  const savedSteps = JSON.parse(String(payload.stepsJson))
  expect(savedSteps.map((step: { stepName: string }) => step.stepName)).toEqual(['新的打开页面步骤', '新的用户名步骤'])
  expect(savedSteps[0].continueOnFailure).toBe(true)
  expect(savedSteps[1].continueOnFailure).toBe(false)
  client.clear()
})

it('保存时检查未选中步骤，并切换到有错误的步骤', async () => {
  const save = vi.spyOn(api, 'updateUiTestCase').mockResolvedValue(cases[0])
  const { container, client } = renderPage()
  const user = await openCase('登录成功-跳转工作台')
  await user.click(screen.getByRole('button', { name: '下一个步骤' }))
  const second = container.querySelector('[data-step-index="1"]') as HTMLElement
  await user.clear(within(second).getByPlaceholderText('点击输入步骤名称'))
  await user.click(screen.getByRole('button', { name: '上一个步骤' }))
  expect(second).not.toBeVisible()
  await user.click(within(container.querySelector('.ui-wb-toolbar') as HTMLElement).getByRole('button', { name: /保存/ }))
  await waitFor(() => expect(second).toBeVisible())
  expect(within(second).getByText('请输入步骤名称')).toBeInTheDocument()
  expect(save).not.toHaveBeenCalled()
  client.clear()
})
