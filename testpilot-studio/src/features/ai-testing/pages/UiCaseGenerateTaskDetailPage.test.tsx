import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '@/app/providers/ThemeProvider'
import { UiCaseGenerateTaskDetailPage } from './UiCaseGenerateTaskDetailPage'

const task = {
  taskId: 'ui-task-1',
  taskType: 'ui_case_generate',
  name: '登录模块 UI 用例生成',
  projectId: 'project-1',
  sprintId: 'sprint-1',
  requirementId: 'requirement-1',
  sourceType: 'source_archive',
  sourceArchive: {
    archiveId: 'archive-1',
    filename: 'source.zip',
    sizeBytes: 2048,
    sha256: 'abc123',
    uploadedAt: '2026-08-02T08:00:00.000Z',
  },
  instruction: '覆盖表单校验',
}

const resultYaml = `cases:
  - name: 登录成功
    enabled: true
    orderNo: 1
    stepsJson:
      - orderNo: 1
        stepName: 打开登录页
        keyword: open
        operationValue: https://example.test/login
        continueOnFailure: false
        enabled: true
`

const run = {
  runId: 'ui-run-1',
  taskId: 'ui-task-1',
  projectId: 'project-1',
  status: 'success',
  reviewStatus: 'pending',
  importStatus: 'pending',
  importedTargets: [],
  importedAt: null,
  importMigrationComplete: true,
  resultYaml,
  createdAt: '2026-08-02T09:00:00.000Z',
}

function jsonResponse(data: unknown, status = 200, message = 'ok') {
  return new Response(JSON.stringify({ code: status < 400 ? 0 : status, message, data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installFetchHandler(onRequest?: (url: URL, init?: RequestInit) => Response | Promise<Response> | undefined) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const requestUrl = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(requestUrl, 'http://localhost')
    const handled = onRequest?.(url, init)
    if (handled) return handled
    if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1') return jsonResponse(task)
    if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: [run], total: 1 })
    if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1') return jsonResponse(run)
    if (url.pathname === '/v1/projects/project-1/integrations/llm/connections') {
      return jsonResponse({ items: [{ connectionId: 'llm-1', name: '主模型', status: 'active' }], total: 1 })
    }
    return jsonResponse({ items: [], total: 0 })
  })
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  seedOwnerProject(queryClient)
  render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/ai-testing/ui-tasks/ui-task-1']}>
          <Routes>
            <Route path="/ai-testing/ui-tasks/:taskId" element={<UiCaseGenerateTaskDetailPage />} />
            <Route path="/ai-testing" element={<div>生成任务列表</div>} />
            <Route path="/ui-automation/suites/:suiteId" element={<div>正式 UI 套件详情</div>} />
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
})

describe('UI 用例生成任务详情', () => {
  it('运行记录不显示中间配置入口', async () => {
    installFetchHandler()
    renderPage()

    expect(await screen.findByRole('button', { name: '结果 YAML' })).toHaveClass('ai-task-run-result-popover-btn')
    expect(screen.queryByRole('button', { name: '中间配置' })).not.toBeInTheDocument()
  })

  it('只读候选结果入口沿用 API 用例的主按钮样式', async () => {
    const importedRun = { ...run, reviewStatus: 'approved', importStatus: 'imported' }
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') {
        return jsonResponse({ items: [importedRun], total: 1 })
      }
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1') return jsonResponse(importedRun)
    })
    renderPage()

    expect(await screen.findByRole('button', { name: '查看候选结果' })).toHaveClass('ant-btn-primary')
  })

  it('返回生成任务时回到生成任务列表', async () => {
    installFetchHandler()
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '返回生成任务' }))

    expect(await screen.findByText('生成任务列表')).toBeInTheDocument()
  })

  it('运行未成功时不提前显示待审核和待导入状态', async () => {
    const runningRun = { ...run, status: 'running', reviewStatus: 'pending', importStatus: 'pending' }
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') {
        return jsonResponse({ items: [runningRun], total: 1 })
      }
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1') return jsonResponse(runningRun)
    })
    renderPage()

    expect(await screen.findByText('running')).toBeInTheDocument()
    expect(screen.queryByText('待审核')).not.toBeInTheDocument()
    expect(screen.queryByText('待导入')).not.toBeInTheDocument()
  })

  it('审核通过且待导入时提供 UI 正式资产导入入口', async () => {
    const approvedPendingRun = {
      ...run,
      reviewStatus: 'approved',
      importStatus: 'pending',
    }
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') {
        return jsonResponse({ items: [approvedPendingRun], total: 1 })
      }
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1') return jsonResponse(approvedPendingRun)
    })
    renderPage()

    expect(await screen.findByRole('button', { name: '导入正式 UI 套件' })).toBeInTheDocument()
  })

  it.each([
    ['非成功', { status: 'failed', reviewStatus: 'approved', importStatus: 'pending' }],
    ['未批准', { status: 'success', reviewStatus: 'pending', importStatus: 'pending' }],
    ['已导入', { status: 'success', reviewStatus: 'approved', importStatus: 'imported' }],
  ])('%s 运行不提供导入入口', async (_label, state) => {
    const ineligibleRun = { ...run, ...state }
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') {
        return jsonResponse({ items: [ineligibleRun], total: 1 })
      }
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1') {
        return jsonResponse(ineligibleRun)
      }
    })
    renderPage()

    expect((await screen.findAllByText(state.status)).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: '导入正式 UI 套件' })).not.toBeInTheDocument()
  })

  it.each([
    [200, 'ok', '当前需求下暂无可用套件'],
    [403, '无权查看该需求的套件', '无权限执行 UI 用例导入操作：无权查看该需求的套件'],
  ])('套件查询返回 %s 时在选择弹窗展示阻断状态', async (status, backendMessage, expectedText) => {
    const approvedRun = { ...run, reviewStatus: 'approved' }
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: [approvedRun], total: 1 })
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1') return jsonResponse(approvedRun)
      if (url.pathname === '/v1/requirements/requirement-1/ui-test-suites') {
        return jsonResponse({ items: [], total: 0 }, status, backendMessage)
      }
    })
    const user = userEvent.setup()
    renderPage()

    const entryButton = await screen.findByRole('button', { name: '导入正式 UI 套件' })
    await user.click(entryButton)
    if (status === 200) await user.click(await screen.findByLabelText('目标 UI 套件'))

    expect(await screen.findByText(expectedText)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始导入' })).toBeDisabled()
  })

  it('导入请求进行中禁用选择、提交和取消操作', async () => {
    const approvedRun = { ...run, reviewStatus: 'approved' }
    let finishImport: ((response: Response) => void) | undefined
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: [approvedRun], total: 1 })
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1' && !init?.method) return jsonResponse(approvedRun)
      if (url.pathname === '/v1/requirements/requirement-1/ui-test-suites') {
        return jsonResponse({ items: [{ suiteId: 'suite-1', name: '登录回归套件' }], total: 1 })
      }
      if (url.pathname.endsWith('/ui-run-1/import') && init?.method === 'POST') {
        return new Promise<Response>((resolve) => { finishImport = resolve })
      }
    })
    const user = userEvent.setup()
    renderPage()

    const entryButton = await screen.findByRole('button', { name: '导入正式 UI 套件' })
    await user.click(entryButton)
    const suiteSelect = await screen.findByLabelText('目标 UI 套件')
    await user.click(suiteSelect)
    await user.click(await screen.findByText('登录回归套件'))
    const importButton = screen.getByRole('button', { name: '开始导入' })
    const cancelButton = screen.getByRole('button', { name: '取 消' })
    await user.click(importButton)

    await waitFor(() => expect(importButton).toBeDisabled())
    expect(entryButton).toBeDisabled()
    expect(cancelButton).toBeDisabled()
    expect(suiteSelect).toBeDisabled()

    finishImport?.(jsonResponse({
      requiresConfirmation: false,
      conflicts: [],
      run: { ...approvedRun, importStatus: 'imported', importedTargets: [], importedAt: '2026-08-03T08:00:00.000Z' },
    }))
    expect((await screen.findAllByText('已导入')).length).toBeGreaterThan(0)
  })

  it('将符合资格的已批准候选无冲突导入需求下的已有 UI 套件', async () => {
    const approvedRun = {
      ...run,
      requirementId: 'requirement-1',
      reviewStatus: 'approved',
    }
    let importBody: unknown
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') {
        return jsonResponse({ items: [approvedRun], total: 1 })
      }
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1' && !init?.method) {
        return jsonResponse(approvedRun)
      }
      if (url.pathname === '/v1/requirements/requirement-1/ui-test-suites') {
        return jsonResponse({
          items: [
            { suiteId: 'suite-1', name: '登录回归套件' },
            { suiteId: 'suite-2', name: '支付回归套件' },
          ],
          total: 2,
        })
      }
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1/import' && init?.method === 'POST') {
        importBody = JSON.parse(String(init.body))
        return jsonResponse({
          requiresConfirmation: false,
          conflicts: [],
          run: {
            ...approvedRun,
            importStatus: 'imported',
            importedTargets: [{ targetType: 'ui_suite', targetId: 'suite-1' }],
            importedAt: '2026-08-03T08:00:00.000Z',
          },
        })
      }
    })
    const user = userEvent.setup()
    const queryClient = renderPage()

    await user.click(await screen.findByRole('button', { name: '导入正式 UI 套件' }))
    const suiteSearch = await screen.findByLabelText('目标 UI 套件')
    await user.click(suiteSearch)
    await user.type(suiteSearch, '登录')
    expect(screen.queryByText('支付回归套件')).not.toBeInTheDocument()
    await user.click(await screen.findByText('登录回归套件'))
    await user.click(screen.getByRole('button', { name: '开始导入' }))

    await waitFor(() => expect(importBody).toEqual({ suiteId: 'suite-1', confirmOverwrite: false }))
    expect((await screen.findAllByText('已导入')).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: '导入正式 UI 套件' })).not.toBeInTheDocument()
    const cachedRuns = queryClient.getQueryData<{ items: typeof run[]; total: number }>([
      'uiCaseGenerateTaskRuns',
      'ui-task-1',
    ])
    expect(cachedRuns?.items).not.toBe(cachedRuns)
    expect(cachedRuns?.items[0]).toMatchObject({ runId: 'ui-run-1', importStatus: 'imported' })
    await user.click(screen.getByRole('button', { name: '查看正式套件' }))
    expect(await screen.findByText('正式 UI 套件详情')).toBeInTheDocument()
  })

  it('零写入预览全部冲突、完整步骤与未知字段，并可安全取消后重试', async () => {
    const approvedRun = { ...run, requirementId: 'requirement-1', reviewStatus: 'approved' }
    const conflicts = [
      {
        normalizedName: 'login',
        existingCase: {
          name: 'Login', enabled: true, orderNo: 1,
          stepsJson: [{
            orderNo: 1,
            stepName: null,
            keyword: '',
            locatorValue: '#email',
            operationValue: 'a'.repeat(120),
            continueOnFailure: false,
            enabled: true,
            extensionFlag: { source: 'plugin' },
          }],
        },
        generatedCase: {
          name: ' login ', enabled: false, orderNo: 7,
          stepsJson: [{
            orderNo: 9,
            stepName: '输入邮箱',
            keyword: 'fill',
            locatorType: 'css',
            locatorValue: '#email',
            operationValue: 'user@example.test',
            continueOnFailure: true,
            enabled: false,
            generatedOnly: '保留我',
          }],
        },
      },
      {
        normalizedName: 'logout',
        existingCase: { name: 'Logout', enabled: true, orderNo: 2, stepsJson: [] },
        generatedCase: { name: ' logout ', enabled: true, orderNo: 8, stepsJson: [] },
      },
    ]
    let importRequests = 0
    const fetchSpy = installFetchHandler((url, init) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: [approvedRun], total: 1 })
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1' && !init?.method) return jsonResponse(approvedRun)
      if (url.pathname === '/v1/requirements/requirement-1/ui-test-suites') {
        return jsonResponse({ items: [{ suiteId: 'suite-1', name: '登录回归套件' }], total: 1 })
      }
      if (url.pathname.endsWith('/ui-run-1/import') && init?.method === 'POST') {
        importRequests += 1
        return jsonResponse({ requiresConfirmation: true, conflicts, run: approvedRun })
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '导入正式 UI 套件' }))
    await user.click(await screen.findByLabelText('目标 UI 套件'))
    await user.click(await screen.findByText('登录回归套件'))
    await user.click(screen.getByRole('button', { name: '开始导入' }))

    expect(await screen.findByText('发现 2 个同名用例冲突')).toBeInTheDocument()
    expect(screen.getByText(/1\. .*login/)).toBeInTheDocument()
    expect(screen.getByText(/2\. .*logout/)).toBeInTheDocument()
    expect(screen.getByText('现有正式用例')).toBeInTheDocument()
    expect(screen.getByText('已批准候选用例')).toBeInTheDocument()
    expect(screen.getByText('（空字符串）')).toBeInTheDocument()
    expect(screen.getByText('null')).toBeInTheDocument()
    expect(screen.getByText('（缺失）')).toBeInTheDocument()
    expect(screen.getByText(/extensionFlag/)).toBeInTheDocument()
    expect(screen.getByText(/generatedOnly/)).toBeInTheDocument()
    expect(screen.queryAllByText(/__rowKey/)).toHaveLength(0)
    expect(screen.getAllByText('完整原始 stepsJson').length).toBeGreaterThan(0)
    expect(fetchSpy.mock.calls.every(([input, init]) => {
      const path = new URL(String(input), 'http://localhost').pathname
      return !(/\/v1\/ui-test-cases|\/v1\/ui-test-suites\/[^/]+\/cases/.test(path) && init?.method !== 'GET')
    })).toBe(true)

    await user.click(screen.getByRole('button', { name: '取消覆盖' }))
    expect(importRequests).toBe(1)
    expect(screen.getAllByText('已批准').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: '导入正式 UI 套件' }))
    expect((await screen.findAllByText('登录回归套件')).length).toBeGreaterThan(0)
  })

  it('使用同一套件整批覆盖，冲突变化时要求再次确认后才成功', async () => {
    const approvedRun = { ...run, requirementId: 'requirement-1', reviewStatus: 'approved' }
    const originalConflict = {
      normalizedName: 'login',
      existingCase: { name: 'Login', enabled: true, orderNo: 1, stepsJson: [] },
      generatedCase: { name: ' login ', enabled: false, orderNo: 7, stepsJson: [] },
    }
    const changedConflict = {
      normalizedName: 'login changed',
      existingCase: { name: 'Login Changed', enabled: true, orderNo: 2, stepsJson: [] },
      generatedCase: { name: ' login changed ', enabled: false, orderNo: 8, stepsJson: [] },
    }
    const requestBodies: unknown[] = []
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: [approvedRun], total: 1 })
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1' && !init?.method) return jsonResponse(approvedRun)
      if (url.pathname === '/v1/requirements/requirement-1/ui-test-suites') {
        return jsonResponse({ items: [{ suiteId: 'suite-1', name: '登录回归套件' }], total: 1 })
      }
      if (url.pathname.endsWith('/ui-run-1/import') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        requestBodies.push(body)
        if (requestBodies.length === 1) return jsonResponse({ requiresConfirmation: true, conflicts: [originalConflict], run: approvedRun })
        if (requestBodies.length === 2) return jsonResponse({ requiresConfirmation: true, conflicts: [changedConflict], run: approvedRun })
        return jsonResponse({
          requiresConfirmation: false,
          conflicts: [],
          run: {
            ...approvedRun,
            importStatus: 'imported',
            importedTargets: [{ targetType: 'ui_suite', targetId: 'suite-1' }],
            importedAt: '2026-08-03T09:00:00.000Z',
          },
        })
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '导入正式 UI 套件' }))
    await user.click(await screen.findByLabelText('目标 UI 套件'))
    await user.click(await screen.findByText('登录回归套件'))
    await user.click(screen.getByRole('button', { name: '开始导入' }))
    await user.click(await screen.findByRole('button', { name: '整批确认覆盖' }))

    expect(await screen.findByText('冲突已变化，请重新检查后再次确认')).toBeInTheDocument()
    expect(screen.getAllByText(/login changed/).length).toBeGreaterThan(0)
    expect(requestBodies).toHaveLength(2)
    expect(requestBodies[1]).toEqual({ suiteId: 'suite-1', confirmOverwrite: true })

    await user.click(screen.getByRole('button', { name: '整批确认覆盖' }))
    await waitFor(() => expect(requestBodies).toHaveLength(3))
    expect(requestBodies[2]).toEqual({ suiteId: 'suite-1', confirmOverwrite: true })
    expect((await screen.findAllByText('已导入')).length).toBeGreaterThan(0)
  })

  it('确认阶段套件失效时保留冲突内容并禁止旧目标再次确认', async () => {
    const approvedRun = { ...run, requirementId: 'requirement-1', reviewStatus: 'approved' }
    const conflict = {
      normalizedName: 'login',
      existingCase: { name: 'Login', enabled: true, orderNo: 1, stepsJson: [] },
      generatedCase: { name: ' login ', enabled: false, orderNo: 7, stepsJson: [] },
    }
    let suiteRequests = 0
    let importRequests = 0
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: [approvedRun], total: 1 })
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1' && !init?.method) return jsonResponse(approvedRun)
      if (url.pathname === '/v1/requirements/requirement-1/ui-test-suites') {
        suiteRequests += 1
        return jsonResponse(suiteRequests === 1
          ? { items: [{ suiteId: 'suite-1', name: '登录回归套件' }], total: 1 }
          : { items: [], total: 0 })
      }
      if (url.pathname.endsWith('/ui-run-1/import') && init?.method === 'POST') {
        importRequests += 1
        return importRequests === 1
          ? jsonResponse({ requiresConfirmation: true, conflicts: [conflict], run: approvedRun })
          : jsonResponse({}, 404, '目标套件不存在')
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '导入正式 UI 套件' }))
    await user.click(await screen.findByLabelText('目标 UI 套件'))
    await user.click(await screen.findByText('登录回归套件'))
    await user.click(screen.getByRole('button', { name: '开始导入' }))

    expect(await screen.findByText(/同名用例原位覆盖，非冲突候选同时新增/)).toBeInTheDocument()
    const confirmButton = screen.getByRole('button', { name: '整批确认覆盖' })
    await user.click(confirmButton)

    expect(await screen.findByText('目标套件不存在')).toBeInTheDocument()
    expect(screen.getAllByText(/login/).length).toBeGreaterThan(0)
    await waitFor(() => expect(confirmButton).toBeDisabled())
    expect(importRequests).toBe(2)
  })

  it.each([
    [400, '该运行已经导入', '该运行已经导入'],
    [403, '无权导入该套件', '无权限执行 UI 用例导入操作：无权导入该套件'],
    [404, '目标套件不存在', '目标套件不存在'],
    [500, '事务执行失败', '服务端导入失败，未完成正式资产写入：事务执行失败'],
  ])('导入失败 %s 时在选择弹窗保留套件并允许重试', async (status, backendMessage, expectedMessage) => {
    const approvedRun = { ...run, requirementId: 'requirement-1', reviewStatus: 'approved' }
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: [approvedRun], total: 1 })
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1' && !init?.method) return jsonResponse(approvedRun)
      if (url.pathname === '/v1/requirements/requirement-1/ui-test-suites') {
        return jsonResponse({ items: [{ suiteId: 'suite-1', name: '登录回归套件' }], total: 1 })
      }
      if (url.pathname.endsWith('/ui-run-1/import') && init?.method === 'POST') {
        return jsonResponse({}, status, backendMessage)
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '导入正式 UI 套件' }))
    await user.click(await screen.findByLabelText('目标 UI 套件'))
    await user.click(await screen.findByText('登录回归套件'))
    await user.click(screen.getByRole('button', { name: '开始导入' }))

    expect(await screen.findByText(expectedMessage)).toBeInTheDocument()
    expect(screen.getAllByText('登录回归套件').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: '开始导入' })).toBeEnabled()
  })

  it('重复导入 400 后重新查询并收敛到其他操作已完成的只读状态', async () => {
    const approvedRun = { ...run, requirementId: 'requirement-1', reviewStatus: 'approved' }
    const importedRun = {
      ...approvedRun,
      importStatus: 'imported',
      importedTargets: [{ targetType: 'ui_suite', targetId: 'suite-1' }],
      importedAt: '2026-08-03T10:00:00.000Z',
    }
    let detailRequests = 0
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: [approvedRun], total: 1 })
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1' && !init?.method) {
        detailRequests += 1
        return jsonResponse(detailRequests >= 3 ? importedRun : approvedRun)
      }
      if (url.pathname === '/v1/requirements/requirement-1/ui-test-suites') {
        return jsonResponse({ items: [{ suiteId: 'suite-1', name: '登录回归套件' }], total: 1 })
      }
      if (url.pathname.endsWith('/ui-run-1/import') && init?.method === 'POST') {
        return jsonResponse({}, 400, '该运行已经导入')
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '导入正式 UI 套件' }))
    await user.click(await screen.findByLabelText('目标 UI 套件'))
    await user.click(await screen.findByText('登录回归套件'))
    await user.click(screen.getByRole('button', { name: '开始导入' }))

    expect(await screen.findByText('该运行已由其他操作完成导入')).toBeInTheDocument()
    expect((await screen.findAllByText('已导入')).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: '导入正式 UI 套件' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看正式套件' })).toBeInTheDocument()
  })

  it('冲突预览期间页面重新聚焦可收敛到其他操作完成的导入状态', async () => {
    const approvedRun = { ...run, requirementId: 'requirement-1', reviewStatus: 'approved' }
    const importedRun = {
      ...approvedRun,
      importStatus: 'imported',
      importedTargets: [{ targetType: 'ui_suite', targetId: 'suite-1' }],
      importedAt: '2026-08-03T10:30:00.000Z',
    }
    let externallyImported = false
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: [approvedRun], total: 1 })
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1' && !init?.method) {
        return jsonResponse(externallyImported ? importedRun : approvedRun)
      }
      if (url.pathname === '/v1/requirements/requirement-1/ui-test-suites') {
        return jsonResponse({ items: [{ suiteId: 'suite-1', name: '登录回归套件' }], total: 1 })
      }
      if (url.pathname.endsWith('/ui-run-1/import') && init?.method === 'POST') {
        externallyImported = true
        return jsonResponse({
          requiresConfirmation: true,
          conflicts: [{
            normalizedName: 'login',
            existingCase: { name: 'Login', enabled: true, orderNo: 1, stepsJson: [] },
            generatedCase: { name: ' login ', enabled: false, orderNo: 7, stepsJson: [] },
          }],
          run: approvedRun,
        })
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '导入正式 UI 套件' }))
    await user.click(await screen.findByLabelText('目标 UI 套件'))
    await user.click(await screen.findByText('登录回归套件'))
    await user.click(screen.getByRole('button', { name: '开始导入' }))
    expect(await screen.findByText('发现 1 个同名用例冲突')).toBeInTheDocument()

    window.dispatchEvent(new Event('focus'))

    expect(await screen.findByText('该运行已由其他操作完成导入')).toBeInTheDocument()
    expect((await screen.findAllByText('已导入')).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: '导入正式 UI 套件' })).not.toBeInTheDocument()
  })

  it('展示源码包、运行状态和结构化候选步骤，不访问内部 Worker 接口', async () => {
    const fetchSpy = installFetchHandler()
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('source.zip')).toBeInTheDocument()
    expect(document.querySelector('.ai-task-detail-split')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^源码包/ }))
    expect(screen.getByText('2 KiB')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^运行记录/ }))
    await user.click(await screen.findByRole('button', { name: '审核候选结果' }))
    await user.click(await screen.findByRole('button', { name: '登录成功，展开' }))
    expect(screen.getByText('登录成功')).toBeInTheDocument()
    expect(screen.getByText('打开登录页')).toBeInTheDocument()
    expect(screen.getAllByText('success').length).toBeGreaterThan(0)
    expect(fetchSpy.mock.calls.every(([input]) => !String(input).includes('/internal/ai-worker/'))).toBe(true)
  })

  it('编辑任务时保留并提交必填的迭代与需求', async () => {
    let patchBody: unknown
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/projects/project-1/sprints') {
        return jsonResponse({ items: [{ sprintId: 'sprint-1', name: '迭代一' }], total: 1 })
      }
      if (url.pathname === '/v1/sprints/sprint-1/requirements') {
        return jsonResponse({ items: [{ requirementId: 'requirement-1', name: '登录需求' }], total: 1 })
      }
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1' && init?.method === 'PATCH') {
        patchBody = JSON.parse(String(init.body))
        return jsonResponse({ ...task, name: '更新后的 UI 任务' })
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /编辑任务/ }))
    const nameInput = screen.getByLabelText('编辑任务名称')
    await user.clear(nameInput)
    await user.type(nameInput, '更新后的 UI 任务')
    await user.click(screen.getByRole('button', { name: /^保\s*存$/ }))

    await waitFor(() => expect(patchBody).toEqual({
      name: '更新后的 UI 任务',
      sprintId: 'sprint-1',
      requirementId: 'requirement-1',
      instruction: '覆盖表单校验',
    }))
  })

  it('未上传源码包时禁用运行并解释前置条件', async () => {
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1') return jsonResponse({ ...task, sourceArchive: null })
    })
    const user = userEvent.setup()
    renderPage()

    const runButton = await screen.findByRole('button', { name: /运行任务/ })
    expect(runButton).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /^源码包/ }))
    expect(screen.getAllByText('请先上传源码 ZIP').length).toBeGreaterThan(0)
  })

  it('选择 LLM 后运行请求只发送 connectionId', async () => {
    let runBody: unknown
    const startedRun = { ...run, runId: 'ui-run-2', status: 'pending' }
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/run' && init?.method === 'POST') {
        runBody = JSON.parse(String(init.body))
        return jsonResponse(startedRun)
      }
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-2') return jsonResponse(startedRun)
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /运行任务/ }))
    await user.click(await screen.findByText('主模型'))
    await user.click(screen.getByRole('button', { name: /确认运行/ }))

    await waitFor(() => expect(runBody).toEqual({ connectionId: 'llm-1' }))
  })

  it('运行返回 403 时展示权限错误且保留任务内容', async () => {
    installFetchHandler((url, init) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/run' && init?.method === 'POST') {
        return jsonResponse({}, 403, '无权运行该任务')
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /运行任务/ }))
    await user.click(await screen.findByText('主模型'))
    await user.click(screen.getByRole('button', { name: /确认运行/ }))

    expect(await screen.findByText('无权运行该任务')).toBeInTheDocument()
    expect(screen.getByText('source.zip')).toBeInTheDocument()
  })

  it('展示五种运行状态，并在存在活动运行时禁用源码包替换', async () => {
    const statusRuns = ['pending', 'claimed', 'running', 'success', 'failed'].map((status, index) => ({
      ...run,
      runId: `run-${status}`,
      status,
      createdAt: `2026-08-02T0${index + 1}:00:00.000Z`,
    }))
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: statusRuns, total: 5 })
      const matched = statusRuns.find((item) => url.pathname.endsWith(`/${item.runId}`))
      if (matched) return jsonResponse(matched)
    })
    const user = userEvent.setup()
    renderPage()

    for (const status of ['pending', 'claimed', 'running', 'success', 'failed']) {
      expect((await screen.findAllByText(status)).length).toBeGreaterThan(0)
    }
    await user.click(screen.getByRole('button', { name: /^源码包/ }))
    expect(screen.getByRole('button', { name: /替换源码包/ })).toBeDisabled()
  })

  it('保存完整 YAML 后可以批准并立即冻结编辑', async () => {
    const savedYaml = resultYaml.replace('登录成功', '登录成功（已确认）')
    let patchBody: unknown
    let reviewBody: unknown
    installFetchHandler((url, init) => {
      if (url.pathname.endsWith('/result') && init?.method === 'PATCH') {
        patchBody = JSON.parse(String(init.body))
        return jsonResponse({ ...run, resultYaml: savedYaml })
      }
      if (url.pathname.endsWith('/review') && init?.method === 'POST') {
        reviewBody = JSON.parse(String(init.body))
        return jsonResponse({ ...run, resultYaml: savedYaml, reviewStatus: 'approved', importStatus: 'pending', importedTargets: [] })
      }
    })
    const user = userEvent.setup()
    renderPage()

    const reviewEntry = await screen.findByRole('button', { name: '审核候选结果' })
    expect(reviewEntry).toHaveClass('ant-btn-primary')
    await user.click(reviewEntry)
    await user.click(await screen.findByRole('tab', { name: '编辑 YAML' }))
    const editor = await screen.findByRole('textbox', { name: '候选结果 YAML' })
    await user.click(editor)
    await user.keyboard('{Control>}a{/Control}')
    await user.paste(savedYaml)
    await user.click(screen.getByRole('button', { name: '保存候选结果' }))

    await waitFor(() => expect(patchBody).toEqual({ resultYaml: savedYaml }))
    await user.click(screen.getByRole('button', { name: '批准候选' }))
    await waitFor(() => expect(reviewBody).toEqual({ action: 'approve' }))
    expect(await screen.findByText('已批准')).toBeInTheDocument()
    expect(screen.getAllByText('待导入').length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: '导入正式 UI 套件' }).length).toBeGreaterThan(0)
    expect(screen.getByRole('textbox', { name: '候选结果 YAML' })).toHaveAttribute('aria-readonly', 'true')
  })

  it('在候选弹窗中按用例名称折叠 UI 根数组结构并展示统计', async () => {
    const uiRootArrayYaml = `
- name: 登录成功
  enabled: true
  orderNo: 1
  stepsJson:
    - orderNo: 1
      stepName: 打开登录页
      keyword: open
      operationValue: https://example.test/login
`
    const uiStructuredRun = { ...run, resultYaml: uiRootArrayYaml }
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') {
        return jsonResponse({ items: [uiStructuredRun], total: 1 })
      }
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1') return jsonResponse(uiStructuredRun)
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '审核候选结果' }))

    expect(await screen.findByText('用例 1')).toBeInTheDocument()
    expect(screen.getByText('步骤 1')).toBeInTheDocument()
    const caseToggle = screen.getByRole('button', { name: '登录成功，展开' })
    expect(caseToggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('打开登录页')).not.toBeInTheDocument()

    await user.click(caseToggle)
    expect(screen.getByRole('button', { name: '登录成功，收起' })).toHaveAttribute('aria-expanded', 'true')
    expect(await screen.findByText('打开登录页')).toBeInTheDocument()
  })

  it('使用支持字段折叠的 YAML 编辑器', async () => {
    installFetchHandler()
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '审核候选结果' }))
    await user.click(await screen.findByRole('tab', { name: '编辑 YAML' }))

    expect(await screen.findByRole('textbox', { name: '候选结果 YAML' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '还原未保存改动' })).not.toBeInTheDocument()
    const candidateActions = screen.getAllByRole('button')
      .map((button) => button.getAttribute('aria-label') ?? button.textContent?.replaceAll(' ', ''))
      .filter((label) => ['取消', '保存候选结果', '拒绝候选', '批准候选'].includes(label ?? ''))
    expect(candidateActions).toEqual(['取消', '保存候选结果', '拒绝候选', '批准候选'])
    const foldGutter = document.querySelector('.cm-foldGutter')
    expect(foldGutter).toBeInTheDocument()
    expect(foldGutter).toHaveTextContent('⌄')
  })

  it('点击审核弹窗外的遮罩不会关闭弹窗', async () => {
    installFetchHandler()
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '审核候选结果' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(dialog)

    expect(dialog).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '取消' })).toBeInTheDocument()
  })

  it('保存失败时保留未保存的 YAML 草稿并允许重试', async () => {
    const invalidYaml = 'cases:\n  - name: [broken'
    installFetchHandler((url, init) => {
      if (url.pathname.endsWith('/result') && init?.method === 'PATCH') {
        return jsonResponse({}, 400, '候选 YAML 结构不合法')
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '审核候选结果' }))
    await user.click(await screen.findByRole('tab', { name: '编辑 YAML' }))
    const editor = await screen.findByRole('textbox', { name: '候选结果 YAML' })
    await user.click(editor)
    await user.keyboard('{Control>}a{/Control}')
    await user.paste(invalidYaml)
    await user.click(screen.getByRole('button', { name: '保存候选结果' }))

    expect(await screen.findByText('候选 YAML 结构不合法')).toBeInTheDocument()
    expect(editor).toHaveTextContent('name: [broken')
    expect(screen.getByRole('button', { name: '保存候选结果' })).toBeEnabled()
  })

  it('关闭存在未保存改动的候选弹窗前要求确认放弃', async () => {
    installFetchHandler()
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '审核候选结果' }))
    await user.click(await screen.findByRole('tab', { name: '编辑 YAML' }))
    const editor = await screen.findByRole('textbox', { name: '候选结果 YAML' })
    await user.click(editor)
    await user.keyboard('{Control>}a{/Control}')
    await user.paste(resultYaml.replace('登录成功', '尚未保存的登录用例'))
    await user.click(screen.getByRole('button', { name: '取消' }))

    expect((await screen.findAllByText('放弃未保存的候选改动？')).length).toBeGreaterThan(0)
    expect(screen.getByRole('textbox', { name: '候选结果 YAML' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '放弃修改' }))
    await user.click(screen.getByRole('button', { name: '审核候选结果' }))
    const reopenedEditor = await screen.findByRole('textbox', { name: '候选结果 YAML' })
    await waitFor(() => expect(reopenedEditor).toHaveTextContent('登录成功'))
    expect(reopenedEditor).not.toHaveTextContent('尚未保存的登录用例')
  })

  it('拒绝候选后冻结编辑且不出现导入入口', async () => {
    installFetchHandler((url, init) => {
      if (url.pathname.endsWith('/review') && init?.method === 'POST') {
        return jsonResponse({ ...run, reviewStatus: 'rejected' })
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '审核候选结果' }))
    await user.click(await screen.findByRole('tab', { name: '编辑 YAML' }))
    await user.click(screen.getByRole('button', { name: '拒绝候选' }))

    expect(await screen.findByText('已拒绝')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '候选结果 YAML' })).toHaveAttribute('aria-readonly', 'true')
    expect(screen.queryByRole('button', { name: '导入正式 UI 套件' })).not.toBeInTheDocument()
  })

  it('空白候选结果不能审核', async () => {
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1/runs') return jsonResponse({ items: [{ ...run, resultYaml: '   ' }], total: 1 })
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1') return jsonResponse({ ...run, resultYaml: '   ' })
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '审核候选结果' }))
    expect(await screen.findByRole('button', { name: '批准候选' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '拒绝候选' })).toBeDisabled()
  })

  it('替换源码包要求确认，并使用 multipart file 字段更新当前包', async () => {
    let uploadBody: BodyInit | null | undefined
    installFetchHandler((url, init) => {
      if (url.pathname.endsWith('/source-archive') && init?.method === 'PUT') {
        uploadBody = init.body
        return jsonResponse({ ...task, sourceArchive: { ...task.sourceArchive, filename: 'next.zip' } })
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /^源码包/ }))
    await user.click(await screen.findByRole('button', { name: /替换源码包/ }))
    await user.upload(screen.getByLabelText('新的源码 ZIP'), new File(['next'], 'next.zip', { type: 'application/zip' }))
    expect(screen.getAllByText(/source.zip/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/next.zip/).length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: /确认替换/ }))

    await waitFor(() => expect(uploadBody).toBeInstanceOf(FormData))
    expect((uploadBody as FormData).get('file')).toBeInstanceOf(File)
    expect((await screen.findAllByText('next.zip')).length).toBeGreaterThan(0)
  })

  it('替换失败时保留原源码包，并展示 413 后端错误', async () => {
    installFetchHandler((url, init) => {
      if (url.pathname.endsWith('/source-archive') && init?.method === 'PUT') {
        return jsonResponse({}, 413, '文件超过网关大小限制')
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /^源码包/ }))
    await user.click(await screen.findByRole('button', { name: /替换源码包/ }))
    await user.upload(screen.getByLabelText('新的源码 ZIP'), new File(['next'], 'next.zip', { type: 'application/zip' }))
    await user.click(screen.getByRole('button', { name: /确认替换/ }))

    expect(await screen.findByText(/源码包超过上传大小限制.*文件超过网关大小限制/)).toBeInTheDocument()
    expect(screen.getAllByText(/source.zip/).length).toBeGreaterThan(0)
  })

  it.each([
    [400, 'ZIP 内容不合法'],
    [404, '任务不存在'],
  ])('上传返回 %s 时展示后端错误并保留旧包', async (status, errorMessage) => {
    installFetchHandler((url, init) => {
      if (url.pathname.endsWith('/source-archive') && init?.method === 'PUT') {
        return jsonResponse({}, status, errorMessage)
      }
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /^源码包/ }))
    await user.click(await screen.findByRole('button', { name: /替换源码包/ }))
    await user.upload(screen.getByLabelText('新的源码 ZIP'), new File(['next'], 'next.zip', { type: 'application/zip' }))
    await user.click(screen.getByRole('button', { name: /确认替换/ }))

    expect(await screen.findByText(errorMessage)).toBeInTheDocument()
    expect(screen.getAllByText(/source.zip/).length).toBeGreaterThan(0)
  })

  it('任务详情返回 403 时显示阻断权限状态，不渲染任务内容', async () => {
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-tasks/ui-task-1') return jsonResponse({}, 403, '无权查看该任务')
    })
    renderPage()

    expect(await screen.findByText('无权查看该任务')).toBeInTheDocument()
    expect(screen.queryByText('source.zip')).not.toBeInTheDocument()
  })

  it('运行详情返回 403 时隐藏候选内容并显示阻断权限状态', async () => {
    installFetchHandler((url) => {
      if (url.pathname === '/v1/ui-case-generate-task-runs/ui-run-1') return jsonResponse({}, 403, '无权查看该运行')
    })
    renderPage()

    expect(await screen.findByText('无权查看该运行')).toBeInTheDocument()
    expect(screen.queryByText('登录成功')).not.toBeInTheDocument()
    expect(screen.getByText(/候选内容已隐藏/)).toBeInTheDocument()
  })
})
