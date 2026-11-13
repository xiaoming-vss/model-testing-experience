import readableSource from '@/domain/requirements/fixtures/readable-material.example.json?raw'
import extractionSource from '@/domain/requirements/fixtures/document-extraction.example.json?raw'
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
import { repositoryProfileApi } from '../api/repositoryProfile.api'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import type { GenerationChain, GenerationChainStage, UiGenerationSourceOptions } from '../api/generationChain.api'
import { RequirementDesignWorkspace } from './RequirementDesignWorkspace'

vi.mock('../api/requirementDesign.api', () => ({
  requirementDesignApi: { overview: vi.fn(), history: vi.fn(), start: vi.fn(), configure: vi.fn() },
}))

vi.mock('../api/generationChain.api', () => ({
  generationChainApi: {
    overview: vi.fn(), chain: vi.fn(), version: vi.fn(), run: vi.fn(),
    revise: vi.fn(), review: vi.fn(), saveDraft: vi.fn(), deleteVersion: vi.fn(),
    importOptions: vi.fn(), importVersion: vi.fn(), uiSourceOptions: vi.fn(), uiSourceCheck: vi.fn(),
  },
}))
vi.mock('../api/aiTesting.api', () => ({
  aiTestingApi: {
    getFunctionalCaseGenerateTaskRun: vi.fn(), getFunctionalCaseGenerateTask: vi.fn(),
    getUiCaseGenerateTask: vi.fn(), getApiCaseGenerateTask: vi.fn(),
    generateFunctionalCaseRelationAnalysis: vi.fn(async (runId: string) => ({ runId })),
  },
}))
vi.mock('../api/repositoryProfile.api', () => ({
  repositoryProfileApi: {
    getRepositoryProfileTasks: vi.fn(),
    createRepositoryProfileTask: vi.fn(),
    runRepositoryProfileTask: vi.fn(),
    getRepositoryProfileTaskRuns: vi.fn(),
    getRepositoryProfileRun: vi.fn(),
    getRepositoryProfileVersions: vi.fn(),
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
const readingActionHosts: HTMLElement[] = []
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
afterEach(() => { cleanup(); readingActionHosts.splice(0).forEach(host => host.remove()); clients.forEach(client => client.clear()); clients.length = 0; vi.clearAllMocks() })

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

function sourceOptions(): UiGenerationSourceOptions {
  return {
    defaultProfileVersionId: 'profile-v2',
    profileVersions: [
      {
        versionId: 'profile-v2', versionNo: 2, label: 'v2',
        createdAt: '2026-11-09T10:00:00Z',
        requirementMaterialVersion: { versionId: 'sv-extract-1', versionNo: 1 },
        repositories: [{
          repositoryId: 'repo-web', pathWithNamespace: 'team/web', role: 'frontend',
          confidence: 0.92, responsibilitySummary: '管理端前端', keyPaths: ['src'],
          branch: 'main', commit: 'a1b2c3d4', isFrontend: true, available: true, profileError: '',
        }],
      },
      {
        versionId: 'profile-v1', versionNo: 1, label: 'v1',
        createdAt: '2026-11-08T10:00:00Z',
        repositories: [{
          repositoryId: 'repo-old', pathWithNamespace: 'team/old-web', role: 'fullstack',
          confidence: 0.8, responsibilitySummary: '旧管理端', keyPaths: ['app'],
          branch: 'release', commit: '9999999', isFrontend: true, available: true, profileError: '',
        }],
      },
    ],
  }
}

function mount(documentPreview?: import('react').ReactNode, onReadingNodeChange?: Parameters<typeof RequirementDesignWorkspace>[0]['onReadingNodeChange'], inspectorHost?: HTMLElement | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  // 阅读态的视图切换与复制走页面标题栏插槽，测试中提供与真实页面等价的宿主节点。
  const readingActionsHost = document.createElement('div')
  readingActionsHost.dataset.testid = 'reading-actions'
  document.body.appendChild(readingActionsHost)
  readingActionHosts.push(readingActionsHost)
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter>
    <RequirementDesignWorkspace requirementId="req" projectId="project" canWrite documentPreview={documentPreview} onReadingNodeChange={onReadingNodeChange} inspectorHost={inspectorHost} readingActionsHost={readingActionsHost} />
  </MemoryRouter></QueryClientProvider></TestThemeProvider>)
}

it('功能测试默认使用最新材料整理，也能选择历史版本', async () => {
  const functional = emptyChain('function', '功能测试')
  functional.configured = true
  functional.taskId = 'function-task'
  functional.stages[0].label = '测试范围风险分析'
  functional.stages[0].upstreamStages = ['extracting_text']
  const analysis = emptyChain('requirement_analysis', '需求分析')
  analysis.configured = true
  const old = { ...version('material-v1', 1), stage: 'extracting_text', summary: '旧材料整理' }
  const latest = { ...version('material-v2', 2), stage: 'extracting_text', summary: '新材料整理' }
  analysis.stages = [{
    stage: 'extracting_text', label: '材料整理', order: 0,
    state: 'approved', latestVersion: latest, versions: [latest, old], upstreamStages: [],
  }]
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [analysis, functional] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(functional)
  vi.mocked(generationChainApi.run).mockResolvedValue(functional)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '测试范围风险分析 · 未开始' }))
  const selector = await screen.findByRole('button', { name: '选择上游版本' })
  await waitFor(() => expect(selector).toHaveTextContent('材料整理 v2'))
  await user.click(selector)
  await user.click(await screen.findByRole('combobox', { name: '上游 · 材料整理' }))
  await user.click(await screen.findByText('v1 · 旧材料整理 · 历史'))
  await user.click(selector)
  await user.click(await screen.findByRole('button', { name: '运行此阶段' }))
  await waitFor(() => expect(generationChainApi.run).toHaveBeenCalledWith(
    'req', 'function', 'requirement_analysis', expect.objectContaining({
      upstreamVersions: { extracting_text: 'material-v1' },
    }),
  ))
})

beforeEach(() => {
  vi.mocked(aiTestingApi.getUiCaseGenerateTask).mockResolvedValue({ name: 'UI', sourceType: 'repository', instruction: '' })
  vi.mocked(generationChainApi.uiSourceOptions).mockResolvedValue(sourceOptions())
  vi.mocked(generationChainApi.uiSourceCheck).mockResolvedValue({
    pinnedCommit: 'a1b2c3d4', currentCommit: 'a1b2c3d4', branch: 'main', changed: false,
  })
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const path = new URL(String(input), 'http://localhost').pathname
    const rows = path.endsWith('/function-test-suites') ? [{ suiteId: 'suite', name: '功能' }]
      : [{ caseId: 'c1', title: '转换成功' }, { caseId: 'c2', title: '转换失败' }]
    return new Response(JSON.stringify({ code: 0, data: { items: rows, total: rows.length } }), { headers: { 'Content-Type': 'application/json' } })
  })
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({
    tasks: [], runCounts: { requirement_analysis: 0, function: 0, api: 0, ui: 0 },
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

it('单击直接在画布内打开阶段产物', async () => {
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

it('阶段侧栏渲染到页面级独立容器，不放进画布大容器', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  try {
    mount(undefined, undefined, host)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
    const inspector = await screen.findByRole('complementary', { name: '阶段详情' })
    expect(host.contains(inspector)).toBe(true)
    expect(inspector.closest('.gc-canvas-workspace')).toBeNull()
    expect(inspector.closest('.requirement-detail-main')).toBeNull()
  } finally { host.remove() }
})

it('阅读时可收起和展开侧栏，保留当前阶段及阅读内容', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  try {
    mount(undefined, undefined, host)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
    const inspector = await screen.findByRole('complementary', { name: '阶段详情' })
    const toggle = screen.getByRole('button', { name: '收起阶段详情' })
    expect(toggle).toHaveAttribute('aria-controls', inspector.id)
    await user.click(toggle)
    expect(screen.getByRole('button', { name: '展开阶段详情' })).toHaveAttribute('aria-expanded', 'false')
    expect(host.querySelector('.gc-inspector-drawer.is-collapsed .gc-inspector-rail')).toBeInTheDocument()
    expect(inspector).toHaveAttribute('aria-hidden', 'true')
    expect(inspector).toHaveAttribute('inert')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '展开阶段详情' }))
    expect(screen.getByRole('button', { name: '收起阶段详情' })).toHaveAttribute('aria-expanded', 'true')
    expect(within(inspector).getByRole('heading', { name: 'UI 用例设计' })).toBeInTheDocument()
    expect(within(inspector).getByRole('button', { name: '返回流程' })).toBeEnabled()
  } finally { host.remove() }
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
  await user.click(screen.getByRole('button', { name: '元素控件清单 · 执行失败' }))
  expect(await screen.findAllByText('阶段执行失败，Worker 未返回具体原因')).toHaveLength(2)
})




it('审核通过后下一阶段未启动时提示已通过和具体原因', async () => {
  const warning = vi.spyOn(message, 'warning')
  vi.mocked(generationChainApi.review).mockResolvedValue({ ...chain(), continuationError: '下一阶段已有待审核产物' })
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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
  await user.click(await screen.findByRole('button', { name: '用例 YAML · 已通过' }))
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
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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
    await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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

it('单击打开阅读区，返回后收起详情栏', async () => {
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
  await user.click(within(screen.getByRole('complementary', { name: '阶段详情' })).getByRole('button', { name: '返回流程' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.queryByRole('complementary', { name: '阶段详情' })).not.toBeInTheDocument()
})

it('返回时等待阅读区收回后恢复原画布', async () => {
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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

it('键盘 Enter 直接打开阶段', async () => {
  mount()
  const user = userEvent.setup()
  const stage = await screen.findByRole('button', { name: '元素控件清单 · 已通过' })
  stage.focus()
  await user.keyboard('{Enter}')
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
})

it('选择 UI 测试分组显示生成摘要，阶段卡片只显示阶段信息', async () => {
  mount()
  const user = userEvent.setup()
  const stage = await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' })
  await user.click(stage)
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).queryByRole('region', { name: 'UI 测试生成摘要' })).not.toBeInTheDocument()
  const group = screen.getByRole('button', { name: '选择UI 测试分组' })
  await user.click(group)
  expect(group).toHaveAttribute('aria-pressed', 'true')
  expect(stage).toHaveAttribute('aria-pressed', 'false')
  expect(within(inspector).getByRole('heading', { name: 'UI 测试' })).toBeInTheDocument()
  expect(await within(inspector).findByRole('region', { name: 'UI 测试生成摘要' })).toBeInTheDocument()
  expect(await within(inspector).findByText('team/web')).toBeInTheDocument()
  expect(within(inspector).queryByText(/源码包/)).not.toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(stage)
  expect(group).toHaveAttribute('aria-pressed', 'false')
  expect(within(inspector).queryByRole('region', { name: 'UI 测试生成摘要' })).not.toBeInTheDocument()
  const container = document.querySelector<HTMLElement>('[data-id="group:ui"] .gc-flow-group')!
  await user.click(container)
  expect(within(inspector).getByRole('region', { name: 'UI 测试生成摘要' })).toBeInTheDocument()
})

it('UI 分组按需读取需求级源码选项并支持历史画像版本', async () => {
  vi.mocked(generationChainApi.chain).mockResolvedValue({
    ...chain(),
    sourceInputs: {
      sourceKind: 'repository',
      repository: {
        repositoryId: 'old', pathWithNamespace: 'team/previous', branch: 'main',
        commit: 'previous123', commitMode: 'profile', profileVersionId: 'profile-v1', profileVersionNo: 1,
        resolvedAt: '2026-11-09T10:00:00Z',
      },
      cases: [{ caseId: 'c1', title: '转换成功' }],
    },
  })
  mount()
  const user = userEvent.setup()
  await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' })
  expect(generationChainApi.uiSourceOptions).not.toHaveBeenCalled()
  expect(generationChainApi.chain).not.toHaveBeenCalledWith('req', 'ui')
  await user.click(screen.getByRole('button', { name: '选择UI 测试分组' }))
  await waitFor(() => expect(generationChainApi.uiSourceOptions).toHaveBeenCalledWith('req'))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(await within(inspector).findByText('team/previous')).toBeInTheDocument()
  expect(within(inspector).getByText('1 条')).toBeInTheDocument()
  expect(within(inspector).queryByRole('group', { name: '选择仓库画像版本' })).not.toBeInTheDocument()
  await user.click(within(inspector).getByRole('button', { name: '配置并生成' }))
  const dialog = await screen.findByRole('dialog', { name: '更换输入并重新生成' })
  expect(await within(dialog).findByRole('button', { name: /v2/ })).toHaveAttribute('aria-pressed', 'true')
  await user.click(within(dialog).getByRole('button', { name: 'v1' }))
  expect(await within(dialog).findByText('team/old-web')).toBeInTheDocument()
  expect(within(dialog).queryByText(/ZIP|源码包/)).not.toBeInTheDocument()
})

it('UI 测试分组与功能测试使用相同大小', async () => {
  const functional = { ...emptyChain('function', '功能测试'), configured: true, taskId: 'function-task' }
  functional.stages = [
    { stage: 'requirement_analysis', label: '测试范围风险分析', order: 0, state: 'not_started', versions: [], upstreamStages: [] },
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

it('未配置 UI 测试时单击入口显示仓库源码配置，启动前先创建设置', async () => {
  const unconfigured = { ...chain(), configured: false, taskId: undefined, runId: undefined, stages: [], draftCount: 0 }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [unconfigured] })
  vi.mocked(requirementDesignApi.configure).mockResolvedValue({ taskId: 'ui-task' } as never)
  vi.mocked(generationChainApi.run).mockResolvedValue(chain())
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /开始UI 测试/ }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByRole('heading', { name: 'UI 测试' })).toBeInTheDocument()
  expect(within(inspector).getByRole('region', { name: 'UI 测试生成摘要' })).toBeInTheDocument()
  expect(await within(inspector).findByText('team/web')).toBeInTheDocument()
  expect(within(inspector).queryByRole('button', { name: /源码包/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(within(inspector).queryByRole('table')).not.toBeInTheDocument()
  await user.click(within(inspector).getByRole('button', { name: '配置并生成' }))
  const dialog = await screen.findByRole('dialog', { name: '配置 UI 测试生成' })
  await user.click(within(dialog).getByRole('button', { name: '下一步：选择用例' }))
  await within(dialog).findByRole('checkbox', { name: '选择用例：转换成功' })
  await waitFor(() => expect(within(dialog).getByRole('button', { name: '核对配置' })).toBeEnabled())
  await user.click(within(dialog).getByRole('button', { name: '核对配置' }))
  expect(requirementDesignApi.configure).not.toHaveBeenCalled()
  await user.click(within(dialog).getByRole('button', { name: '开始生成' }))
  await waitFor(() => expect(requirementDesignApi.configure).toHaveBeenCalledWith('req', 'ui', {
    requestId: expect.any(String), newConfiguration: false,
  }))
  await waitFor(() => expect(generationChainApi.run).toHaveBeenCalledWith('req', 'ui', 'ui_surface', expect.objectContaining({
    sourceProfileVersionId: 'profile-v2',
    sourceRepositoryId: 'repo-web',
  })))
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

it('阅读工具和审核操作在侧栏，视图切换与复制在页面标题栏', async () => {
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  const reader = await screen.findByRole('dialog')
  expect(within(inspector).getByRole('button', { name: '审核通过' })).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: '审核不通过' })).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: '继续优化' })).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: /对比/ })).toBeInTheDocument()
  expect(within(inspector).getByRole('group', { name: '侧栏选择版本' })).toBeInTheDocument()
  expect(within(inspector).queryByLabelText('内容展示方式')).not.toBeInTheDocument()
  expect(within(reader).queryByRole('toolbar', { name: '阅读视图工具' })).not.toBeInTheDocument()
  expect(within(reader).queryByLabelText('内容展示方式')).not.toBeInTheDocument()
  const headerActions = screen.getByTestId('reading-actions')
  expect(within(headerActions).getByLabelText('内容展示方式')).toBeInTheDocument()
  expect(within(headerActions).queryByRole('button', { name: /复制/ })).not.toBeInTheDocument()
  await user.click(within(headerActions).getByTitle('YAML'))
  expect(within(headerActions).getByRole('button', { name: '复制 YAML' })).toBeInTheDocument()
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
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  await waitFor(() => expect(within(inspector).getByText('元素控件清单').closest('.gc-trace-chip')).toHaveTextContent('v1'))
  await user.click(await screen.findByRole('button', { name: '元素控件清单 · 已通过' }))
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
  await user.click(await screen.findByRole('button', { name: '用例 YAML · 待审核' }))
  const dialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  expect(within(dialog).queryByRole('button', { name: '审核通过并继续' })).not.toBeInTheDocument()

  await user.click(within(dialog).getByRole('button', { name: /^v2/ }))
  await waitFor(() => expect(generationChainApi.version).toHaveBeenCalledWith('req', 'ui', 'sv-v2'))
  await user.click(within(screen.getByTestId('reading-actions')).getByTitle('YAML'))
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
  await user.click(await screen.findByRole('button', { name: '用例 YAML · 待审核' }))
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
  await user.click(await screen.findByRole('button', { name: '用例 YAML · 已通过' }))
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
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 已作废' }))
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
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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
    await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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

it('测试点复核失败时展示每条具体问题', async () => {
  const detail = '测试点复核未通过（2 项问题）\n1. 报告生成：缺少成功条件\n2. 语义切片：缺少前置条件'
  const data = chainWith('function', '功能测试', [{
    stage: 'case_names', label: '测试点', order: 0, state: 'failed', errorMessage: detail,
    latestVersion: null, draft: null, versions: [], upstreamStages: [],
  }])
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  await userEvent.setup().click(await screen.findByRole('button', { name: '测试点 · 执行失败' }))
  const alert = within(screen.getByRole('complementary', { name: '阶段详情' })).getByRole('alert')
  expect(alert).toHaveTextContent('报告生成：缺少成功条件')
  expect(alert).toHaveTextContent('语义切片：缺少前置条件')
  expect(alert).toHaveStyle({ whiteSpace: 'pre-line' })
})

it('需求分析第一阶段展示新版可读说明并可切换 JSON', async () => {
  const data: GenerationChain = {
    kind: 'requirement_analysis', label: '需求分析', configured: true, taskId: 'task', runId: 'run',
    active: false, busy: false, sourceChanged: false, draftCount: 1,
    stages: [
      {
        stage: 'extracting_text', label: '材料整理', order: 0, state: 'draft', latestVersion: null,
        draft: {
          attemptId: 'extract-draft', runId: 'run', status: 'draft',
          summary: '1 个材料来源 · 4 条提取事实', artifactFormat: 'json',
          content: readableSource, revision: 1, createdAt: '2026-10-30T09:00:00Z',
        },
        versions: [], upstreamStages: [],
      },
    ],
    leaf: {},
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [data, emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), chain()],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '材料整理 · 待审核' }))
  const dialog = (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement
  expect(document.querySelector('.gc-artifact-scroll')).toHaveClass('is-material-comparison')
  expect(within(dialog).queryByRole('region', { name: '材料内容' })).not.toBeInTheDocument()
  expect(within(dialog).getByRole('textbox', { name: '保存 功能使用与业务规则 内容 1' })).toHaveValue('保存后展示结果')

  await user.click(within(screen.getByTestId('reading-actions')).getByTitle('JSON'))
  expect(within(dialog).queryByRole('region', { name: '材料内容' })).not.toBeInTheDocument()
  expect(within(dialog).getByRole('textbox', { name: '阶段产物 JSON' })).toHaveTextContent('"artifactType": "readable_requirement_material"')
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

it('继续优化逐条填写并保留取消后的答复', async () => {
  const data = chainWith('requirement_analysis', '需求分析', [draftStage('extracting_text', '材料整理', 0, extractionSource)])
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '材料整理 · 待审核' }))
  await user.click(await screen.findByRole('button', { name: '继续优化' }))
  const answer = await screen.findByRole('textbox', { name: '补充答复' })
  expect(screen.getByRole('button', { name: '提交优化' })).toBeDisabled()
  await user.type(answer, '默认开关开启')
  await user.click(screen.getByRole('button', { name: '取消优化' }))
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  expect(screen.getByRole('textbox', { name: '补充答复' })).toHaveValue('默认开关开启')
  await user.click(screen.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(generationChainApi.revise).toHaveBeenCalledWith('req', 'requirement_analysis', 'extracting_text', expect.objectContaining({ instruction: expect.stringContaining('答复：默认开关开启') })))
})

/** 每次重新挂载工作区并打开指定阶段，避免依赖弹框关闭动画。 */
async function openStage(label: string) {
  cleanup()
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: `${label} · 待审核` }))
  return { user, dialog: (await screen.findByRole('dialog')).closest('.gc-canvas-workspace') as HTMLElement }
}


it('需求分析分组内提供仓库画像卡片，进入阅读区后在侧栏运行', async () => {
  const data = chainWith('requirement_analysis', '需求分析', [
    {
      stage: 'extracting_text', label: '材料整理', order: 0, state: 'approved',
      latestVersion: { ...version('sv-extract-1', 1), stage: 'extracting_text' },
      draft: null, versions: [{ ...version('sv-extract-1', 1), stage: 'extracting_text' }],
      upstreamStages: [],
    },
  ])
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data, chain()] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([
    { taskId: 'profile-task', requirementId: 'req', name: '画像', instruction: '' },
  ] as never)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTaskRuns).mockResolvedValue([
    {
      runId: 'run-1', status: 'success', reviewStatus: 'not_required',
      createdAt: '2026-11-09T10:00:00Z',
    },
  ] as never)
  vi.mocked(repositoryProfileApi.getRepositoryProfileVersions).mockResolvedValue([
    {
      versionId: 'run-1', versionNo: 1, label: 'v1', sourceRunId: 'run-1',
      resultYaml: '{"repositories":[],"overallSummary":"当前需求主要涉及后端仓库"}',
      createdAt: '2026-11-09T10:00:00Z',
      requirementMaterialVersion: { versionId: 'sv-extract-1', versionNo: 1 },
      profile: {
        repositories: [
          {
            repositoryId: 'repo-1', pathWithNamespace: 'team/repo-1', role: 'backend',
            responsibilitySummary: '提供登录接口', techStack: ['Java'],
            keyPaths: ['src'], confidence: 0.9, evidence: ['pom.xml'],
          },
        ],
        overallSummary: '当前需求主要涉及后端仓库',
      },
    },
  ] as never)
  vi.spyOn(baseServicesApi, 'getGitlabRequirementBindings').mockResolvedValue([
    {
      bindingId: 'binding-1', provider: 'gitlab', remoteResourceType: 'repository',
      remoteResourceId: 'repo-1', remoteNameSnapshot: 'team/repo-1', branch: 'main',
    },
  ] as never)

  mount()
  const user = userEvent.setup()
  const card = await screen.findByRole('button', { name: '仓库画像 · 已生成' })
  expect(card).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /生成 UI 用例/ })).not.toBeInTheDocument()
  await waitFor(() => {
    expect(document.querySelector('[data-testid="rf__edge-analysis-to-profile"]')).not.toBeNull()
    expect(document.querySelector('[data-testid="rf__edge-profile-to-ui"]')).not.toBeNull()
    expect(document.querySelector('[data-testid="rf__edge-analysis-to-ui"]')).toBeNull()
  })

  await user.click(card)
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByText('画像版本')).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: 'v1（最新）' })).toBeInTheDocument()
  expect(within(inspector).getByText('上游追溯')).toBeInTheDocument()
  expect(within(inspector).queryByText('阅读工具')).not.toBeInTheDocument()
  expect(within(inspector).queryByRole('button', { name: '打开画像结果' })).not.toBeInTheDocument()
  expect(within(inspector).queryByText('需求理解版本')).not.toBeInTheDocument()
  expect(within(inspector).queryByText('阶段操作')).not.toBeInTheDocument()
  expect(within(inspector).queryByText('最近结果')).not.toBeInTheDocument()
  const reading = await screen.findByRole('dialog', { name: '仓库画像' })
  expect(within(reading).getByText('整体画像')).toBeInTheDocument()
  expect(within(reading).getByText('team/repo-1')).toBeInTheDocument()
  expect(within(reading).queryByRole('button', { name: '重新生成画像' })).not.toBeInTheDocument()
  expect(within(inspector).getByRole('heading', { name: '运行' })).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: '重新生成画像' })).toBeInTheDocument()
})

it('仓库画像运行中复用阶段卡片的运行状态和加载动画', async () => {
  const data = chainWith('requirement_analysis', '需求分析', [
    {
      stage: 'extracting_text', label: '材料整理', order: 0, state: 'approved',
      latestVersion: { ...version('sv-extract-1', 1), stage: 'extracting_text' },
      draft: null, versions: [{ ...version('sv-extract-1', 1), stage: 'extracting_text' }],
      upstreamStages: [],
    },
  ])
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([
    { taskId: 'profile-task', requirementId: 'req', name: '画像', instruction: '' },
  ] as never)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTaskRuns).mockResolvedValue([
    {
      runId: 'run-running', status: 'running', reviewStatus: 'not_required',
      createdAt: '2026-11-09T10:00:00Z',
    },
  ] as never)
  vi.mocked(repositoryProfileApi.getRepositoryProfileVersions).mockResolvedValue([] as never)

  mount()
  const card = await screen.findByRole('button', { name: '仓库画像 · 运行中' })
  expect(card).toHaveClass('is-running')
  expect(card).toHaveAttribute('aria-busy', 'true')
  expect(card.querySelector('.gc-running-indicator')).toBeInTheDocument()
})

it('功能测试各阶段沿用页签的测试范围风险分析、测试点与完整用例视图', async () => {
  const analysis = { schemaVersion: '1.0', artifactType: 'test_scope_impact_risk', testObjects: [{ id: 'TO1', name: '导出转换数据', type: '功能', description: '选择类型导出', sourceBlockIds: ['b1'], basisStatus: 'confirmed' }], impactAreas: [], risks: [], openQuestions: [] }
  const points = { artifactType: 'traceable_test_points', schemaVersion: '1.0', reviewStatus: 'independent_reviewed', testPoints: [{ id: 'P1', module: '导出', dimension: '功能场景', name: '【导出】验证导出成功', materialBlockIds: ['b1'] }], coverageGaps: [] }
  const cases = { cases: [{ case_module: '导出', case_name: '导出成功', priority: 'P0', steps: '1. 点击导出', expected: '成功' }] }
  const data = chainWith('function', '功能测试', [
    draftStage('requirement_analysis', '测试范围风险分析', 0, JSON.stringify(analysis)),
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

  const analysisView = await openStage('测试范围风险分析')
  expect(within(analysisView.dialog).getByText('导出转换数据')).toBeInTheDocument()

  const pointsView = await openStage('测试点')
  expect(within(pointsView.dialog).getByText('功能场景')).toBeInTheDocument()
  await pointsView.user.click(within(pointsView.dialog).getByRole('tab', { name: '树图' }))
  expect(within(pointsView.dialog).getByRole('button', { name: /保存图片/ })).toBeInTheDocument()

  const casesView = await openStage('完整用例')
  expect(casesView.dialog.querySelector('.ai-generated-case-browser')).not.toBeNull()
  expect(within(casesView.dialog).getAllByText('导出成功').length).toBeGreaterThan(0)
  // 图谱是「完整用例」之后的独立派生节点，不再放进阶段弹框。
  expect(within(casesView.dialog).queryByRole('button', { name: '用例图谱' })).not.toBeInTheDocument()
  await casesView.user.click(within(casesView.dialog).getByRole('button', { name: '返回流程' }))
  await casesView.user.click(await screen.findByRole('button', { name: '用例图谱 · 派生' }))
  const generateGraph = await screen.findByRole('button', { name: '生成图谱' })
  await casesView.user.click(generateGraph)
  await waitFor(() => expect(aiTestingApi.generateFunctionalCaseRelationAnalysis).toHaveBeenCalledWith('run', 'llm'))
})

it('待审核完整用例的 JSON 原文按缩进展开，避免压缩成一整行', async () => {
  const cases = { cases: [{ case_id: 'case-1', case_module: '导出', case_title: '导出成功', case_type: '功能测试', priority: 'P1', test_steps: ['1. 点击导出'], expected_results: ['导出成功'] }] }
  const data = chainWith('function', '功能测试', [draftStage('detailed_cases', '完整用例', 0, JSON.stringify(cases))])
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data, chain()] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  vi.mocked(repositoryProfileApi.getRepositoryProfileVersions).mockResolvedValue([] as never)

  const casesView = await openStage('完整用例')
  await casesView.user.click(within(screen.getByTestId('reading-actions')).getByTitle('JSON'))
  const editor = await within(casesView.dialog).findByRole('textbox', { name: '阶段产物 JSON' })
  await waitFor(() => expect(editor.querySelectorAll('.cm-line').length).toBeGreaterThan(1))
  const lines = Array.from(editor.querySelectorAll('.cm-line')).map(line => line.textContent ?? '')
  expect(lines[0]).toBe('{')
  expect(lines.some(line => line.trimStart().startsWith('"cases": ['))).toBe(true)
})

it('用例图谱节点使用完整用例已通过版本的来源运行', async () => {
  const cases = { cases: [{ case_module: '导出', case_name: '导出成功', priority: 'P0', steps: '1. 点击导出', expected: '成功' }] }
  const approved = { ...version('func-cases-v1', 1, 'run-version'), summary: '1 条用例' }
  const data = chainWith('function', '功能测试', [
    draftStage('requirement_analysis', '测试范围风险分析', 0, '{}'),
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
  await user.click(await screen.findByRole('button', { name: '用例图谱 · 派生' }))
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
    draftStage('requirement_analysis', '测试范围风险分析', 0, '{}'),
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
  await user.click(await screen.findByRole('button', { name: '接口配置提取 · 待审核' }))
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
  await user.click(node)
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
  await user.click(node)
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

it('API 独立输入，仓库画像连接 UI，初始分组不重叠', async () => {
  const analysis = { ...emptyChain('requirement_analysis', '需求分析'), configured: true }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [analysis, emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), chain()],
  })
  mount()
  await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' })
  await waitFor(() => {
    expect(document.querySelector('[aria-label="Edge from requirement_analysis:extracting_text to group:api"]')).not.toBeInTheDocument()
    expect(document.querySelector('[aria-label="Edge from profile to ui:ui_surface"]')).toBeInTheDocument()
  })
  const api = document.querySelector<HTMLElement>('[data-id="group:api"]')!
  const ui = document.querySelector<HTMLElement>('[data-id="group:ui"]')!
  const analysisGroup = document.querySelector<HTMLElement>('[data-id="group:requirement_analysis"]')!
  expect(Number.parseFloat(analysisGroup.style.width)).toBeCloseTo(292 * 1.2)
  expect(Number.parseFloat(analysisGroup.style.height)).toBeCloseTo(280 * 1.2)
  const y = (node: HTMLElement) => Number(node.style.transform.match(/,\s*([\d.]+)px\)/)?.[1])
  expect(y(ui)).toBeGreaterThan(y(api) + Number.parseFloat(api.style.height))
})

it('UI 首阶段运行先选择仓库来源和功能用例，再把所选输入传给生成链', async () => {
  const data: GenerationChain = {
    kind: 'ui', label: 'UI 测试', configured: true, taskId: 'task', draftCount: 0,
    stages: [{ stage: 'ui_surface', label: '元素控件清单', order: 0, state: 'not_started', versions: [], upstreamStages: [] }], leaf: {},
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(generationChainApi.run).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '元素控件清单 · 未开始' }))
  const runButton = await screen.findByRole('button', { name: '运行此阶段' })
  expect(runButton).toBeEnabled()
  await user.click(runButton)
  expect(generationChainApi.run).not.toHaveBeenCalled()
  const inputDialog = (await screen.findByText('配置 UI 测试生成')).closest('[role=dialog]') as HTMLElement
  await waitFor(() => expect(within(inputDialog).getByRole('button', { name: '下一步：选择用例' })).toBeEnabled())
  expect(within(inputDialog).getByRole('radio', { name: '选择仓库 team/web' })).toBeChecked()
  await user.click(within(inputDialog).getByRole('button', { name: '下一步：选择用例' }))
  await within(inputDialog).findByRole('checkbox', { name: '选择用例：转换成功' })
  await user.click(within(inputDialog).getByRole('checkbox', { name: '选择用例：转换失败' }))
  await user.click(within(inputDialog).getByRole('button', { name: '核对配置' }))
  await user.click(within(inputDialog).getByRole('button', { name: '开始生成' }))
  await waitFor(() => expect(generationChainApi.run).toHaveBeenCalledWith('req', 'ui', 'ui_surface', expect.objectContaining({
    connectionId: 'llm',
    refreshInputs: false,
    functionCaseIds: ['c1'],
    sourceProfileVersionId: 'profile-v2',
    sourceRepositoryId: 'repo-web',
    sourceCommitMode: 'profile',
    requestId: expect.any(String),
  })))
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
  const approvedState = dialog.querySelector('.gc-inspector-header .gc-state')
  expect(approvedState).toHaveTextContent('已通过')
  expect(approvedState).toHaveClass('is-approved')
  expect(approvedState?.querySelector('.gc-state-text')).toHaveTextContent('已通过')
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
  await userEvent.setup().click(running)
  const reading = await screen.findByRole('dialog', { name: 'UI 用例设计' })
  expect(within(reading).getByRole('status')).toHaveTextContent('正在生成UI 用例设计')
  expect(within(reading).queryByText('输入账号')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '审核通过' })).not.toBeInTheDocument()
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
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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
  const onReadingNodeChange = vi.fn()
  mount(<div>需求文档阅读内容</div>, onReadingNodeChange)
  const user = userEvent.setup()
  const card = await screen.findByRole('button', { name: /查看需求文档/ })
  await user.click(card)
  expect(card).toHaveAttribute('aria-pressed', 'true')
  const document = await screen.findByRole('dialog', { name: '需求文档' })
  expect(document).toHaveAttribute('aria-modal', 'false')
  expect(document.closest('.gc-canvas-stage')).not.toBeNull()
  expect(within(document).getByText('需求文档阅读内容')).toBeInTheDocument()
  expect(screen.getByRole('complementary', { name: '阶段详情' })).toBeVisible()
  // 阅读态把当前产物交给页面标题栏，作为面包屑的最后一级。
  expect(onReadingNodeChange).toHaveBeenLastCalledWith(expect.objectContaining({ label: '需求文档' }))
  await user.click(within(screen.getByRole('complementary', { name: '阶段详情' })).getByRole('button', { name: '返回流程' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /查看需求文档/ })).toBeInTheDocument()
  expect(onReadingNodeChange).toHaveBeenLastCalledWith(null)
})

it('阅读态上报的上级面包屑能退回生成流程', async () => {
  const onReadingNodeChange = vi.fn()
  mount(<div>需求文档阅读内容</div>, onReadingNodeChange)
  const user = userEvent.setup()
  const card = await screen.findByRole('button', { name: /查看需求文档/ })
  await user.click(card)
  expect(await screen.findByRole('dialog', { name: '需求文档' })).toBeInTheDocument()
  const reported: { leave?: () => void } | null = onReadingNodeChange.mock.lastCall?.[0]
  expect(reported?.leave).toBeTypeOf('function')
  await act(async () => { reported?.leave?.() })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(onReadingNodeChange).toHaveBeenLastCalledWith(null)
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
    await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 待审核' }))
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

it('继续优化预填全部功能的待确认问题，并保留已填写的内容', async () => {
  const material = JSON.parse(readableSource)
  material.functions = [
    { ...material.functions[0], id: 'F1', name: '功能甲' },
    { ...material.functions[0], id: 'F2', name: '功能乙' },
  ]
  material.questions = [
    { id: 'q1', question: '功能乙的问题', reason: '', materialBlockIds: [], functionIds: ['F2'] },
    { id: 'q2', question: '功能甲的问题', reason: '', materialBlockIds: [], functionIds: ['F1'] },
    { id: 'q3', question: '整体问题', reason: '', materialBlockIds: [], functionIds: [] },
  ]
  const data = chainWith('requirement_analysis', '需求分析', [draftStage('extracting_text', '材料整理', 0, JSON.stringify(material))])
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '材料整理 · 待审核' }))
  await user.click(await screen.findByRole('button', { name: '继续优化' }))
  expect(screen.getByText('功能乙的问题')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '问题 q2' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '问题 q3' })).toBeInTheDocument()
  await user.type(screen.getByRole('textbox', { name: '补充答复' }), '已经填写的补充')
  await user.click(screen.getByRole('button', { name: '问题 q2' }))
  expect(screen.getByText('功能甲的问题')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '取消优化' }))
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  expect(await screen.findByRole('textbox', { name: '补充答复' })).toHaveValue('已经填写的补充')
})

it('完整用例运行时在画布和阅读区展示模块子 Agent 进度', async () => {
  const data = chainWith('function', '功能测试', [{
    stage: 'detailed_cases', label: '完整用例', order: 0, state: 'running', versions: [], upstreamStages: [], activeRunId: 'modules-run',
    moduleGeneration: {
      attemptId: 'modules-run', sequence: 2, concurrency: 2, status: 'running', modules: [
        { id: '0', module: '文件校验', status: 'completed', caseCount: 3, elapsedMs: 21000, repairAttempt: 0 },
        { id: '1', module: 'IMU 校验', status: 'running', caseCount: 0, elapsedMs: 0, repairAttempt: 0 },
      ],
    },
  }])
  data.active = data.busy = true
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  mount()
  const user = userEvent.setup()
  const card = await screen.findByRole('button', { name: '完整用例 · 运行中' })
  expect(card).toHaveTextContent('已完成 1/2 个模块')
  await user.click(card)
  const panel = await screen.findByRole('region', { name: '模块生成进度' })
  expect(within(panel).getByText('子 Agent 执行进度')).toBeVisible()
  expect(within(panel).getByText('IMU 校验')).toBeVisible()
  expect(within(panel).getByText('生成中', { exact: true })).toBeVisible()
  expect(within(panel).getByText('3 条用例 · 21 秒')).toBeVisible()
})

it('重新生成测试点时用本次分组进度替换旧结果，完成后打开新草稿', async () => {
  const points = (name: string) => JSON.stringify({
    artifactType: 'traceable_test_points', schemaVersion: '1.0', reviewStatus: 'independent_reviewed',
    testPoints: [{ id: 'P1', module: '配置', dimension: '功能场景', name, materialBlockIds: ['B1'] }],
  })
  const oldVersion = { ...version('points-v1', 1, 'old-points-run'), summary: '旧版本测试点摘要' }
  const previous: GenerationChainStage = {
    stage: 'case_names', label: '测试点', order: 0, state: 'approved', latestVersion: oldVersion, versions: [oldVersion], upstreamStages: [],
  }
  const approved = chainWith('function', '功能测试', [previous])
  const running = chainWith('function', '功能测试', [{
    ...previous, state: 'running', activeRunId: 'points-run',
    moduleGeneration: {
      stage: 'case_names', attemptId: 'points-run', sequence: 8, concurrency: 2, status: 'reviewing', reviewRound: 1,
      modules: [{ id: '0', module: '跨组与公共规则', status: 'completed', caseCount: 0, pointCount: 6, elapsedMs: 17000, repairAttempt: 0 }],
    },
  }])
  running.active = running.busy = true
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [approved] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(approved)
  vi.mocked(generationChainApi.version).mockResolvedValue({
    ...oldVersion, kind: 'function', stage: 'case_names', stageLabel: '测试点', content: points('旧测试点'),
    reviewedAt: null, reviewComment: '', upstreamVersions: {}, upstream: [],
  })
  vi.mocked(generationChainApi.run).mockImplementation(async () => {
    vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [running] })
    vi.mocked(generationChainApi.chain).mockResolvedValue(running)
    return running
  })
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '测试点 · 已通过' }))
  const reading = await screen.findByRole('dialog', { name: '测试点' })
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(await within(reading).findByText('旧测试点')).toBeVisible()
  await user.click(within(screen.getByTestId('reading-actions')).getByTitle('JSON'))
  await user.click(within(inspector).getByRole('button', { name: '按所选上游重新生成' }))
  const panel = await screen.findByRole('region', { name: '测试点分组进度' })
  expect(within(panel).getByText('初稿已完成 1/1 个分组')).toBeVisible()
  expect(within(panel).getByText('6 个测试点（初稿） · 17 秒')).toBeVisible()
  expect(within(panel).getByRole('status')).toHaveTextContent('正在进行首次全局覆盖与依据审查')
  expect(within(reading).queryByRole('textbox', { name: '阶段产物 JSON' })).not.toBeInTheDocument()
  expect(within(inspector).queryByText(oldVersion.summary)).not.toBeInTheDocument()
  expect(within(inspector).queryByText('old-points-run')).not.toBeInTheDocument()
  expect(within(inspector).getByText('points-run')).toBeVisible()
  expect(within(inspector).queryByRole('group', { name: '侧栏选择版本' })).not.toBeInTheDocument()

  const completed = chainWith('function', '功能测试', [{
    ...previous, ...draftStage('case_names', '测试点', 0, points('新测试点')),
    latestVersion: oldVersion, versions: [oldVersion],
  }])
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [completed] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(completed)
  await act(async () => { await clients.at(-1)!.invalidateQueries({ queryKey: ['generationChain', 'req'] }) })
  expect(await within(reading).findByRole('textbox', { name: '测试点 P1' })).toHaveValue('新测试点')
  expect(within(reading).queryByRole('region', { name: '测试点分组进度' })).not.toBeInTheDocument()
  await user.click(within(inspector).getByRole('button', { name: 'v1' }))
  expect(await within(reading).findByText('旧测试点')).toBeVisible()
})
