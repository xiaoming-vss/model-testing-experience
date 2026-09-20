import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '@/app/providers/ThemeProvider'
import { useThemeStore } from '@/shared/store/theme.store'
import analysisFixture from '../__fixtures__/functional-requirement-analysis.json'
import type { FunctionalCaseGenerateTaskRun } from '../types'
import { FunctionalCaseGenerateTaskDetailPage } from './FunctionalCaseGenerateTaskDetailPage'
import { FunctionalCaseRelationsPage } from './FunctionalCaseRelationsPage'

const task = {
  taskId: 'task-1',
  taskType: 'functional_case_generate',
  name: '登录功能用例生成',
  projectId: 'project-1',
  sprintId: 'sprint-1',
  requirementId: 'requirement-1',
  instruction: '生成登录功能用例',
}

const candidateYaml = JSON.stringify({
  cases: [
    {
      case_module: '登录',
      'Case Title': '账号密码登录成功',
      preconditions: '用户已注册',
      steps: '输入账号密码并提交',
      expected_results: '登录成功',
      priority: 'P0',
      case_type: '功能',
    },
  ],
}, null, 2)

const pendingRun: FunctionalCaseGenerateTaskRun = {
  runId: 'run-1',
  taskId: 'task-1',
  projectId: 'project-1',
  requirementId: 'requirement-1',
  status: 'success',
  reviewStatus: 'pending',
  importStatus: 'pending',
  importedTargets: [],
  importedAt: null,
  importMigrationComplete: true,
  resultYaml: candidateYaml,
  createdAt: '2026-08-02T07:00:00.000Z',
}

function jsonResponse(data: unknown, status = 200, message = 'ok') {
  return new Response(JSON.stringify({ code: status < 400 ? 0 : status, message, data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installFetchHandler(
  getRun: () => typeof pendingRun,
  onRequest?: (url: URL, init?: RequestInit) => Response | Promise<Response> | undefined,
) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const requestUrl = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(requestUrl, 'http://localhost')
    if (url.pathname === '/v1/projects/project-1') return jsonResponse({ projectId: 'project-1', name: '测试项目', role: 'owner', permissions: ['read', 'write', 'execute', 'review', 'manage'] })
    const handled = onRequest?.(url, init)
    if (handled) return handled

    if (url.pathname === '/v1/function-case-generate-tasks/task-1') return jsonResponse(task)
    if (url.pathname === '/v1/function-case-generate-tasks/task-1/runs') {
      return jsonResponse({ items: [getRun()], total: 1 })
    }
    if (url.pathname === '/v1/function-case-generate-task-runs/run-1') return jsonResponse(getRun())
    if (url.pathname === '/v1/requirements/requirement-1/function-test-suites') {
      return jsonResponse({
        items: [
          { suiteId: 'suite-login', name: '登录' },
          { suiteId: 'suite-checkout', name: '结算' },
        ],
        total: 2,
      })
    }
    if (url.pathname.includes('/integrations/llm/connections')) return jsonResponse({ items: [{ connectionId: 'mine', name: '本人模型', status: 'active' }], total: 1 })
    return jsonResponse({ items: [], total: 0 })
  })
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  seedOwnerProject(queryClient)

  render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/ai-testing/function-tasks/task-1']}>
          <Routes>
            <Route path="/ai-testing/function-tasks/:taskId" element={<FunctionalCaseGenerateTaskDetailPage />} />
            <Route path="/ai-testing/function-tasks/:taskId/runs/:runId/graph" element={<FunctionalCaseRelationsPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  )
  return queryClient
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useThemeStore.setState({ mode: 'light' })
})

// 行内的「查看结果/审核/审核候选结果」直接点按钮；「更多」下拉只放状态变更类操作。
async function findRunRow(runId: string) {
  const idCell = await screen.findByText(runId.slice(0, 8))
  const row = idCell.closest('tr')
  if (!row) throw new Error(`未找到运行记录行：${runId}`)
  return row
}

async function clickRunInlineAction(user: ReturnType<typeof userEvent.setup>, runId: string, name: string) {
  const row = await findRunRow(runId)
  // 行内按钮依赖异步加载的运行详情，需等待按钮出现；antd 会在两个汉字间插入空格。
  await user.click(await within(row).findByRole('button', { name: buttonNamePattern(name) }))
}

function buttonNamePattern(name: string) {
  return new RegExp(`^${name.split('').join('\\s*')}$`)
}

async function openRunActionsMenu(user: ReturnType<typeof userEvent.setup>, runId: string) {
  const row = await findRunRow(runId)
  await user.click(await within(row).findByRole('button', { name: '更多操作' }))
}

describe('功能候选结果审核与正式资产导入', () => {
  it.each([false, true])('非选中运行详情加载完成前禁止确认导入，支持加载失败重试（失败：%s）', async (failFirst) => {
    const targetRun = { ...pendingRun, runId: 'run-2', reviewStatus: 'approved', createdAt: '2026-08-01T07:00:00.000Z' }
    let resolveDetails!: (response: Response) => void
    const details = new Promise<Response>((resolve) => { resolveDetails = resolve })
    let detailRequests = 0
    let importedRun: string | undefined
    installFetchHandler(() => pendingRun, (url, init) => {
      if (url.pathname.endsWith('/task-1/runs')) return jsonResponse({ items: [pendingRun, targetRun], total: 2 })
      if (url.pathname === '/v1/function-case-generate-task-runs/run-2') {
        detailRequests += 1
        return detailRequests === 1 ? details : jsonResponse(targetRun)
      }
      if (url.pathname.endsWith('/import') && init?.method === 'POST') {
        importedRun = url.pathname
        return jsonResponse({ ...targetRun, importStatus: 'imported' })
      }
    })
    const user = userEvent.setup()
    renderPage()
    await openRunActionsMenu(user, 'run-2')
    await user.click(await screen.findByRole('menuitem', { name: '导入正式用例' }))
    const checkbox = screen.getByRole('checkbox', { name: '我已确认结果，确定导入正式用例' })
    expect(checkbox).toBeDisabled()
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled()
    expect(screen.getByText('正在加载待导入结果…')).toBeInTheDocument()
    expect(importedRun).toBeUndefined()
    await act(async () => { resolveDetails(failFirst ? jsonResponse(null, 500, '详情加载失败') : jsonResponse(targetRun)) })
    if (failFirst) {
      expect(await screen.findByText('详情加载失败')).toBeInTheDocument()
      expect(checkbox).toBeDisabled()
      expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled()
      await user.click(screen.getByRole('button', { name: '重新加载结果' }))
    }
    await waitFor(() => expect(checkbox).toBeEnabled())
    expect(screen.getByRole('dialog')).toHaveTextContent(/1\s*条用例/)
    await user.click(checkbox)
    await user.click(screen.getByRole('button', { name: '确认导入' }))
    await waitFor(() => expect(importedRun).toBe('/v1/function-case-generate-task-runs/run-2/import'))
  })

  it('类型筛选只展示匹配用例，并更新分组数量和结果范围', async () => {
    installFetchHandler(() => ({ ...pendingRun, resultYaml: JSON.stringify({ cases: [
      { case_module: '登录', 'Case Title': '正常流程', case_type: '功能' },
      { case_module: '登录', 'Case Title': '异常流程', case_type: '异常' },
    ] }) }))
    const user = userEvent.setup()
    renderPage()
    await clickRunInlineAction(user, 'run-1', '审核候选结果')
    await user.click(screen.getByRole('button', { name: '异常 1' }))
    expect(screen.queryByText('正常流程')).not.toBeInTheDocument()
    expect(screen.getByText('异常流程')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录 1' })).toBeInTheDocument()
    expect(screen.getByText('第 1–1 条，共 1 条')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '全部 2' }))
    expect(screen.getByText('正常流程')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: '搜索模块或场景' }), '正常')
    expect(screen.queryByText('异常流程')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '异常 1' }))
    expect(screen.queryByText('正常流程')).not.toBeInTheDocument()
    expect(screen.getByText('没有匹配的用例分组')).toBeInTheDocument()
  })

  it('类型按钮根据实际用例类型生成，不根据标题推测分类', async () => {
    installFetchHandler(() => ({ ...pendingRun, resultYaml: JSON.stringify({ cases: [
      { case_module: '登录', 'Case Title': '异常输入下的响应时间', case_type: '性能测试' },
      { case_module: '登录', 'Case Title': '键盘操作', case_type: '可访问性测试' },
    ] }) }))
    const user = userEvent.setup()
    renderPage()
    await clickRunInlineAction(user, 'run-1', '审核候选结果')
    expect(screen.getByRole('button', { name: '性能测试 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '可访问性测试 1' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^功能 / })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '性能测试 1' }))
    expect(screen.queryByText('键盘操作')).not.toBeInTheDocument()
    expect(screen.getByText('异常输入下的响应时间')).toBeInTheDocument()
  })

  it('用例编号标签展示 UUID 前缀并保留完整值，缺失时不产生空标签', async () => {
    const caseId = '9f1c2e4a-5b6d-4c7e-8f90-1a2b3c4d5e6f'
    installFetchHandler(() => ({ ...pendingRun, resultYaml: JSON.stringify({ cases: [
      { case_id: caseId, case_module: '登录', 'Case Title': '正常流程', case_type: '功能' },
      { case_module: '登录', 'Case Title': '异常流程', case_type: '功能' },
    ] }) }))
    const user = userEvent.setup()
    renderPage()
    await clickRunInlineAction(user, 'run-1', '审核候选结果')
    const cards = screen.getAllByRole('article')
    expect(within(cards[0]).getByText('9f1c2e4a…')).toHaveAttribute('title', caseId)
    expect(within(cards[1]).queryByText('9f1c2e4a…')).not.toBeInTheDocument()
    expect(within(cards[1]).getByText('异常流程')).toBeInTheDocument()
  })

  it('暗色主题下树图节点使用高对比度配色', async () => {
    useThemeStore.setState({ mode: 'dark' })
    const currentRun: FunctionalCaseGenerateTaskRun = {
      ...pendingRun,
      configJson: JSON.stringify({
        caseNames: {
          categories: [
            {
              model: 'EGO 首次接入流程',
              data: [
                {
                  test_model: '功能场景测试',
                  test_points: ['验证手机 App 完成配网'],
                },
              ],
            },
          ],
        },
      }),
    }
    installFetchHandler(() => currentRun)
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '测试点' }))
    await user.click(screen.getByRole('tab', { name: '可视化' }))

    const pointNode = await screen.findByTitle('验证手机 App 完成配网')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(getComputedStyle(pointNode).backgroundColor).toBe('rgba(37, 43, 56, 0.96)')
    expect(getComputedStyle(pointNode).color).toBe('rgb(230, 237, 247)')
  })

  it('暗色主题下候选审核弹窗使用统一表面和暗色滚动条', async () => {
    useThemeStore.setState({ mode: 'dark' })
    installFetchHandler(() => pendingRun)
    const user = userEvent.setup()
    renderPage()

    await clickRunInlineAction(user, 'run-1', '审核候选结果')
    const dialog = await screen.findByRole('dialog')

    const modalContent = dialog.querySelector<HTMLElement>('.ant-modal-container')
    const modalHeader = dialog.querySelector<HTMLElement>('.ant-modal-header')
    const modalBody = dialog.querySelector<HTMLElement>('.ant-modal-body')
    const modalFooter = dialog.querySelector<HTMLElement>('.ant-modal-footer')

    expect(modalContent).not.toBeNull()
    expect(modalHeader).not.toBeNull()
    expect(modalBody).not.toBeNull()
    expect(modalFooter).not.toBeNull()
    expect(getComputedStyle(modalContent!).backgroundColor).toBe('rgba(22, 27, 38, 0.98)')
    expect(getComputedStyle(modalHeader!).backgroundColor).toBe('rgba(0, 0, 0, 0)')
    expect(getComputedStyle(modalFooter!).backgroundColor).toBe('rgba(0, 0, 0, 0)')
    expect(getComputedStyle(modalBody!).scrollbarColor).toBe('rgba(148, 163, 184, 0.42)')
  })

  it('预览候选使用分组导航和结构化卡片，编辑候选直接展示 JSON', async () => {
    installFetchHandler(() => pendingRun)
    const user = userEvent.setup()
    renderPage()

    await clickRunInlineAction(user, 'run-1', '审核候选结果')

    const moduleItem = await screen.findByRole('button', { name: /登录\s*1/ })
    expect(moduleItem).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('textbox', { name: '搜索模块或场景' })).toBeInTheDocument()
    expect(await screen.findByText('账号密码登录成功')).toBeInTheDocument()
    expect(screen.getByText('前置条件')).toBeInTheDocument()
    expect(screen.getByText('测试步骤')).toBeInTheDocument()
    expect(screen.getByText('预期结果')).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'json' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '卡片' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: '编辑候选' }))

    expect(await screen.findByRole('textbox', { name: '功能候选结果 JSON' })).toBeInTheDocument()
  })

  it.each([false, true])('展示新版需求分析结构（直接返回：%s）', async (direct) => {
    const currentRun: FunctionalCaseGenerateTaskRun = {
      ...pendingRun,
      status: 'waiting_review',
      checkpointEnabled: true,
      currentStage: 'requirement_analysis',
      stageStatus: 'waiting_review',
      configJson: JSON.stringify(direct ? analysisFixture : { requirementAnalysis: analysisFixture }),
    }
    installFetchHandler(() => currentRun)
    const user = userEvent.setup()
    renderPage()
    await clickRunInlineAction(user, 'run-1', '审核')
    await user.click(screen.getByRole('tab', { name: '可视化' }))
    for (const title of ['功能概览', '业务规则', '场景因素', '场景拆解', '待确认项']) {
      await user.click(screen.getByRole('button', { name: new RegExp(title) }))
    }
    expect(screen.getByText(analysisFixture.functionalOverview.purpose)).toBeInTheDocument()
    expect(screen.getByText(analysisFixture.businessRules[0].name)).toBeInTheDocument()
    expect(screen.getByText(analysisFixture.scenarioFactors[0].clarificationNeeded)).toBeInTheDocument()
    expect(screen.getByText(analysisFixture.scenarioBreakdown[0].verificationObjective)).toBeInTheDocument()
    expect(screen.getByText(analysisFixture.openQuestions[0].question)).toBeInTheDocument()
    expect(screen.getAllByText('可生成测试点')).toHaveLength(6)
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
  })

  it('历史预览展示阻塞场景及未明确字段', async () => {
    installFetchHandler(() => ({
      ...pendingRun,
      configJson: JSON.stringify({ requirementAnalysis: {
        scenarioBreakdown: [{
          scenarioId: 'S01', conditions: [], verificationObjective: '验证解绑失败处理',
          readyForTestPointGeneration: false, blockingReason: '失败反馈未明确',
          relatedRuleIds: ['R01'], relatedQuestionIds: ['Q01'],
        }],
      } }),
    }))
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '需求分析' }))
    await user.click(screen.getByRole('tab', { name: '可视化' }))
    await user.click(screen.getByRole('button', { name: /场景拆解/ }))
    expect(screen.getByText('暂不可生成测试点')).toBeInTheDocument()
    expect(screen.getByText('失败反馈未明确')).toBeInTheDocument()
    expect(screen.getByText('R01')).toBeInTheDocument()
    expect(screen.getByText('Q01')).toBeInTheDocument()
    expect(screen.getByText('无')).toBeInTheDocument()
    expect(screen.getAllByText('未明确').length).toBeGreaterThan(0)
  })

  it('按方案测试点分析返回格式展示功能流程和场景设计', async () => {
    const requirementAnalysis = {
      Platform_core_functions: [
        {
          function: 'EGO 设备接入',
          description: '发现、配网并接入本地化 Server',
          business_value: '降低设备接入成本',
        },
      ],
      Target_understanding: [
        {
          target: '验证部署可用性',
          description: '确保本地化 Server 可以稳定接入设备',
        },
      ],
      Risk_point_prediction: [
        {
          risk_area: '设备发现',
          risk_description: '局域网广播可能被网络策略拦截',
          impact: '设备无法自动接入',
        },
      ],
      function_flow: [
        {
          flow_name: 'EGO 首次接入流程',
          description: '手机 App 配网 -> 自动发现本地化 Server -> 自动上报',
        },
      ],
      Scene_Design: [
        {
          scene_type: '功能场景',
          sub_category: [
            {
              scene_type: 'EGO 配网与首次接入',
              description: '覆盖首次接入全流程，关注自动发现、自动上报与状态可观测性',
            },
          ],
        },
      ],
    }
    const currentRun: FunctionalCaseGenerateTaskRun = {
      ...pendingRun,
      status: 'waiting_review',
      checkpointEnabled: true,
      currentStage: 'requirement_analysis',
      stageStatus: 'waiting_review',
      configJson: JSON.stringify({ requirementAnalysis }),
    }
    installFetchHandler(() => currentRun)
    const user = userEvent.setup()
    renderPage()

    await clickRunInlineAction(user, 'run-1', '审核')
    await user.click(screen.getByRole('tab', { name: '可视化' }))

    for (const sectionName of ['平台核心功能', '目标理解', '风险点预测', '功能流程', '场景设计']) {
      expect(screen.getByRole('button', { name: new RegExp(sectionName) })).toHaveAttribute('aria-expanded', 'false')
    }
    expect(screen.queryByText(requirementAnalysis.Platform_core_functions[0].description)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /平台核心功能/ }))
    expect(screen.getByRole('button', { name: /平台核心功能/ })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(requirementAnalysis.Platform_core_functions[0].description)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /功能流程/ }))
    expect(await screen.findByText('流程和依赖链')).toBeInTheDocument()
    expect(screen.getByText(requirementAnalysis.function_flow[0].description)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /场景设计/ }))
    expect(screen.getByText('场景说明')).toBeInTheDocument()
    expect(screen.getByText(requirementAnalysis.Scene_Design[0].sub_category[0].description)).toBeInTheDocument()
    expect(screen.queryByText('来源依据')).not.toBeInTheDocument()
    expect(screen.queryByText('验证重点')).not.toBeInTheDocument()
    expect(screen.queryByText('保护价值/风险')).not.toBeInTheDocument()
  }, 60_000)

  // jsdom 下 antd Table 的整页重渲染明显慢于旧列表，放宽该用例超时。
  it('待审核成功运行可编辑保存，批准不导入并冻结候选', async () => {
    let currentRun: FunctionalCaseGenerateTaskRun = { ...pendingRun }
    let patchBody: unknown
    let reviewBody: unknown
    let importRequests = 0
    const changedYaml = candidateYaml.replace('账号密码登录成功', '账号密码登录并进入首页')
    installFetchHandler(() => currentRun, (url, init) => {
      if (url.pathname === '/v1/function-case-generate-task-runs/run-1/result' && init?.method === 'PATCH') {
        patchBody = JSON.parse(String(init.body))
        currentRun = { ...currentRun, resultYaml: changedYaml }
        return jsonResponse(currentRun)
      }
      if (url.pathname === '/v1/function-case-generate-task-runs/run-1/review' && init?.method === 'POST') {
        reviewBody = JSON.parse(String(init.body))
        currentRun = {
          ...currentRun,
          reviewStatus: 'approved',
          importStatus: 'pending',
          reviewComment: '内容正确',
          reviewedAt: '2026-08-02T08:00:00.000Z',
        }
        return jsonResponse(currentRun)
      }
      if (url.pathname.endsWith('/import')) importRequests += 1
    })
    const user = userEvent.setup()
    renderPage()

    await clickRunInlineAction(user, 'run-1', '审核候选结果')
    await user.click(screen.getByRole('tab', { name: '编辑候选' }))
    const editor = await screen.findByRole('textbox', { name: '功能候选结果 JSON' })
    await user.click(editor)
    await user.keyboard('{Control>}a{/Control}')
    await user.paste(changedYaml)
    await user.click(screen.getByRole('button', { name: '保存候选结果' }))
    await waitFor(() => expect(patchBody).toEqual({ resultYaml: changedYaml }))

    await user.type(screen.getByLabelText('审核备注'), '内容正确')
    await user.click(screen.getByRole('button', { name: /批\s*准/ }))

    await waitFor(() => expect(reviewBody).toEqual({ action: 'approve', reviewComment: '内容正确' }))
    expect(importRequests).toBe(0)
    expect(await screen.findByText('待导入')).toBeInTheDocument()
    expect(document.querySelectorAll('.ai-task-run-pipeline-dot.is-done')).toHaveLength(2)
    await openRunActionsMenu(user, 'run-1')
    expect(await screen.findByRole('menuitem', { name: '导入正式用例' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: '查看结果' }))
    await user.click(screen.getByRole('tab', { name: '编辑候选' }))
    expect(await screen.findByRole('textbox', { name: '功能候选结果 JSON' })).toHaveAttribute('aria-readonly', 'true')
    expect(screen.queryByRole('button', { name: '保存候选结果' })).not.toBeInTheDocument()
  }, 90_000)

  it('拒绝候选结果时要求填写审核备注', async () => {
    let reviewRequests = 0
    installFetchHandler(() => pendingRun, (url) => {
      if (url.pathname === '/v1/function-case-generate-task-runs/run-1/review') reviewRequests += 1
    })
    const user = userEvent.setup()
    renderPage()

    await clickRunInlineAction(user, 'run-1', '审核候选结果')
    await user.click(screen.getByRole('button', { name: /拒\s*绝/ }))

    expect(await screen.findByText('拒绝候选结果时请填写审核备注')).toBeInTheDocument()
    expect(reviewRequests).toBe(0)
  })

  it('无冲突时一次导入并隐藏目标套件标签，且禁止再次导入', async () => {
    let currentRun: FunctionalCaseGenerateTaskRun = { ...pendingRun, reviewStatus: 'approved' }
    const requestBodies: unknown[] = []
    installFetchHandler(() => currentRun, (url, init) => {
      if (url.pathname.endsWith('/import') && init?.method === 'POST') {
        requestBodies.push(JSON.parse(String(init.body)))
        currentRun = {
          ...currentRun,
          importStatus: 'imported',
          importedAt: '2026-08-02T09:00:00.000Z',
          importedTargets: [
            { targetType: 'function_suite', targetId: 'suite-login' },
            { targetType: 'function_suite', targetId: 'suite-checkout' },
          ],
        }
        return jsonResponse({ requiresConfirmation: false, conflicts: [], run: currentRun })
      }
    })
    const user = userEvent.setup()
    renderPage()

    await openRunActionsMenu(user, 'run-1')
    await user.click(await screen.findByRole('menuitem', { name: '导入正式用例' }))
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: '我已确认结果，确定导入正式用例' }))
    await user.click(screen.getByRole('button', { name: '确认导入' }))

    await waitFor(() => expect(requestBodies).toEqual([{ confirmOverwrite: false }]))
    expect(await screen.findByText('已导入')).toBeInTheDocument()
    expect(screen.queryByText('功能套件：登录')).not.toBeInTheDocument()
    expect(screen.queryByText('功能套件：结算')).not.toBeInTheDocument()
    expect(screen.getByText('2026/8/2 17:00:00')).toBeInTheDocument()
    await openRunActionsMenu(user, 'run-1')
    expect(screen.queryByRole('menuitem', { name: '导入正式用例' })).not.toBeInTheDocument()
  })

  it('首次冲突只展示完整新旧字段，取消后仍可重试', async () => {
    const currentRun: FunctionalCaseGenerateTaskRun = { ...pendingRun, reviewStatus: 'approved' }
    const requestBodies: unknown[] = []
    installFetchHandler(() => currentRun, (url, init) => {
      if (url.pathname.endsWith('/import') && init?.method === 'POST') {
        requestBodies.push(JSON.parse(String(init.body)))
        return jsonResponse({
          requiresConfirmation: true,
          conflicts: [{
            normalizedName: '账号密码登录成功',
            existingCase: {
              module: '旧登录模块', title: '旧标题', preconditions: '旧前置', steps: '旧步骤',
              expectedResults: '旧预期', priority: 'P1', caseType: '旧类型',
            },
            generatedCase: {
              module: '新登录模块', title: '新标题', preconditions: '新前置', steps: '新步骤',
              expectedResults: '新预期', priority: 'P0', caseType: '新类型',
            },
          }],
          run: currentRun,
        })
      }
    })
    const user = userEvent.setup()
    renderPage()

    await openRunActionsMenu(user, 'run-1')
    await user.click(await screen.findByRole('menuitem', { name: '导入正式用例' }))
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: '我已确认结果，确定导入正式用例' }))
    await user.click(screen.getByRole('button', { name: '确认导入' }))
    expect(await screen.findByText('旧登录模块')).toBeInTheDocument()
    expect(screen.getByText('新登录模块')).toBeInTheDocument()
    for (const value of ['旧标题', '新标题', '旧前置', '新前置', '旧步骤', '新步骤', '旧预期', '新预期', 'P1', 'P0', '旧类型', '新类型']) {
      expect(screen.getAllByText(value).length).toBeGreaterThan(0)
    }
    expect(screen.getByText('待导入')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '取消覆盖' }))
    expect(requestBodies).toHaveLength(1)
    await openRunActionsMenu(user, 'run-1')
    expect(await screen.findByRole('menuitem', { name: '导入正式用例' })).toBeEnabled()
  })

  it('确认覆盖后再次请求并显示导入成功', async () => {
    let currentRun: FunctionalCaseGenerateTaskRun = { ...pendingRun, reviewStatus: 'approved' }
    const requestBodies: unknown[] = []
    installFetchHandler(() => currentRun, (url, init) => {
      if (url.pathname.endsWith('/import') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as { confirmOverwrite: boolean }
        requestBodies.push(body)
        if (!body.confirmOverwrite) {
          return jsonResponse({
            requiresConfirmation: true,
            conflicts: [{
              normalizedName: 'login',
              existingCase: { module: '登录', title: '旧标题', preconditions: '', steps: '', expectedResults: '', priority: 'P1', caseType: '功能' },
              generatedCase: { module: '登录', title: '新标题', preconditions: '', steps: '', expectedResults: '', priority: 'P0', caseType: '功能' },
            }],
            run: currentRun,
          })
        }
        currentRun = {
          ...currentRun,
          importStatus: 'imported',
          importedAt: '2026-08-02T09:00:00.000Z',
          importedTargets: [{ targetType: 'function_suite', targetId: 'suite-login' }],
        }
        return jsonResponse({ requiresConfirmation: false, conflicts: [], run: currentRun })
      }
    })
    const user = userEvent.setup()
    renderPage()

    await openRunActionsMenu(user, 'run-1')
    await user.click(await screen.findByRole('menuitem', { name: '导入正式用例' }))
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: '我已确认结果，确定导入正式用例' }))
    await user.click(screen.getByRole('button', { name: '确认导入' }))
    await user.click(await screen.findByRole('button', { name: '整批确认覆盖' }))

    await waitFor(() => expect(requestBodies).toEqual([
      { confirmOverwrite: false },
      { confirmOverwrite: true },
    ]))
    expect(await screen.findByText('已导入')).toBeInTheDocument()
    await openRunActionsMenu(user, 'run-1')
    expect(screen.queryByRole('menuitem', { name: '导入正式用例' })).not.toBeInTheDocument()
  })

  it('导入失败后保持审核通过、待导入并允许重试', async () => {
    const currentRun: FunctionalCaseGenerateTaskRun = {
      ...pendingRun,
      reviewStatus: 'approved',
      importStatus: 'pending',
    }
    let attempts = 0
    installFetchHandler(() => currentRun, (url, init) => {
      if (url.pathname.endsWith('/import') && init?.method === 'POST') {
        attempts += 1
        return jsonResponse({}, 500, '正式资产写入失败')
      }
    })
    const user = userEvent.setup()
    renderPage()

    await openRunActionsMenu(user, 'run-1')
    await user.click(await screen.findByRole('menuitem', { name: '导入正式用例' }))
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: '我已确认结果，确定导入正式用例' }))
    await user.click(screen.getByRole('button', { name: '确认导入' }))
    expect(await screen.findByText('正式资产写入失败')).toBeInTheDocument()
    expect(screen.getByText('待导入')).toBeInTheDocument()
    expect(document.querySelectorAll('.ai-task-run-pipeline-dot.is-done')).toHaveLength(2)
    await openRunActionsMenu(user, 'run-1')
    const retryItem = await screen.findByRole('menuitem', { name: '导入正式用例' })
    expect(retryItem).toBeEnabled()
    await user.click(retryItem)
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: '我已确认结果，确定导入正式用例' }))
    await user.click(screen.getByRole('button', { name: '确认导入' }))
    await waitFor(() => expect(attempts).toBe(2))
  })
})

describe('功能测试继续优化', () => {
  it.each(['case_names', 'detailed_cases'])('在 %s 优化时不预填上游需求分析的待确认项', async (stage) => {
    const currentRun: FunctionalCaseGenerateTaskRun = {
      ...pendingRun,
      status: stage === 'case_names' ? 'waiting_review' : 'success',
      checkpointEnabled: true,
      currentStage: stage,
      stageStatus: stage === 'case_names' ? 'waiting_review' : 'success',
      configJson: JSON.stringify({
        requirementAnalysis: { openQuestions: [{ questionId: 'Q01', question: '上游需求分析问题' }] },
        caseNames: { categories: [] },
      }),
    }
    installFetchHandler(() => currentRun)
    const user = userEvent.setup()
    renderPage()
    await clickRunInlineAction(user, 'run-1', stage === 'case_names' ? '审核' : '审核候选结果')
    await user.click(screen.getByRole('button', { name: '继续优化' }))
    expect(screen.getByRole('textbox', { name: '优化指令' })).toHaveValue('')
    expect(screen.queryByRole('button', { name: /Q01.*上游需求分析问题/ })).not.toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: '优化指令' }), '补充异常场景')
    const revisionDialog = screen.getByRole('textbox', { name: '优化指令' }).closest<HTMLElement>('.ant-modal')!
    await user.click(within(revisionDialog).getByRole('button', { name: '取消优化' }))
    await user.click(screen.getByRole('button', { name: '继续优化' }))
    expect(screen.getByRole('textbox', { name: '优化指令' })).toHaveValue('补充异常场景')
  })

  it.each(['requirement_analysis', 'case_names'])('在 %s 当前检查点提交优化并保持当前阶段', async (stage) => {
    const field = stage === 'requirement_analysis' ? 'requirementAnalysis' : 'caseNames'
    const content = stage === 'requirement_analysis' ? { purpose: 'existing' } : { categories: [] }
    let currentRun: FunctionalCaseGenerateTaskRun = {
      ...pendingRun, status: 'waiting_review', checkpointEnabled: true,
      currentStage: stage, stageStatus: 'waiting_review', configJson: JSON.stringify({ [field]: content }),
    }
    let requestBody: unknown
    installFetchHandler(() => currentRun, (url, init) => {
      if (url.pathname.endsWith('/stage-revise')) {
        requestBody = JSON.parse(String(init?.body))
        currentRun = { ...currentRun, status: 'pending', stageStatus: 'pending' }
        return jsonResponse(currentRun)
      }
    })
    const user = userEvent.setup()
    renderPage()
    await clickRunInlineAction(user, 'run-1', '审核')
    await user.click(screen.getByRole('button', { name: '继续优化' }))
    await user.click(screen.getByRole('button', { name: '提交优化' }))
    expect(requestBody).toBeUndefined()
    await user.type(screen.getByRole('textbox', { name: '优化指令' }), '补充异常场景')
    await user.click(screen.getByRole('button', { name: '提交优化' }))
    await waitFor(() => expect(requestBody).toEqual({ stage, llmConnectionId: 'mine', revisionInstruction: '补充异常场景', configJson: { [field]: content } }))
  })

  it('最终结果优化携带未保存编辑，失败保留内容与指令并支持重试', async () => {
    const changed = candidateYaml.replace('账号密码登录成功', '未保存的登录修改')
    let requestBody: unknown
    let requests = 0
    installFetchHandler(() => pendingRun, (url, init) => {
      if (url.pathname.endsWith('/stage-revise')) {
        requests += 1
        requestBody = JSON.parse(String(init?.body))
        return jsonResponse(null, 400, '优化提交失败')
      }
    })
    const user = userEvent.setup()
    renderPage()
    await clickRunInlineAction(user, 'run-1', '审核候选结果')
    await user.click(screen.getByRole('tab', { name: '编辑候选' }))
    const editor = await screen.findByRole('textbox', { name: '功能候选结果 JSON' })
    await user.click(editor)
    await user.keyboard('{Control>}a{/Control}')
    await user.paste(changed)
    await user.click(screen.getByRole('button', { name: '继续优化' }))
    await user.type(screen.getByRole('textbox', { name: '优化指令' }), '补充异常')
    await user.click(screen.getByRole('button', { name: '提交优化' }))
    await waitFor(() => expect(requestBody).toEqual({ stage: 'detailed_cases', llmConnectionId: 'mine', revisionInstruction: '补充异常', resultYaml: changed }))
    expect(screen.getByRole('textbox', { name: '优化指令' })).toHaveValue('补充异常')
    await waitFor(() => expect(screen.getByRole('button', { name: '提交优化' })).not.toHaveClass('ant-btn-loading'))
    await user.click(screen.getByRole('button', { name: '提交优化' }))
    await waitFor(() => expect(requests).toBe(2))
    expect(requestBody).toEqual({ stage: 'detailed_cases', llmConnectionId: 'mine', revisionInstruction: '补充异常', resultYaml: changed })
  }, 60_000)

  it('审核通过的候选结果没有优化入口', async () => {
    installFetchHandler(() => ({ ...pendingRun, reviewStatus: 'approved' }))
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '查看结果' }))
    expect(screen.queryByRole('button', { name: '继续优化' })).not.toBeInTheDocument()
  })
})

it('阶段优化带入未保存的 JSON，并在提交期间禁止重复请求', async () => {
  let currentRun: FunctionalCaseGenerateTaskRun = {
    ...pendingRun, status: 'waiting_review', checkpointEnabled: true,
    currentStage: 'requirement_analysis', stageStatus: 'waiting_review',
    configJson: JSON.stringify({ requirementAnalysis: { purpose: 'old' } }),
  }
  let requests = 0
  let requestBody: unknown
  let finish!: (response: Response) => void
  installFetchHandler(() => currentRun, (url, init) => {
    if (url.pathname.endsWith('/stage-revise')) {
      requests += 1
      requestBody = JSON.parse(String(init?.body))
      return new Promise<Response>((resolve) => { finish = resolve })
    }
  })
  const user = userEvent.setup()
  const queryClient = renderPage()
  await clickRunInlineAction(user, 'run-1', '审核')
  await user.click(screen.getByRole('tab', { name: 'json' }))
  const editor = document.querySelector('.cm-content') as HTMLElement
  await user.click(editor)
  await user.keyboard('{Control>}a{/Control}')
  await user.paste('{"purpose":"unsaved change"}')
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  await user.type(screen.getByRole('textbox', { name: '优化指令' }), '补充边界')
  await user.click(screen.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(requests).toBe(1))
  expect(requestBody).toEqual({ stage: 'requirement_analysis', llmConnectionId: 'mine', revisionInstruction: '补充边界', configJson: { requirementAnalysis: { purpose: 'unsaved change' } } })
  expect(screen.getByRole('textbox', { name: '优化指令' })).toBeDisabled()
  const submit = screen.getByRole('button', { name: /提交优化/ })
  expect(submit).toHaveClass('ant-btn-loading')
  await user.click(submit)
  expect(requests).toBe(1)
  currentRun = { ...currentRun, status: 'pending', stageStatus: 'pending' }
  await act(async () => {
    finish(jsonResponse(currentRun))
  })
  await waitFor(() => expect(queryClient.getMutationCache().getAll().at(-1)?.state.status).toBe('success'), { timeout: 5000 })
  expect(queryClient.getQueryData(['functionalCaseGenerateTaskRun', 'run-1'])).toMatchObject({ status: 'pending' })
  // JSDOM does not finish Ant Design's CSS exit animation.
  const closingInput = screen.queryByRole('textbox', { name: '优化指令' })
  if (closingInput) expect(closingInput.closest('[role="dialog"]')).toHaveClass('ant-zoom-leave')
})

it.each(['failed', 'retrying'])('失败记录阶段状态为 %s 时可重试并提交当前阶段', async (stageStatus) => {
  let body: Record<string, unknown> | undefined
  installFetchHandler(() => ({
    ...pendingRun, status: 'error', stageStatus, checkpointEnabled: true,
    currentStage: 'requirement_analysis',
  }), (url, init) => {
    if (url.pathname.endsWith('/stage-retry')) {
      body = JSON.parse(String(init?.body))
      return jsonResponse({ ...pendingRun, status: 'pending', stageStatus: 'pending' })
    }
  })
  const user = userEvent.setup()
  renderPage()
  await openRunActionsMenu(user, 'run-1')
  await user.click(await screen.findByRole('menuitem', { name: '重试阶段' }))
  await waitFor(() => expect(body).toEqual({ stage: 'requirement_analysis', llmConnectionId: 'mine' }))
})

it.each(['requirement_analysis', 'case_names', 'detailed_cases'])('从 %s 打开的优化输入框位于原弹窗右侧', async (stage) => {
  const final = stage === 'detailed_cases'
  installFetchHandler(() => ({
    ...pendingRun,
    currentStage: stage,
    checkpointEnabled: !final,
    status: final ? 'success' : 'waiting_review',
    stageStatus: final ? 'completed' : 'waiting_review',
    configJson: JSON.stringify({ requirementAnalysis: { purpose: 'analysis' }, caseNames: { categories: [] } }),
  }))
  const user = userEvent.setup()
  renderPage()
  await clickRunInlineAction(user, 'run-1', final ? '审核候选结果' : '审核')
  const reviseButton = screen.getByRole('button', { name: '继续优化' })
  const parentWrap = reviseButton.closest('.ant-modal-wrap')!
  await user.click(reviseButton)
  const input = screen.getByRole('textbox', { name: '优化指令' })
  const revisionWrap = input.closest('.ant-modal-wrap')!
  expect(revisionWrap).toBe(parentWrap)
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  await user.click(input)
  await user.type(input, '补充异常场景')
  expect(input).toHaveValue('补充异常场景')
  expect(input).toHaveFocus()
})

it('优化侧栏预填当前编辑中的待确认项，并保留补充内容', async () => {
  const currentRun: FunctionalCaseGenerateTaskRun = {
    ...pendingRun, status: 'waiting_review', checkpointEnabled: true,
    currentStage: 'requirement_analysis', stageStatus: 'waiting_review',
    configJson: JSON.stringify({ requirementAnalysis: { openQuestions: [{ questionId: 'Q01', question: '旧问题' }] } }),
  }
  let body: Record<string, unknown> | undefined
  installFetchHandler(() => currentRun, (url, init) => {
    if (url.pathname.endsWith('/stage-revise')) {
      body = JSON.parse(String(init?.body))
      return jsonResponse(null, 400, '模拟失败')
    }
  })
  const user = userEvent.setup()
  renderPage()
  await clickRunInlineAction(user, 'run-1', '审核')
  await user.click(screen.getByRole('tab', { name: 'json' }))
  const stageEditor = document.querySelector('.cm-content') as HTMLElement
  await user.click(stageEditor)
  await user.keyboard('{Control>}a{/Control}')
  await user.paste(JSON.stringify({ openQuestions: [
    { questionId: 'Q01', question: '离线如何提示？' }, { questionId: 'Q02', question: '解绑入口在哪里？' },
  ] }))
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  const input = screen.getByRole('textbox', { name: '优化指令' }) as HTMLTextAreaElement
  expect(input.value).toContain('离线如何提示？')
  expect(input.value).toContain('解绑入口在哪里？')
  expect(input.value).not.toContain('旧问题')
  await user.click(screen.getByRole('button', { name: '提交优化' }))
  expect(body).toBeUndefined()
  expect(screen.getByText('待确认项（2）')).toBeInTheDocument()
  await user.clear(input)
  await user.type(input, '补充：解绑入口在设备管理页。离线提示仍待确认。')
  await user.click(screen.getByRole('button', { name: '取消优化' }))
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  expect(screen.getByRole('textbox', { name: '优化指令' })).toHaveValue('补充：解绑入口在设备管理页。离线提示仍待确认。')
  await user.click(screen.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(body?.revisionInstruction).toBe('补充：解绑入口在设备管理页。离线提示仍待确认。'))
  expect(screen.getByRole('textbox', { name: '优化指令' })).toHaveValue('补充：解绑入口在设备管理页。离线提示仍待确认。')
})


it('显示模型输出自动修复进度，终态不显示过期修复信息', async () => {
  let currentRun: FunctionalCaseGenerateTaskRun = {
    ...pendingRun, status: 'running', currentStage: 'detailed_cases',
    resultSummaryJson: JSON.stringify({ outputValidation: {
      stage: 'detailed_cases', module: '登录', repairAttempt: 1, maxRepairs: 2, status: 'repairing',
    } }),
  }
  installFetchHandler(() => currentRun)
  const user = userEvent.setup()
  renderPage()
  expect(await screen.findByLabelText('详细用例 / 登录：输出校验未通过，正在进行第 1/2 次自动修复')).toBeInTheDocument()
  currentRun = { ...currentRun, status: 'error', stageStatus: 'failed' }
  await user.click(screen.getByRole('button', { name: /刷新/ }))
  await waitFor(() => expect(screen.queryByLabelText(/正在进行第 1\/2 次自动修复/)).not.toBeInTheDocument())
})

it.each(['save', 'approve'])('需求分析 %s 后重新加载应显示修改内容', async (action) => {
  let currentRun: FunctionalCaseGenerateTaskRun = {
    ...pendingRun, status: 'waiting_review', checkpointEnabled: true,
    currentStage: 'requirement_analysis', stageStatus: 'waiting_review',
    configJson: JSON.stringify({ requirementAnalysis: { functionalOverview: { purpose: 'old' } } }),
  }
  let reviewRequested = false
  let requestBody: { stage: string; configJson: string } | undefined
  installFetchHandler(() => currentRun, (url, init) => {
    if (url.pathname.endsWith('/stage-review')) {
      reviewRequested = true
      expect(JSON.parse(String(currentRun.configJson)).requirementAnalysis.functionalOverview.purpose).toBe('edited')
      return jsonResponse(currentRun)
    }
    if (url.pathname.endsWith('/stage-output')) {
      requestBody = JSON.parse(String(init?.body))
      const config = JSON.parse(requestBody!.configJson)
      currentRun = { ...currentRun, configJson: JSON.stringify({
        ...JSON.parse(String(currentRun.configJson)), ...config,
      }) }
      return jsonResponse(currentRun)
    }
  })
  const user = userEvent.setup()
  renderPage()
  await clickRunInlineAction(user, 'run-1', '审核')
  await user.click(screen.getByRole('tab', { name: 'json' }))
  const editor = document.querySelector('.cm-content') as HTMLElement
  await user.click(editor)
  await user.keyboard('{Control>}a{/Control}')
  await user.paste('{"functionalOverview":{"purpose":"edited"}}')
  await user.click(screen.getByRole('button', { name: action === 'save' ? /^保\s*存$/ : '审核通过并继续' }))
  await waitFor(() => expect(requestBody).toBeDefined())
  expect(requestBody?.stage).toBe('requirement_analysis')
  expect(JSON.parse(requestBody!.configJson)).toEqual({ requirementAnalysis: { functionalOverview: { purpose: 'edited' } } })
  if (action === 'save') await screen.findByText('阶段产物已保存')
  else await waitFor(() => expect(reviewRequested).toBe(true))
  cleanup()
  renderPage()
  await clickRunInlineAction(user, 'run-1', '审核')
  await user.click(screen.getByRole('tab', { name: 'json' }))
  await waitFor(() => expect(document.querySelector('.cm-content')).toHaveTextContent('edited'))
})

it('优化在原窗口右侧展开，取消保留草稿并使用内联选择的模型', async () => {
  const currentRun: FunctionalCaseGenerateTaskRun = {
    ...pendingRun, status: 'waiting_review', checkpointEnabled: true,
    currentStage: 'requirement_analysis', stageStatus: 'waiting_review',
    configJson: JSON.stringify({ requirementAnalysis: { purpose: 'analysis' } }),
  }
  let body: Record<string, unknown> | undefined
  installFetchHandler(() => currentRun, (url, init) => {
    if (url.pathname.includes('/integrations/llm/connections')) {
      return jsonResponse({ items: [
        { connectionId: 'mine', name: '模型一', status: 'active' },
        { connectionId: 'second', name: '模型二', status: 'active' },
      ], total: 2 })
    }
    if (url.pathname.endsWith('/stage-revise')) {
      body = JSON.parse(String(init?.body))
      return jsonResponse({ ...currentRun, status: 'pending', stageStatus: 'pending' })
    }
  })
  const user = userEvent.setup()
  renderPage()
  await clickRunInlineAction(user, 'run-1', '审核')
  expect(screen.getByRole('textbox', { name: '审核备注' }).closest('.ant-modal-footer')).not.toBeNull()
  await user.type(screen.getByRole('textbox', { name: '审核备注' }), '保留审核备注')
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  expect(screen.queryByRole('textbox', { name: '审核备注' })).not.toBeInTheDocument()
  const input = screen.getByRole('textbox', { name: '优化指令' })
  await user.type(input, '补充异常场景')
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  expect(screen.getByRole('button', { name: /提交优化/ })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: '取消优化' }))
  expect(screen.queryByRole('textbox', { name: '优化指令' })).not.toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: '审核备注' })).toHaveValue('保留审核备注')
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  expect(screen.getByRole('textbox', { name: '优化指令' })).toHaveValue('补充异常场景')
  await user.click(screen.getByRole('combobox', { name: '本次使用的模型' }))
  await user.click(await screen.findByText(/模型二 ·/))
  await user.click(screen.getByRole('button', { name: /提交优化/ }))
  await waitFor(() => expect(body).toMatchObject({ llmConnectionId: 'second', revisionInstruction: '补充异常场景' }))
})

it('功能任务详情有原文但无增强文本时禁止运行', async () => {
  let runRequested = false
  installFetchHandler(() => pendingRun, (url) => {
    if (url.pathname === '/v1/requirements/requirement-1') return jsonResponse({ requirementId: 'requirement-1', name: '需求', documentType: 'docx', documentFilename: '原文.docx', documentContent: ' \n ' })
    if (url.pathname.endsWith('/run')) runRequested = true
  })
  const user = userEvent.setup()
  renderPage()
  const button = await screen.findByRole('button', { name: /^运行$/ })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  expect(await screen.findByText('请先完成需求分析并导入增强文本，再生成功能用例')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '确认运行' })).not.toBeInTheDocument()
  expect(runRequested).toBe(false)
})

describe('图谱分析', () => {
  const relations = {
    schema_version: '2.0',
    main_paths: [{ path_id: 'P01', case_ids: ['case-1', 'case-2'] }],
    edges: [{ edge_id: 'E01', from_case_id: 'case-1', to_case_id: 'case-2', relation_type: 'next', order: 1 }],
  }

  it('审核通过后在更多操作中出现生成图谱，点击派发并在完成后展示鱼骨图谱，可切换查看 JSON', async () => {
    let relationRequested = false
    let currentRun: FunctionalCaseGenerateTaskRun = {
      ...pendingRun,
      reviewStatus: 'approved',
      reviewedAt: '2026-08-02T08:00:00.000Z',
    }
    installFetchHandler(() => currentRun, (url, init) => {
      if (url.pathname === '/v1/function-case-generate-task-runs/run-1/relation-analysis' && init?.method === 'POST') {
        relationRequested = true
        currentRun = {
          ...currentRun,
          status: 'success',
          currentStage: 'completed',
          stageStatus: 'completed',
          configJson: { caseRelations: relations },
        }
        return jsonResponse(currentRun)
      }
    })
    const user = userEvent.setup()
    renderPage()

    await openRunActionsMenu(user, 'run-1')
    expect(screen.queryByRole('button', { name: '图谱分析' })).not.toBeInTheDocument()
    await user.click(await screen.findByRole('menuitem', { name: '生成图谱' }))
    await waitFor(() => expect(relationRequested).toBe(true))

    await openRunActionsMenu(user, 'run-1')
    expect(
      await screen.findByRole('menuitem', { name: '重新生成图谱' }, { timeout: 5000 }),
    ).toBeEnabled()
    await user.click(screen.getByRole('button', { name: '图谱分析' }))
    // 图谱分析跳转到独立页面，鱼骨可视化在整页画布上展示。
    await waitFor(() => {
      expect(document.querySelector('.ai-relations-node')).not.toBeNull()
    })
    expect(document.body.textContent).toContain('1 条业务主线')

    // 单行工具条用 Segmented 切换可视化 / json（隐藏的 radio input 不可点击，点可见分段项）
    const relationsBar = document.querySelector('.ai-relations-page-bar') as HTMLElement
    await user.click(within(relationsBar).getByText('json'))
    await waitFor(() => {
      expect(document.querySelector('.json-editor-codemirror')).not.toBeNull()
    })
  })

  it('未审核通过的运行不出现生成图谱入口', async () => {
    installFetchHandler(() => pendingRun)
    renderPage()

    const row = await findRunRow('run-1')
    // 待审核记录的「审核候选结果」已在行内，「更多」里只剩状态变更类操作，因此没有可展开的菜单。
    await within(row).findByRole('button', { name: buttonNamePattern('审核候选结果') })
    expect(within(row).queryByRole('button', { name: '更多操作' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '图谱分析' })).not.toBeInTheDocument()
  })
})
