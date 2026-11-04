import extractionSource from '@/domain/requirements/fixtures/document-extraction.example.json?raw'
import understandingSource from '@/domain/requirements/fixtures/requirement-understanding.example.json?raw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { api } from '@/services/api'
import * as storedFiles from '@/shared/api/files'
import { message } from '@/shared/utils/feedback'
import { canNavigateAway } from '@/shared/utils/unsavedChanges'
import { requirementDesignApi } from '../api/requirementDesign.api'
import { aiTestingApi } from '../api/aiTesting.api'
import { generationChainApi } from '../api/generationChain.api'
import type { GenerationChain, GenerationChainStage } from '../api/generationChain.api'
import { RequirementDesignWorkspace } from './RequirementDesignWorkspace'
import { buildRevisionTemplate, getRevisionQuestions } from '../utils/functionalRevision'

vi.mock('../api/requirementDesign.api', () => ({
  requirementDesignApi: { overview: vi.fn(), history: vi.fn(), start: vi.fn(), configure: vi.fn() },
}))

vi.mock('../api/generationChain.api', () => ({
  generationChainApi: {
    overview: vi.fn(), chain: vi.fn(), version: vi.fn(), run: vi.fn(),
    revise: vi.fn(), review: vi.fn(), saveDraft: vi.fn(), deleteVersion: vi.fn(),
    importOptions: vi.fn(), importVersion: vi.fn(),
  },
}))
vi.mock('../api/aiTesting.api', () => ({
  aiTestingApi: {
    getFunctionalCaseGenerateTaskRun: vi.fn(), getFunctionalCaseGenerateTask: vi.fn(),
    getUiCaseGenerateTask: vi.fn(), getApiCaseGenerateTask: vi.fn(), uploadUiCaseGenerateTaskSourceArchive: vi.fn(),
    generateFunctionalCaseRelationAnalysis: vi.fn(async (runId: string) => ({ runId })),
  },
}))
vi.mock('../hooks/usePersonalLlmChoice', () => ({
  usePersonalLlmChoice: () => ({
    choose: async () => 'llm',
    chooseRun: async () => ({ connectionId: 'llm', checkpointEnabled: true, instruction: '只覆盖登录接口' }),
    dialog: null,
  }),
}))
vi.mock('@/features/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))

const clients: QueryClient[] = []
const stopFlowDragInJsdom = (event: MouseEvent) => {
  if ((event.target as Element).closest('.react-flow__node button, .gc-flow-group')) event.stopPropagation()
}
// React Flow measures nodes before exposing them; jsdom has no layout engine.
beforeAll(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(180)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(100)
  document.addEventListener('mousedown', stopFlowDragInJsdom, true)
  vi.stubGlobal('DOMMatrixReadOnly', class { m22 = 1 })
  vi.stubGlobal('ResizeObserver', class {
    callback: ResizeObserverCallback
    constructor(callback: ResizeObserverCallback) { this.callback = callback }
    observe(target: Element) { queueMicrotask(() => this.callback([{ target, contentRect: { width: 180, height: 100 } } as ResizeObserverEntry], this as unknown as ResizeObserver)) }
    unobserve() {}
    disconnect() {}
  })
})
afterAll(() => { document.removeEventListener('mousedown', stopFlowDragInJsdom, true); vi.restoreAllMocks(); vi.unstubAllGlobals() })
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.clearAllMocks() })

function version(versionId: string, versionNo: number, sourceRunId = 'run') {
  return {
    versionId, versionNo, label: `v${versionNo}`, summary: '2 个页面 · 5 个控件',
    artifactFormat: 'json', createdAt: '2026-10-29T09:30:00Z', reviewerUserId: 'u',
    sourceRunId, imported: false,
  }
}

function chain(): GenerationChain {
  return {
    kind: 'ui', label: 'UI 测试', configured: true, taskId: 'task', runId: 'run',
    active: false, busy: false, sourceChanged: false, draftCount: 1,
    stages: [
      {
        stage: 'ui_surface', label: '元素控件清单', order: 0, state: 'approved',
        latestVersion: version('sv-v1', 1), draft: null, versions: [version('sv-v1', 1)],
        upstreamStages: [],
      },
      {
        stage: 'ui_design', label: 'UI 用例设计', order: 1, state: 'draft',
        latestVersion: version('sv-v1', 1),
        draft: {
          attemptId: 'draft', runId: 'run', status: 'draft', summary: '1 个场景 · 2 步',
          artifactFormat: 'yaml', content: 'name: 登录\nstepsJson:\n  - stepName: 输入账号\n',
          revision: 2, baseVersionId: 'sv-v1', baseVersionLabel: 'v1',
          upstreamVersions: { ui_surface: 'sv-v1' }, createdAt: '2026-10-29T10:00:00Z',
        },
        versions: [version('sv-v1', 1)], upstreamStages: ['ui_surface'],
      },
      {
        stage: 'ui_yaml', label: '用例 YAML', order: 2, state: 'not_started',
        latestVersion: null, draft: null, versions: [], upstreamStages: ['ui_surface', 'ui_design'],
      },
    ],
    leaf: { stage: 'ui_design', versionId: 'sv-v1', versionNo: 1, imported: false },
  }
}

const emptyChain = (kind: 'requirement_analysis' | 'function' | 'api', label: string): GenerationChain => ({
  kind, label, configured: false, draftCount: 0,
  stages: [{ stage: kind === 'function' ? 'requirement_analysis' : kind === 'api' ? 'generate' : 'extracting_text', label: '首阶段', order: 0, state: 'not_started', versions: [], upstreamStages: [] }],
  leaf: {},
})

function mount(documentPreview?: import('react').ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter>
    <RequirementDesignWorkspace requirementId="req" projectId="project" canWrite documentPreview={documentPreview} />
  </MemoryRouter></QueryClientProvider></TestThemeProvider>)
}

it('功能测试默认使用最新需求理解，也能选择历史版本', async () => {
  const functional = emptyChain('function', '功能测试')
  functional.configured = true
  functional.taskId = 'function-task'
  functional.stages[0].label = '测试需求分析'
  functional.stages[0].upstreamStages = ['feature_understanding']
  const analysis = emptyChain('requirement_analysis', '需求分析')
  analysis.configured = true
  const old = { ...version('understanding-v1', 1), stage: 'feature_understanding', summary: '旧需求理解' }
  const latest = { ...version('understanding-v2', 2), stage: 'feature_understanding', summary: '新需求理解' }
  analysis.stages.push({
    stage: 'feature_understanding', label: '需求理解', order: 1,
    state: 'approved', latestVersion: latest, versions: [latest, old], upstreamStages: [],
  })
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [analysis, functional] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(functional)
  vi.mocked(generationChainApi.run).mockResolvedValue(functional)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: '测试需求分析 · 未开始' }))
  const selector = await screen.findByRole('button', { name: '选择上游版本' })
  await waitFor(() => expect(selector).toHaveTextContent('需求理解 v2'))
  await user.click(selector)
  await user.click(await screen.findByRole('combobox', { name: '上游 · 需求理解' }))
  await user.click(await screen.findByText('v1 · 旧需求理解 · 历史'))
  await user.click(selector)
  await user.click(await screen.findByRole('button', { name: '运行此阶段' }))
  await waitFor(() => expect(generationChainApi.run).toHaveBeenCalledWith(
    'req', 'function', 'requirement_analysis', expect.objectContaining({
      upstreamVersions: { feature_understanding: 'understanding-v1' },
    }),
  ))
})

beforeEach(() => {
  vi.mocked(aiTestingApi.getUiCaseGenerateTask).mockResolvedValue({ name: 'UI', sourceType: 'source_archive', instruction: '', sourceArchive: null })
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({
    tasks: [], runCounts: { requirement_analysis: 0, function: 0, api: 0, ui: 0 },
    adoptedUnderstanding: true,
  })
  vi.mocked(requirementDesignApi.history).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), chain()],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(chain())
  vi.mocked(generationChainApi.version).mockResolvedValue({
    versionId: 'sv-v1', kind: 'ui', stage: 'ui_surface', stageLabel: '元素控件清单', versionNo: 1,
    label: 'v1', summary: '2 个页面', artifactFormat: 'yaml', content: 'name: 登录\nstepsJson:\n  - stepName: 输入账号\n',
    reviewerUserId: 'u', reviewedAt: '2026-10-29T09:30:00Z',
    reviewComment: '', upstreamVersions: {}, upstream: [],
  })
  vi.mocked(generationChainApi.review).mockResolvedValue(chain())
  vi.mocked(generationChainApi.revise).mockResolvedValue(chain())
  vi.mocked(generationChainApi.importOptions).mockResolvedValue({
    kind: 'ui', versionId: 'sv-v2', versionLabel: 'v2', leafStage: 'ui_yaml',
    parentVersions: { ui_surface: 'sv-surface', ui_design: 'sv-design' },
    parents: [
      { ...version('sv-surface', 1), stage: 'ui_surface', stageLabel: '元素控件清单' },
      { ...version('sv-design', 1), stage: 'ui_design', stageLabel: 'UI 用例设计' },
    ],
    targets: [{
      targetType: 'ui_suite', targetId: 'suite', name: '正式 UI 套件', caseCount: 3,
      effectiveImportId: 'vi-old', sourceDeleted: false,
      effectiveImport: {
        importId: 'vi-old', versionId: 'sv-v1', versionNo: 1, versionLabel: 'v1',
        leafStage: 'ui_yaml', parentVersions: { ui_surface: 'sv-v1', ui_design: 'sv-v1' },
        changedCaseIds: ['case-1'], changedCaseCount: 1, targetCaseCount: 3,
        mixedSource: true, importedBy: 'u', importedAt: '2026-10-29T12:00:00Z', reviewComment: '',
      },
    }],
    targetRequired: true,
  })
  vi.mocked(generationChainApi.importVersion).mockResolvedValue({
    requiresConfirmation: false, conflicts: [], imported: true, targetId: 'suite',
    targetType: 'ui_suite', changedCaseIds: ['case-1', 'case-2'], changedCaseCount: 2,
    importRecords: [],
  })
  vi.spyOn(api, 'getLlmConnections').mockResolvedValue(Object.assign([{ connectionId: 'llm', name: '本人模型', status: 'active' as const, provider: 'openai', baseUrl: 'https://example.test', authType: 'api_key', account: '', hasAccessToken: true, modelId: 'model' }], { items: [{ connectionId: 'llm', name: '本人模型', status: 'active' as const, provider: 'openai', baseUrl: 'https://example.test', authType: 'api_key', account: '', hasAccessToken: true, modelId: 'model' }], total: 1 }))
  vi.spyOn(api, 'getFunctionalCaseGenerateTaskRun').mockImplementation(async runId => ({ runId, status: 'success', currentStage: 'completed', reviewStatus: 'approved', configJson: {}, importStatus: 'pending', importedTargets: [], importedAt: '' }))
  vi.spyOn(api, 'getFunctionalCaseGenerateTask').mockResolvedValue({ taskId: 'task-function', name: '功能测试', projectId: 'project', instruction: '' })
})

it('单击选中并展示侧栏，双击在画布内打开阶段产物', async () => {
  mount()
  const user = userEvent.setup()
  expect(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' })).toBeInTheDocument()
  expect(screen.getByText('查看需求文档')).toBeInTheDocument()
  expect(screen.queryByText('只读来源')).not.toBeInTheDocument()
  expect(screen.getAllByText('UI 测试').length).toBeGreaterThan(0)
  expect(screen.queryByRole('group', { name: '筛选生成链' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: '需求的生成链' })).not.toBeInTheDocument()
  expect(screen.queryByRole('complementary', { name: '阶段详情' })).not.toBeInTheDocument()

  const card = screen.getByRole('button', { name: 'UI 用例设计 · 待审核' })
  await user.click(card)
  expect(card).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(within(screen.getByRole('complementary', { name: '阶段详情' })).getByRole('heading', { name: 'UI 用例设计' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '关闭阶段详情' }))
  expect(screen.queryByRole('complementary', { name: '阶段详情' })).not.toBeInTheDocument()
  await user.click(card)
  expect(screen.getByRole('complementary', { name: '阶段详情' })).toBeVisible()
  await user.dblClick(card)
  const dialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  expect(within(dialog).getByRole('heading', { name: 'UI 用例设计' })).toBeInTheDocument()
  expect(within(dialog).getByRole('dialog')).toHaveAttribute('aria-modal', 'false')
  expect(within(dialog).getByRole('dialog').closest('.gc-canvas-stage')).not.toBeNull()
  expect(screen.getByRole('complementary', { name: '阶段详情' })).toBeVisible()
  expect(screen.queryByRole('button', { name: '查看并审核' })).not.toBeInTheDocument()
  expect(within(dialog).getByRole('button', { name: '待审核' })).toHaveAttribute('aria-pressed', 'true')
  expect(within(screen.getByRole('complementary', { name: '阶段详情' })).getByText('1 个场景 · 2 步')).toBeInTheDocument()

  await user.click(within(dialog).getByRole('button', { name: /对比/ }))
  const diff = await within(dialog).findByRole('table', { name: '版本差异' })
  expect(within(diff).getAllByRole('columnheader').map(cell => cell.textContent))
    .toEqual(['v1旧版本', '待审核产物当前内容'])
  await user.click(within(dialog).getByRole('button', { name: /审核通过并继续/ }))
  await waitFor(() => expect(generationChainApi.review).toHaveBeenCalledWith('req', 'ui', 'ui_design', {
    action: 'approve', expectedAttemptId: 'draft', continueAfter: true, connectionId: 'llm', requestId: expect.any(String),
  }))
})

it('执行失败且 Worker 未返回原因时仍展示失败详情和运行信息', async () => {
  const failed = chain()
  failed.stages[0] = {
    stage: 'ui_surface', label: '元素控件清单', order: 0, state: 'failed',
    latestVersion: null, draft: null, versions: [], upstreamStages: [],
    errorMessage: '', failureRunId: 'failed-run-1234', failedAt: '2026-11-03T10:11:48Z',
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), failed],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(failed)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '元素控件清单 · 执行失败' }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByRole('heading', { name: '失败详情' })).toBeInTheDocument()
  expect(within(inspector).getByText('阶段执行失败，Worker 未返回具体原因')).toBeInTheDocument()
  expect(within(inspector).getByText(/failed-run-1234/)).toBeInTheDocument()
  expect(within(inspector).getByText(/失败时间/)).toBeInTheDocument()
  await user.dblClick(screen.getByRole('button', { name: '元素控件清单 · 执行失败' }))
  expect(await screen.findAllByText('阶段执行失败，Worker 未返回具体原因')).toHaveLength(2)
})

it('审核通过后下一阶段未启动时提示已通过和具体原因', async () => {
  const warning = vi.spyOn(message, 'warning')
  vi.mocked(generationChainApi.review).mockResolvedValue({ ...chain(), continuationError: '下一阶段已有待审核产物' })
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  await user.click(await screen.findByRole('button', { name: /审核通过并继续/ }))
  await waitFor(() => expect(warning).toHaveBeenCalledWith('已审核通过，下一阶段未启动：下一阶段已有待审核产物'))
  warning.mockRestore()
})

it('历史版本不提示基于旧版上游', async () => {
  const data = chain()
  data.stages[1].latestVersion = data.stages[1].versions[0]
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  const workspace = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  await user.click(within(workspace).getByRole('button', { name: /v1/ }))
  expect(within(workspace).queryByText(/基于旧版/)).not.toBeInTheDocument()
})

it('已审核版本的上游缺失时不提示缺失且仍可导入', async () => {
  const data = chain()
  data.stages[2] = {
    ...data.stages[2], state: 'approved', latestVersion: version('leaf-v1', 1),
    versions: [version('leaf-v1', 1)],
  }
  data.stages[1].versions = []
  data.stages[1].latestVersion = null
  data.stages[1].draft = null
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(generationChainApi.version).mockResolvedValue({
    versionId: 'leaf-v1', kind: 'ui', stage: 'ui_yaml', stageLabel: '用例 YAML', versionNo: 1,
    label: 'v1', summary: '已审核用例', artifactFormat: 'yaml', content: '- name: 登录\n',
    reviewerUserId: 'u', reviewedAt: null, reviewComment: '',
    upstreamVersions: { ui_surface: 'sv-v1', ui_design: 'deleted' }, upstream: [],
  })
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: '用例 YAML · 已通过' }))
  await waitFor(() => expect(generationChainApi.version).toHaveBeenCalledWith('req', 'ui', 'leaf-v1'))
  expect(screen.queryByText('上游已删除')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '导入此版本' })).toBeEnabled()
})

it('编辑候选时提示未保存修改并以候选标识保存', async () => {
  const saved = chain()
  saved.stages[1].draft = { ...saved.stages[1].draft!, attemptId: 'draft-new', content: 'new content' }
  vi.mocked(generationChainApi.saveDraft).mockResolvedValue(saved)
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  expect(screen.queryByRole('button', { name: '编辑产物' })).toBeNull()
  expect(screen.queryByRole('button', { name: '撤销修改' })).toBeNull()
  expect(screen.queryByRole('button', { name: '保存修改' })).toBeNull()
  await user.click(screen.getByRole('radio', { name: 'YAML' }).closest('label')!)
  const editor = await screen.findByRole('textbox', { name: /阶段产物/ })
  expect(editor).toHaveAttribute('aria-readonly', 'false')
  await user.click(editor)
  await user.keyboard('x')
  expect(screen.getByRole('button', { name: '撤销修改' })).toBeEnabled()
  expect(screen.getByRole('button', { name: '保存修改' })).toBeEnabled()
  await user.click(screen.getByRole('button', { name: '撤销修改' }))
  expect(confirm).toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '保存修改' })).toBeEnabled()
  await user.click(screen.getByRole('button', { name: '保存修改' }))
  await waitFor(() => expect(generationChainApi.saveDraft).toHaveBeenCalledWith(
    'req', 'ui', 'ui_design', expect.objectContaining({ expectedAttemptId: 'draft', content: expect.stringContaining('x') }),
  ))
  confirm.mockRestore()
})

it('未保存时阻止页面离开和切换版本，确认后才放弃修改', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  await user.click(screen.getByRole('radio', { name: 'YAML' }).closest('label')!)
  await user.click(await screen.findByRole('textbox', { name: /阶段产物/ }))
  await user.keyboard('x')
  expect(canNavigateAway()).toBe(false)
  const unload = new Event('beforeunload', { cancelable: true })
  expect(window.dispatchEvent(unload)).toBe(false)
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  await user.click(within(inspector).getByRole('button', { name: 'v1' }))
  expect(screen.getByRole('button', { name: '保存修改' })).toBeEnabled()
  confirm.mockReturnValue(true)
  await user.click(within(inspector).getByRole('button', { name: 'v1' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: '保存修改' })).not.toBeInTheDocument())
  expect(canNavigateAway()).toBe(true)
  confirm.mockRestore()
})

it('浏览器后退时取消确认会恢复原历史位置', async () => {
  const previousState = window.history.state
  window.history.replaceState({ ...previousState, idx: 3 }, '')
  const go = vi.spyOn(window.history, 'go').mockImplementation(() => undefined)
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  try {
    mount()
    const user = userEvent.setup()
    await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
    await user.click(screen.getByRole('radio', { name: 'YAML' }).closest('label')!)
    await user.click(await screen.findByRole('textbox', { name: /阶段产物/ }))
    await user.keyboard('x')
    window.dispatchEvent(new PopStateEvent('popstate', { state: { idx: 2 } }))
    expect(confirm).toHaveBeenCalledOnce()
    expect(go).toHaveBeenCalledWith(1)
    expect(screen.getByRole('button', { name: '保存修改' })).toBeEnabled()
  } finally {
    confirm.mockRestore()
    go.mockRestore()
    window.history.replaceState(previousState, '')
  }
})

it('进入和返回阅读区时只为详情栏内容添加轻微过渡', async () => {
  mount()
  const user = userEvent.setup()
  const card = await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' })
  await user.click(card)
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  const header = inspector.querySelector<HTMLElement>('.gc-inspector-header')!
  const animate = vi.fn(() => ({ id: '', cancel: vi.fn() }))
  Object.defineProperty(header, 'animate', { value: animate, configurable: true })
  await user.dblClick(card)
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
  expect(animate).toHaveBeenCalledTimes(1)
  await user.click(within(inspector).getByRole('button', { name: '返回流程' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(animate).toHaveBeenCalledTimes(2)
})

it('返回时等待阅读区收回后恢复原画布', async () => {
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  const reader = await screen.findByRole('dialog')
  const animation = { onfinish: null as (() => void) | null, cancel: vi.fn() }
  const animate = vi.fn(() => animation)
  Object.defineProperty(reader, 'animate', { value: animate, configurable: true })
  await user.click(within(screen.getByRole('complementary', { name: '阶段详情' })).getByRole('button', { name: '返回流程' }))
  expect(animate).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(reader.closest('.gc-canvas-stage')?.querySelector('.gc-canvas-map')).toHaveAttribute('inert')
  act(() => { animation.onfinish?.() })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.getByRole('button', { name: 'UI 用例设计 · 待审核' })).toBeVisible()
})

it('单击切换卡片只更新选中与侧栏，键盘可打开选中阶段', async () => {
  mount()
  const user = userEvent.setup()
  const stage = await screen.findByRole('button', { name: '元素控件清单 · 已通过' })
  await user.click(stage)
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(stage).toHaveAttribute('aria-pressed', 'true')
  expect(within(inspector).getByRole('heading', { name: '元素控件清单' })).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  const risk = screen.getByRole('button', { name: /代码风险分析/ })
  await user.click(risk)
  expect(risk).toHaveAttribute('aria-pressed', 'true')
  expect(stage).toHaveAttribute('aria-pressed', 'false')
  expect(within(inspector).getByRole('heading', { name: '代码风险分析' })).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(stage)
  await user.keyboard('{Enter}')
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
})

it('选择 UI 测试分组才显示源码设置，阶段卡片只显示阶段信息', async () => {
  mount()
  const user = userEvent.setup()
  const stage = await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' })
  await user.click(stage)
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).queryByRole('region', { name: 'UI 测试源码包' })).not.toBeInTheDocument()
  const group = screen.getByRole('button', { name: '选择UI 测试分组' })
  await user.click(group)
  expect(group).toHaveAttribute('aria-pressed', 'true')
  expect(stage).toHaveAttribute('aria-pressed', 'false')
  expect(within(inspector).getByRole('heading', { name: 'UI 测试' })).toBeInTheDocument()
  expect(await within(inspector).findByRole('region', { name: 'UI 测试源码包' })).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(stage)
  expect(group).toHaveAttribute('aria-pressed', 'false')
  expect(within(inspector).queryByRole('region', { name: 'UI 测试源码包' })).not.toBeInTheDocument()
  const container = document.querySelector<HTMLElement>('[data-id="group:ui"] .gc-flow-group')!
  await user.click(container)
  expect(within(inspector).getByRole('region', { name: 'UI 测试源码包' })).toBeInTheDocument()
})

it('UI 测试分组与功能测试使用相同大小', async () => {
  const functional = { ...emptyChain('function', '功能测试'), configured: true, taskId: 'function-task' }
  functional.stages = [
    { stage: 'requirement_analysis', label: '测试需求分析', order: 0, state: 'not_started', versions: [], upstreamStages: [] },
    { stage: 'case_names', label: '测试点', order: 1, state: 'not_started', versions: [], upstreamStages: [] },
    { stage: 'detailed_cases', label: '完整用例', order: 2, state: 'not_started', versions: [], upstreamStages: [] },
  ]
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [functional, chain()] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(chain())
  mount()
  await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' })
  const node = (id: string) => document.querySelector<HTMLElement>(`[data-id="${id}"]`)!
  const ui = node('group:ui')
  const functionalGroup = node('group:function')
  expect(ui.style.width).toBe(functionalGroup.style.width)
  expect(ui.style.height).toBe(functionalGroup.style.height)
  expect(ui.style.width).toBe('594px')
  expect(ui.style.height).toBe('280px')
})

it('单击 API 阶段可在侧栏运行两步生成', async () => {
  const apiChain = { ...emptyChain('api', 'API 测试'), configured: true, taskId: 'api-task' }
  apiChain.stages[0] = { ...apiChain.stages[0], stage: 'openapi_extract', label: '接口配置提取' }
  apiChain.stages.push({ stage: 'generate', label: 'API 用例生成', order: 1, state: 'not_started', versions: [], upstreamStages: ['openapi_extract'], blockedReason: '请先审核通过「接口配置提取」' })
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [apiChain] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(apiChain)
  vi.mocked(generationChainApi.run).mockResolvedValue(apiChain)
  mount()
  const user = userEvent.setup()
  expect(await screen.findByRole('button', { name: 'API 用例生成 · 未开始' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '接口配置提取 · 未开始' }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByText(/提取 OpenAPI 接口配置/)).toBeInTheDocument()
  expect(within(inspector).getByText('OpenAPI 文档')).toBeInTheDocument()
  expect(within(inspector).queryByText('需求材料')).not.toBeInTheDocument()
  await user.click(await within(inspector).findByRole('button', { name: '运行此阶段' }))
  await waitFor(() => expect(generationChainApi.run).toHaveBeenCalledWith('req', 'api', 'openapi_extract', expect.objectContaining({ instruction: '只覆盖登录接口' })))
})

it('API 阶段阻塞时侧栏展示原因并禁止运行', async () => {
  const apiChain = { ...emptyChain('api', 'API 测试'), configured: true, taskId: 'api-task' }
  apiChain.stages[0].label = 'API 用例生成'
  apiChain.stages[0].blockedReason = '请先配置文档'
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [apiChain] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(apiChain)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'API 用例生成 · 未开始' }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(await within(inspector).findByText('请先配置文档')).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: '运行此阶段' })).toBeDisabled()
})

it('未配置 UI 测试时单击入口在侧栏添加源码包', async () => {
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [{ ...chain(), configured: false, taskId: undefined, stages: [], draftCount: 0 }] })
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /开始UI 测试/ }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByRole('heading', { name: 'UI 测试' })).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: '添加源码包' })).toBeInTheDocument()
  expect(within(inspector).getByText('尚未上传源码包')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('API 测试从分组侧栏打开文档编辑弹框并保存', async () => {
  vi.mocked(requirementDesignApi.configure).mockResolvedValue({ taskId: 'api-task' } as never)
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [{ ...emptyChain('api', 'API 测试'), taskId: '' }] })
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /开始API 测试/ }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByText('尚未配置文档')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(within(inspector).getByRole('button', { name: '添加文档' }))
  const dialog = await screen.findByRole('dialog')
  await user.type(within(dialog).getByRole('textbox', { name: 'OpenAPI / Swagger 文档' }), 'openapi: 3.0.0')
  await user.click(within(dialog).getByRole('button', { name: '保存设置' }))
  await waitFor(() => expect(requirementDesignApi.configure).toHaveBeenCalledWith('req', 'api', expect.objectContaining({ sourceContent: 'openapi: 3.0.0' })))
})

it('阅读工具和审核操作在侧栏，视图切换与复制在正文右上角', async () => {
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  const reader = await screen.findByRole('dialog')
  expect(within(inspector).getByRole('button', { name: '审核通过' })).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: '审核不通过' })).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: '继续优化' })).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: /对比/ })).toBeInTheDocument()
  expect(within(inspector).getByRole('group', { name: '侧栏选择版本' })).toBeInTheDocument()
  expect(within(inspector).queryByLabelText('内容展示方式')).not.toBeInTheDocument()
  const toolbar = within(reader).getByRole('toolbar', { name: '阅读视图工具' })
  expect(within(toolbar).getByLabelText('内容展示方式')).toBeInTheDocument()
  expect(within(toolbar).queryByRole('button', { name: /复制/ })).not.toBeInTheDocument()
  await user.click(within(toolbar).getByTitle('YAML'))
  expect(within(toolbar).getByRole('button', { name: '复制 YAML' })).toBeInTheDocument()
  expect(reader.querySelector('.ant-modal-footer')).toBeNull()
  expect(reader.querySelector('.gc-artifact-head')).toBeNull()
  expect(within(inspector).queryByText('基于 v1')).not.toBeInTheDocument()
  expect(within(reader).queryByRole('button', { name: '审核通过' })).not.toBeInTheDocument()
})

it('侧栏展示所选产物对应的运行 ID，切换版本时同步更新，无来源时隐藏', async () => {
  const data = chain()
  data.stages[1].draft!.runId = '01af1479-ec86-4acb-b51d-88b12fcff3da'
  data.stages[1].versions[0].sourceRunId = 'approved-run-id'
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(await within(inspector).findByText('01af1479…f3da')).toHaveAttribute('title', '01af1479-ec86-4acb-b51d-88b12fcff3da')
  await user.click(within(inspector).getByRole('button', { name: 'v1' }))
  expect(await within(inspector).findByText('approved-run-id')).toBeInTheDocument()
  expect(within(inspector).queryByText('01af1479…f3da')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '用例 YAML · 未开始' }))
  await waitFor(() => expect(within(inspector).queryByText('运行 ID')).not.toBeInTheDocument())
})

it('侧栏保留上游选择、版本历史与追溯，阅读区直接展示正文，返回流程位于侧栏', async () => {
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  const reader = await screen.findByRole('dialog')
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(reader).toHaveAccessibleName('UI 用例设计')
  expect(within(inspector).getByRole('button', { name: '返回流程' })).toBeInTheDocument()
  expect(reader.querySelector('.ant-modal-header')).toBeNull()
  expect(reader.querySelector('.ant-modal-content')).toBeNull()
  expect(within(inspector).getByRole('button', { name: /版本 1/ })).toBeInTheDocument()
  expect(within(inspector).getByText('上游追溯')).toBeInTheDocument()
  await user.click(within(inspector).getByRole('button', { name: '选择上游版本' }))
  expect(await screen.findByText('上游 · 元素控件清单')).toBeInTheDocument()
  expect(screen.getByRole('combobox')).toBeInTheDocument()
})

it('其他阶段有待审核产物时仍可重新运行本阶段', async () => {
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  await waitFor(() => expect(within(inspector).getByText('元素控件清单').closest('.gc-trace-chip')).toHaveTextContent('v1'))
  await user.dblClick(await screen.findByRole('button', { name: '元素控件清单 · 已通过' }))
  const dialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  // UI 链仍有「用例 YAML」待审核，但元素控件清单自身没有待审核产物，可以重新运行。
  const run = within(dialog).getByRole('button', { name: '使用原输入重新生成' })
  expect(run).toBeEnabled()
  await user.click(run)
  // 首阶段不能带入此前自动选中的 UI 设计阶段的上游参数。
  await waitFor(() => expect(generationChainApi.run).toHaveBeenCalledWith('req', 'ui', 'ui_surface', expect.objectContaining({ upstreamVersions: {} })))
})

it('最终阶段没有审核通过并继续，版本切换保留可视化与原文开关', async () => {
  const data = chain()
  data.stages[2] = {
    ...data.stages[2], state: 'draft', latestVersion: version('sv-v2', 2),
    draft: {
      attemptId: 'final-draft', runId: 'run', status: 'draft', summary: '2 条用例',
      artifactFormat: 'yaml', content: 'name: 登录\nstepsJson: []',
      revision: 1, baseVersionId: 'sv-v2', baseVersionLabel: 'v2',
      upstreamVersions: { ui_surface: 'sv-v1', ui_design: 'sv-v1' }, createdAt: '2026-10-29T11:00:00Z',
    },
    versions: [version('sv-v2', 2)],
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), data],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: '用例 YAML · 待审核' }))
  const dialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  expect(within(dialog).queryByRole('button', { name: '审核通过并继续' })).not.toBeInTheDocument()

  await user.click(within(dialog).getByRole('button', { name: /^v2/ }))
  await waitFor(() => expect(generationChainApi.version).toHaveBeenCalledWith('req', 'ui', 'sv-v2'))
  await user.click(await within(dialog).findByTitle('YAML'))
  expect(within(dialog).getByRole('textbox', { name: '阶段产物 YAML' })).toHaveTextContent('name: 登录')
})

it('已通过叶子版本可以查看关联阶段和正式来源并导入', async () => {
  const data = chain()
  data.stages[2] = {
    ...data.stages[2], state: 'approved', latestVersion: version('sv-v2', 2),
    draft: {
      attemptId: 'final-draft', runId: 'run', status: 'draft', summary: '2 条用例',
      artifactFormat: 'yaml', content: 'name: 登录\nstepsJson: []',
      revision: 1, baseVersionId: 'sv-v2', baseVersionLabel: 'v2',
      upstreamVersions: { ui_surface: 'sv-v1', ui_design: 'sv-v1' }, createdAt: '2026-10-29T11:00:00Z',
    },
    versions: [version('sv-v2', 2)],
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), data],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: '用例 YAML · 待审核' }))
  const stageDialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  await user.click(within(stageDialog).getByRole('button', { name: /^v2/ }))
  await user.click(within(stageDialog).getByRole('button', { name: '导入此版本' }))
  expect(await screen.findByText('关联阶段')).toBeInTheDocument()
  expect(screen.getByText('正式 UI 套件')).toBeInTheDocument()
  expect(screen.getByText(/当前正式来源 v1/)).toBeInTheDocument()
  const dialogs = screen.getAllByRole('dialog')
  await user.click(within(dialogs[dialogs.length - 1]).getByRole('button', { name: '导入此版本' }))
  await waitFor(() => expect(generationChainApi.importVersion).toHaveBeenCalledWith(
    'req', 'ui', 'sv-v2', { targetId: 'suite', confirmOverwrite: false },
  ))
})

it('导入冲突确认后才覆盖正式用例', async () => {
  vi.mocked(generationChainApi.importVersion)
    .mockResolvedValueOnce({
      requiresConfirmation: true,
      conflicts: [{ normalizedName: 'login works' }],
      imported: false, targetId: 'suite', targetType: 'ui_suite',
      changedCaseIds: [], changedCaseCount: 0, importRecords: [],
    })
    .mockResolvedValueOnce({
      requiresConfirmation: false, conflicts: [], imported: true, targetId: 'suite',
      targetType: 'ui_suite', changedCaseIds: ['case-1'], changedCaseCount: 1,
      importRecords: [],
    })
  const data = chain()
  data.stages[2] = {
    ...data.stages[2], state: 'approved', latestVersion: version('sv-v2', 2),
    draft: null, versions: [version('sv-v2', 2)],
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), data],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: '用例 YAML · 已通过' }))
  const stageDialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  await user.click(within(stageDialog).getByRole('button', { name: '导入此版本' }))
  const dialogs = screen.getAllByRole('dialog')
  const importDialog = dialogs[dialogs.length - 1]
  await user.click(within(importDialog).getByRole('button', { name: '导入此版本' }))
  expect(await screen.findByText('发现 1 个同名正式用例')).toBeInTheDocument()
  await user.click(within(importDialog).getByRole('button', { name: '确认覆盖并导入' }))
  await waitFor(() => expect(generationChainApi.importVersion).toHaveBeenLastCalledWith(
    'req', 'ui', 'sv-v2', { targetId: 'suite', confirmOverwrite: true },
  ))
})

it('上游版本删除后产物显示作废且不再提供审核或继续优化', async () => {
  const data = chain()
  data.draftCount = 0
  data.stages[1] = {
    ...data.stages[1], state: 'approved',
    draft: {
      ...data.stages[1].draft!,
      status: 'invalidated',
      invalidated: true,
      invalidatedReason: '上游版本已删除，请重新生成该阶段',
    },
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), data],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 已作废' }))
  const dialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  expect(within(dialog).getAllByText('产物已作废').length).toBeGreaterThan(0)
  expect(within(dialog).getByText('上游版本已删除，请重新生成该阶段')).toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: '审核通过' })).not.toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: '继续优化' })).not.toBeInTheDocument()
  expect(within(dialog).getByRole('button', { name: '重新生成此阶段' })).toBeInTheDocument()
})

it('待审核产物可以打开继续优化侧栏并提交修订指令', async () => {
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  const dialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  await user.click(within(dialog).getByRole('button', { name: '继续优化' }))
  expect(within(dialog).getByRole('complementary', { name: '继续优化' })).toBeInTheDocument()
  await user.type(within(dialog).getByRole('textbox', { name: '优化指令' }), '补充失败重试')
  await user.click(within(dialog).getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(generationChainApi.revise).toHaveBeenCalledWith('req', 'ui', 'ui_design', {
    connectionId: 'llm', instruction: '补充失败重试', requestId: expect.any(String),
  }))
})

it('生成链继续优化把上传的截图随本轮指令提交', async () => {
  const upload = vi.spyOn(storedFiles, 'uploadStoredFile').mockResolvedValue('revision-image')
  const download = vi.spyOn(storedFiles, 'downloadStoredFile').mockResolvedValue({ blob: new Blob(['png']), filename: 'switch.png' })
  const createUrl = URL.createObjectURL
  const revokeUrl = URL.revokeObjectURL
  URL.createObjectURL = vi.fn(() => 'blob:revision-image')
  URL.revokeObjectURL = vi.fn()
  try {
    mount()
    const user = userEvent.setup()
    await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
    await user.click(await screen.findByRole('button', { name: '继续优化' }))
    await user.upload(document.querySelector('.revision-side-panel input[type="file"]') as HTMLInputElement,
      new File(['png'], 'switch.png', { type: 'image/png' }))
    expect(await screen.findByAltText('switch.png')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: '优化指令' }), '按截图补充')
    await user.click(screen.getByRole('button', { name: '提交优化' }))
    await waitFor(() => expect(generationChainApi.revise).toHaveBeenCalledWith('req', 'ui', 'ui_design', {
      connectionId: 'llm', instruction: '按截图补充', requestId: expect.any(String), attachmentFileIds: ['revision-image'],
    }))
  } finally {
    cleanup()
    upload.mockRestore()
    download.mockRestore()
    URL.createObjectURL = createUrl
    URL.revokeObjectURL = revokeUrl
  }
})

it('需求分析第一阶段沿用材料提取结果的对照阅读', async () => {
  const data: GenerationChain = {
    kind: 'requirement_analysis', label: '需求分析', configured: true, taskId: 'task', runId: 'run',
    active: false, busy: false, sourceChanged: false, draftCount: 1,
    stages: [
      {
        stage: 'extracting_text', label: '提取与整理', order: 0, state: 'draft', latestVersion: null,
        draft: {
          attemptId: 'extract-draft', runId: 'run', status: 'draft',
          summary: '1 个材料来源 · 4 条提取事实', artifactFormat: 'json',
          content: extractionSource, revision: 1, createdAt: '2026-10-30T09:00:00Z',
        },
        versions: [], upstreamStages: [],
      },
      { stage: 'feature_understanding', label: '需求理解与确认', order: 1, state: 'not_started', latestVersion: null, draft: null, versions: [], upstreamStages: [] },
    ],
    leaf: {},
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [data, emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), chain()],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: '提取与整理 · 待审核' }))
  const dialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  expect(document.querySelector('.gc-artifact-scroll')).toHaveClass('is-material-comparison')
  expect(within(dialog).queryByRole('region', { name: '材料内容' })).not.toBeInTheDocument()
  expect(within(dialog).getByRole('region', { name: '提取事实' })).toBeInTheDocument()

  await user.click(within(dialog).getByTitle('JSON'))
  expect(within(dialog).queryByRole('region', { name: '材料内容' })).not.toBeInTheDocument()
  expect(within(dialog).getByRole('textbox', { name: '阶段产物 JSON' })).toHaveTextContent('"artifactType": "document_extraction"')
})

function draftStage(stage: string, label: string, order: number, content: string, upstreamVersions: Record<string, string> = {}, upstreamStages: string[] = []): GenerationChainStage {
  return {
    stage, label, order, state: 'draft', latestVersion: null,
    draft: {
      attemptId: `${stage}-draft`, runId: 'run', status: 'draft', summary: '草稿',
      artifactFormat: 'json', content, revision: 1, upstreamVersions, createdAt: '2026-10-30T09:00:00Z',
    },
    versions: [], upstreamStages,
  }
}

function chainWith(kind: GenerationChain['kind'], label: string, stages: GenerationChainStage[]): GenerationChain {
  return {
    kind, label, configured: true, taskId: `task-${kind}`, runId: `run-${kind}`,
    active: false, busy: false, sourceChanged: false, draftCount: stages.length, stages, leaf: {},
  }
}

it.each([
  ['extracting_text', '提取与整理', extractionSource, '材料提取结果'],
  ['feature_understanding', '需求理解', understandingSource, '需求理解记录'],
])('继续优化预填待确认问题并保留取消后的填写：%s', async (stageName, label, content, templateLabel) => {
  const data = chainWith('requirement_analysis', '需求分析', [draftStage(stageName, label, 0, content)])
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: `${label} · 待审核` }))
  await user.click(await screen.findByRole('button', { name: '继续优化' }))
  const instruction = await screen.findByRole('textbox', { name: '优化指令' })
  const template = buildRevisionTemplate(getRevisionQuestions(content), templateLabel, '答复')
  expect(template).not.toBe('')
  expect(instruction).toHaveValue(template)
  expect(instruction.closest('.revision-side-panel')?.parentElement).toHaveClass('gc-workspace', 'is-revising')
  expect(screen.getByRole('button', { name: '添加图片' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '提交优化' }))
  expect(await screen.findByText('请补充已确认的信息，或填写其他优化要求')).toBeInTheDocument()
  expect(generationChainApi.revise).not.toHaveBeenCalled()
  await waitFor(() => expect(screen.getByRole('textbox', { name: '优化指令' })).toBeEnabled())
  await user.clear(screen.getByRole('textbox', { name: '优化指令' }))
  await user.type(screen.getByRole('textbox', { name: '优化指令' }), '默认开关开启')
  await user.click(screen.getByRole('button', { name: '取消优化' }))
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  expect(screen.getByRole('textbox', { name: '优化指令' })).toHaveValue('默认开关开启')
})

/** 每次重新挂载工作区并打开指定阶段，避免依赖弹框关闭动画。 */
async function openStage(label: string) {
  cleanup()
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: `${label} · 待审核` }))
  return { user, dialog: (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement }
}

it('需求理解阶段沿用需求理解记录的材料对照视图并读取上游材料', async () => {
  const understanding = {
    schemaVersion: '2.0', artifactType: 'requirement_understanding', title: '测试需求理解', sources: [], evidence: [],
    functionalOverview: { purpose: '完成转换数据导出' }, businessFlows: [], modules: [], businessRules: [], questions: [],
  }
  const data = chainWith('requirement_analysis', '需求分析', [
    draftStage('extracting_text', '提取与整理', 0, extractionSource),
    draftStage('feature_understanding', '需求理解', 1, JSON.stringify(understanding), { extracting_text: 'v-extract' }, ['extracting_text']),
  ])
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [data, emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), chain()],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(generationChainApi.version).mockResolvedValue({
    versionId: 'v-extract', kind: 'requirement_analysis', stage: 'extracting_text', stageLabel: '提取与整理', versionNo: 1,
    label: 'v1', summary: '材料提取', artifactFormat: 'json', content: extractionSource,
    reviewerUserId: 'u', reviewedAt: null, reviewComment: '', upstreamVersions: {}, upstream: [],
  })

  const { user, dialog } = await openStage('需求理解')
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  const reader = within(dialog).getByRole('dialog')
  expect(within(inspector).queryByRole('button', { name: /材料／依据/ })).not.toBeInTheDocument()
  expect(within(reader).queryByRole('region', { name: '材料内容' })).not.toBeInTheDocument()
  expect(within(dialog).getByRole('region', { name: '需求理解内容' })).toBeInTheDocument()
  await user.click(within(dialog).getByRole('tab', { name: '功能概况' }))
  expect(within(dialog).getByText('完成转换数据导出')).toBeInTheDocument()
  expect(generationChainApi.version).not.toHaveBeenCalledWith('req', 'requirement_analysis', 'v-extract')
})

it('功能测试各阶段沿用页签的测试需求分析、测试点与完整用例视图', async () => {
  const analysis = { Platform_core_functions: [{ function: '导出转换数据', description: '选择类型导出', business_value: '提升效率' }] }
  const points = { categories: [{ name: '导出', data: [{ test_model: '正常导出', test_points: ['导出成功'] }] }] }
  const cases = { cases: [{ case_module: '导出', case_name: '导出成功', priority: 'P0', steps: '1. 点击导出', expected: '成功' }] }
  const data = chainWith('function', '功能测试', [
    draftStage('requirement_analysis', '测试需求分析', 0, JSON.stringify(analysis)),
    draftStage('case_names', '测试点', 1, JSON.stringify(points), { requirement_analysis: 'v-func-analysis' }, ['requirement_analysis']),
    draftStage('detailed_cases', '完整用例', 2, JSON.stringify(cases), { requirement_analysis: 'v-func-analysis', case_names: 'v-case-names' }, ['requirement_analysis', 'case_names']),
  ])
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), data, emptyChain('api', 'API 测试'), chain()],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(generationChainApi.version).mockImplementation(async (_requirementId, kind, versionId) => ({
    versionId, kind, stage: 'case_names', stageLabel: '测试点', versionNo: 1, label: 'v1', summary: '上游',
    artifactFormat: 'json', content: versionId === 'v-case-names' ? JSON.stringify(points) : JSON.stringify(analysis),
    reviewerUserId: 'u', reviewedAt: null, reviewComment: '', upstreamVersions: {}, upstream: [],
  }))

  const analysisView = await openStage('测试需求分析')
  expect(within(analysisView.dialog).getByRole('button', { name: /平台核心功能/ })).toBeInTheDocument()

  const pointsView = await openStage('测试点')
  expect(within(pointsView.dialog).getByRole('button', { name: /保存图片/ })).toBeInTheDocument()
  expect(within(pointsView.dialog).getByText('正常导出')).toBeInTheDocument()

  const casesView = await openStage('完整用例')
  expect(casesView.dialog.querySelector('.ai-generated-case-browser')).not.toBeNull()
  expect(within(casesView.dialog).getAllByText('导出成功').length).toBeGreaterThan(0)
  // 图谱是「完整用例」之后的独立派生节点，不再放进阶段弹框。
  expect(within(casesView.dialog).queryByRole('button', { name: '用例图谱' })).not.toBeInTheDocument()
  await casesView.user.click(within(casesView.dialog).getByRole('button', { name: '返回流程' }))
  await casesView.user.dblClick(await screen.findByRole('button', { name: '用例图谱 · 派生' }))
  const generateGraph = await screen.findByRole('button', { name: '生成图谱' })
  await casesView.user.click(generateGraph)
  await waitFor(() => expect(aiTestingApi.generateFunctionalCaseRelationAnalysis).toHaveBeenCalledWith('run', 'llm'))
})

it('用例图谱节点使用完整用例已通过版本的来源运行', async () => {
  const cases = { cases: [{ case_module: '导出', case_name: '导出成功', priority: 'P0', steps: '1. 点击导出', expected: '成功' }] }
  const approved = { ...version('func-cases-v1', 1, 'run-version'), summary: '1 条用例' }
  const data = chainWith('function', '功能测试', [
    draftStage('requirement_analysis', '测试需求分析', 0, '{}'),
    {
      stage: 'detailed_cases', label: '完整用例', order: 1, state: 'approved',
      latestVersion: approved, draft: null, versions: [approved], upstreamStages: [],
    },
  ])
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), data, emptyChain('api', 'API 测试'), chain()],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(generationChainApi.version).mockResolvedValue({
    versionId: 'func-cases-v1', kind: 'function', stage: 'detailed_cases', stageLabel: '完整用例',
    versionNo: 1, label: 'v1', summary: '1 条用例', artifactFormat: 'json', content: JSON.stringify(cases),
    reviewerUserId: 'u', reviewedAt: null, reviewComment: '', upstreamVersions: {}, upstream: [],
  })
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: '用例图谱 · 派生' }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  const dialog = await screen.findByRole('dialog', { name: '用例图谱' })
  expect(dialog.querySelector('.ant-modal-header')).toBeNull()
  expect(dialog.querySelector('.ai-relations-page-bar')).toBeNull()
  expect(dialog.querySelector('.gc-relations-toolbar')).toBeNull()
  expect(within(inspector).getByRole('button', { name: '返回流程' })).toBeInTheDocument()
  expect(within(inspector).getByRole('heading', { name: '阅读工具' })).toBeInTheDocument()
  await user.click(await within(inspector).findByRole('button', { name: '生成图谱' }))
  await waitFor(() => expect(aiTestingApi.generateFunctionalCaseRelationAnalysis).toHaveBeenCalledWith('run-version', 'llm'))
})

it('完整用例还没有运行记录时不显示用例图谱节点', async () => {
  const data = chainWith('function', '功能测试', [
    draftStage('requirement_analysis', '测试需求分析', 0, '{}'),
    {
      stage: 'detailed_cases', label: '完整用例', order: 1, state: 'not_started',
      latestVersion: null, draft: null, versions: [], upstreamStages: ['requirement_analysis'],
    },
  ])
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), data, emptyChain('api', 'API 测试'), chain()],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  expect(await screen.findByRole('button', { name: /^完整用例 · / })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '用例图谱 · 派生' })).not.toBeInTheDocument()
})

it('API 提取审核通过并继续时向下一阶段传递生成要求', async () => {
  const apiData = chainWith('api', 'API 测试', [
    draftStage('openapi_extract', '接口配置提取', 0, '{"login":{"path":"/login","method":"POST"}}'),
    { stage: 'generate', label: 'API 用例生成', order: 1, state: 'not_started', versions: [], upstreamStages: ['openapi_extract'] },
  ])
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [apiData] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(apiData)
  vi.mocked(generationChainApi.review).mockResolvedValue(apiData)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: '接口配置提取 · 待审核' }))
  await user.click(await screen.findByRole('button', { name: /审核通过并继续/ }))
  await waitFor(() => expect(generationChainApi.review).toHaveBeenCalledWith('req', 'api', 'openapi_extract', expect.objectContaining({ continueAfter: true, instruction: '只覆盖登录接口' })))
})

it('API 与 UI 阶段沿用页签的接口链路和 UI 三阶段工作台', async () => {
  const apiData = chainWith('api', 'API 测试', [
    draftStage('generate', 'API 用例生成', 0, '- name: 查询任务\n  method: GET\n  path: /api/tasks\n'),
  ])
  const uiData = chainWith('ui', 'UI 测试', [
    draftStage('ui_surface', '元素控件清单', 0, JSON.stringify({ schemaVersion: 'ui_test_surface/1.0', pages: [] })),
  ])
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), emptyChain('function', '功能测试'), apiData, uiData],
  })
  vi.mocked(generationChainApi.chain).mockImplementation(async (_requirementId, kind) => kind === 'api' ? apiData : kind === 'ui' ? uiData : chain())

  const apiView = await openStage('API 用例生成')
  expect(apiView.dialog.querySelector('.api-config-visual-view')).not.toBeNull()
  expect(within(apiView.dialog).getByText('接口 1')).toBeInTheDocument()

  const uiView = await openStage('元素控件清单')
  expect(uiView.dialog.querySelector('.gc-artifact-scroll.is-ui-stage .ui-generation-stage-visual')).not.toBeNull()
})

it('阅读时侧栏切换版本同步更新正文，返回流程后可再次打开', async () => {
  mount()
  const user = userEvent.setup()
  const node = await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' })
  await user.dblClick(node)
  expect(node).toHaveAttribute('aria-pressed', 'true')
  expect(await screen.findByRole('dialog')).toHaveAttribute('aria-modal', 'false')
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  // 阶段名与状态在标题栏，摘要仅保留产物概述，版本由下方按钮的选中状态表示。
  expect(within(inspector).getByRole('heading', { name: 'UI 用例设计' })).toBeInTheDocument()
  expect(within(inspector).queryByText('所属阶段')).not.toBeInTheDocument()
  expect(within(inspector).queryByText('当前状态')).not.toBeInTheDocument()
  expect(within(inspector).queryByText('当前版本')).not.toBeInTheDocument()
  // 追溯显示待审核产物实际引用的上游版本。
  expect(within(inspector).getByText('上游追溯')).toBeInTheDocument()
  expect(within(inspector).getByText('元素控件清单').closest('.gc-trace-chip')).toHaveTextContent('v1')
  const versions = within(inspector).getByRole('group', { name: '侧栏选择版本' })
  expect(within(versions).getByRole('button', { name: '待审核' })).toHaveAttribute('aria-pressed', 'true')
  await user.click(within(versions).getByRole('button', { name: 'v1' }))
  expect(within(versions).getByRole('button', { name: 'v1' })).toHaveAttribute('aria-pressed', 'true')
  expect(within(inspector).queryByRole('button', { name: '对比上一版' })).not.toBeInTheDocument()
  const dialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  expect(await within(dialog).findByRole('button', { name: /^v1/ })).toHaveAttribute('aria-pressed', 'true')
  await waitFor(() => expect(generationChainApi.version).toHaveBeenCalledWith('req', 'ui', 'sv-v1'))
  await user.click(within(dialog).getByRole('button', { name: '返回流程' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.dblClick(node)
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
})

it('画布不再显示缩放按钮、比例和适应画布入口', async () => {
  mount()
  await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' })
  expect(screen.queryByRole('group', { name: '画布缩放' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '放大画布' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '缩小画布' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '适应画布' })).not.toBeInTheDocument()
  expect(screen.queryByRole('group', { name: '筛选生成链' })).not.toBeInTheDocument()
})

it('需求分析连接 API 和 UI，初始分组不重叠', async () => {
  const analysis = { ...emptyChain('requirement_analysis', '需求分析'), configured: true }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [analysis, emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), chain()],
  })
  mount()
  await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' })
  await waitFor(() => {
    expect(document.querySelector('[aria-label="Edge from requirement_analysis:extracting_text to group:api"]')).toBeInTheDocument()
    expect(document.querySelector('[aria-label="Edge from requirement_analysis:extracting_text to ui:ui_surface"]')).toBeInTheDocument()
  })
  const api = document.querySelector<HTMLElement>('[data-id="group:api"]')!
  const ui = document.querySelector<HTMLElement>('[data-id="group:ui"]')!
  const y = (node: HTMLElement) => Number(node.style.transform.match(/,\s*([\d.]+)px\)/)?.[1])
  expect(y(ui)).toBeGreaterThan(y(api) + Number.parseFloat(api.style.height))
})

it('UI 首阶段运行先选择源码和功能用例，再把所选编号传给生成链', async () => {
  const data: GenerationChain = {
    kind: 'ui', label: 'UI 测试', configured: true, taskId: 'task', draftCount: 0,
    stages: [{ stage: 'ui_surface', label: '元素控件清单', order: 0, state: 'not_started', versions: [], upstreamStages: [] }], leaf: {},
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(generationChainApi.run).mockResolvedValue(data)
  vi.mocked(aiTestingApi.getUiCaseGenerateTask).mockResolvedValue({ name: 'UI', sourceType: 'source_archive', instruction: '',
    sourceArchive: { archiveId: 'a', fileId: 'file', filename: 'source.zip', sizeBytes: 2, sha256: '', uploadedAt: '' } })
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const path = new URL(String(input), 'http://localhost').pathname
    const rows = path.endsWith('/function-test-suites') ? [{ suiteId: 'suite', name: '功能' }]
      : [{ caseId: 'c1', title: '转换成功' }, { caseId: 'c2', title: '转换失败' }]
    return new Response(JSON.stringify({ code: 0, data: { items: rows, total: rows.length } }), { headers: { 'Content-Type': 'application/json' } })
  })
  try {
    mount()
    const user = userEvent.setup()
    await user.dblClick(await screen.findByRole('button', { name: '元素控件清单 · 未开始' }))
    const runButton = await screen.findByRole('button', { name: '运行此阶段' })
    expect(runButton).toBeEnabled()
    await user.click(runButton)
    expect(generationChainApi.run).not.toHaveBeenCalled()
    const inputDialog = (await screen.findByText('选择 UI 生成输入')).closest('[role=dialog]') as HTMLElement
    await waitFor(() => expect(within(inputDialog).getByRole('button', { name: '开始生成' })).toBeEnabled())
    await user.click(within(inputDialog).getByRole('checkbox', { name: '选择用例：转换失败' }))
    await user.click(within(inputDialog).getByRole('button', { name: '开始生成' }))
    await waitFor(() => expect(generationChainApi.run).toHaveBeenCalledWith('req', 'ui', 'ui_surface', expect.objectContaining({
      connectionId: 'llm', refreshInputs: false, functionCaseIds: ['c1'], requestId: expect.any(String),
    })))
  } finally { fetchSpy.mockRestore() }
})

it('审核不通过后移除待审核候选，保留历史版本并允许重新生成', async () => {
  const original = chain()
  const discarded: GenerationChain = {
    ...original, draftCount: 0,
    stages: original.stages.map(stage => stage.stage === 'ui_design' ? { ...stage, state: 'approved', draft: null } : stage),
  }
  vi.mocked(generationChainApi.review).mockImplementation(async () => {
    vi.mocked(generationChainApi.chain).mockResolvedValue(discarded)
    return discarded
  })
  const { user, dialog } = await openStage('UI 用例设计')
  expect(within(dialog).queryByRole('textbox', { name: '审核备注' })).not.toBeInTheDocument()
  await user.click(within(dialog).getByRole('button', { name: '审核不通过' }))
  await waitFor(() => expect(within(dialog).queryByRole('button', { name: '审核不通过' })).not.toBeInTheDocument())
  expect(within(dialog).queryByText('已丢弃')).not.toBeInTheDocument()
  expect(within(dialog).queryByText('审核未通过，候选产物已丢弃')).not.toBeInTheDocument()
  expect(dialog.querySelector('.gc-inspector-header .gc-state')).toHaveTextContent('已通过')
  expect(generationChainApi.review).toHaveBeenCalledWith('req', 'ui', 'ui_design', { action: 'reject', expectedAttemptId: 'draft', continueAfter: false })
  const versions = within(dialog).getByRole('group', { name: '侧栏选择版本' })
  expect(within(versions).queryByRole('button', { name: '待审核' })).not.toBeInTheDocument()
  expect(within(versions).getByRole('button', { name: /^v1/ })).toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: '继续优化' })).not.toBeInTheDocument()
  expect(within(dialog).queryByRole('button', { name: '审核通过' })).not.toBeInTheDocument()
  expect(within(dialog).getByRole('button', { name: '按所选上游重新生成' })).toBeEnabled()
})

it('运行中节点优先显示加载状态，保留旧草稿时也不显示为待审核', async () => {
  const data = chain()
  data.stages = data.stages.map(stage => stage.stage === 'ui_design' ? { ...stage, state: 'running' } : stage)
  data.active = data.busy = true
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const running = await screen.findByRole('button', { name: 'UI 用例设计 · 运行中' })
  expect(running).toHaveClass('is-running')
  expect(running).toHaveAttribute('aria-busy', 'true')
  expect(running.querySelector('.gc-running-indicator')).not.toBeNull()
  expect(screen.queryByRole('button', { name: 'UI 用例设计 · 待审核' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '元素控件清单 · 已通过' }).querySelector('.gc-running-indicator')).toBeNull()
})


it('运行光束只到紧邻下游，运行结束后恢复普通连线', async () => {
  const data = chain()
  data.stages = data.stages.map((stage, index) => index === 0 ? { ...stage, state: 'running' } : stage)
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  await screen.findByRole('button', { name: '元素控件清单 · 运行中' })
  await waitFor(() => expect(document.querySelector('[data-testid="rf__edge-ui:1"] .gc-flow-edge-output')).not.toBeNull())
  expect(document.querySelector('[data-testid="rf__edge-ui:2"] .gc-flow-edge-output')).toBeNull()
  expect(document.querySelector('[data-testid="rf__edge-ui:2"] .gc-flow-edge-stream')).not.toBeNull()
  const completed = { ...data, stages: data.stages.map((stage, index) => index === 0 ? { ...stage, state: 'approved' as const } : stage) }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [completed] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(completed)
  await act(async () => { await clients.at(-1)!.invalidateQueries({ queryKey: ['generationChain', 'req'] }) })
  await waitFor(() => expect(document.querySelector('.gc-flow-edge-output')).toBeNull())
  expect(document.querySelector('[data-testid="rf__edge-ui:1"] .gc-flow-edge-stream')).not.toBeNull()
})

it('后续阶段运行时可审核前序候选，并允许尝试继续', async () => {
  const running = chain()
  running.active = true
  running.busy = true
  running.stages[2] = { ...running.stages[2], state: 'running', activeRunId: 'run' }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [running] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(running)
  mount()
  const user = userEvent.setup()
  await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  const dialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  expect(within(dialog).getByRole('button', { name: /^审核通过$/ })).toBeEnabled()
  expect(within(dialog).getByRole('button', { name: '审核不通过' })).toBeEnabled()
  expect(within(dialog).getByRole('button', { name: /审核通过并继续/ })).toBeEnabled()
  expect(within(dialog).getByRole('button', { name: '继续优化' })).toBeEnabled()
  await user.click(within(dialog).getByRole('button', { name: /^审核通过$/ }))
  await waitFor(() => expect(generationChainApi.review).toHaveBeenCalledWith(
    'req', 'ui', 'ui_design', { action: 'approve', expectedAttemptId: 'draft', continueAfter: false },
  ))
})

it('需求文档直接占满画布阅读区，侧栏保持可见，返回后保留流程', async () => {
  mount(<div>需求文档阅读内容</div>)
  const user = userEvent.setup()
  const card = await screen.findByRole('button', { name: /查看需求文档/ })
  await user.click(card)
  expect(card).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(within(screen.getByRole('complementary', { name: '阶段详情' })).getByRole('heading', { name: '需求文档' })).toBeInTheDocument()
  await user.dblClick(card)
  const document = await screen.findByRole('dialog', { name: '需求文档' })
  expect(document).toHaveAttribute('aria-modal', 'false')
  expect(document.closest('.gc-canvas-stage')).not.toBeNull()
  expect(within(document).getByText('需求文档阅读内容')).toBeInTheDocument()
  expect(screen.getByRole('complementary', { name: '阶段详情' })).toBeVisible()
  await user.click(within(document).getByRole('button', { name: '返回流程' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /查看需求文档/ })).toBeInTheDocument()
})

it('隐藏期间延迟尺寸通知，返回流程后已测量节点仍可见', async () => {
  const OriginalObserver = globalThis.ResizeObserver
  vi.stubGlobal('ResizeObserver', class extends OriginalObserver {
    constructor(callback: ResizeObserverCallback) {
      super((entries, observer) => {
        const visibleEntries = entries.filter(entry => !entry.target.closest('.gc-canvas-map[inert]'))
        if (visibleEntries.length) callback(visibleEntries, observer)
      })
    }
  })
  try {
    mount()
    const user = userEvent.setup()
    await user.dblClick(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: '返回流程' }))
    await waitFor(() => {
      const nodes = document.querySelectorAll<HTMLElement>('.react-flow__node')
      expect(nodes.length).toBeGreaterThan(0)
      for (const node of nodes) expect(node).toBeVisible()
    })
  } finally {
    vi.stubGlobal('ResizeObserver', OriginalObserver)
  }
})
