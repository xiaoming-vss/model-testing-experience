import readableSource from '@/domain/requirements/fixtures/readable-material.example.json?raw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { api } from '@/services/api'
import { canNavigateAway } from '@/shared/utils/unsavedChanges'
import { requirementDesignApi } from '../api/requirementDesign.api'
import { aiTestingApi } from '../api/aiTesting.api'
import { generationChainApi } from '../api/generationChain.api'
import { generationCandidatesApi } from '../api/generationCandidates.api'
import { profileCandidatesApi } from '../api/profileCandidates.api'
import { repositoryProfileApi } from '../api/repositoryProfile.api'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import type { GenerationChain, GenerationChainStage, UiGenerationSourceOptions } from '../api/generationChain.api'
import { RequirementDesignWorkspace } from './RequirementDesignWorkspace'

vi.mock('../api/requirementDesign.api', () => ({
  requirementDesignApi: { overview: vi.fn(), history: vi.fn(), start: vi.fn(), configure: vi.fn() },
}))

vi.mock('../api/generationChain.api', () => ({
  generationChainApi: {
    overview: vi.fn(), chain: vi.fn(), uiSourceOptions: vi.fn(), uiSourceCheck: vi.fn(),
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
  },
}))
vi.mock('../hooks/usePersonalLlmChoice', () => ({
  usePersonalLlmChoice: () => ({
    choose: async () => 'llm',
    chooseRun: async () => ({ connectionId: 'llm', checkpointEnabled: true, instruction: '只覆盖登录接口' }),
    dialog: null,
  }),
}))
vi.mock('@/domain/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))

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

function chain(): GenerationChain {
  return {
    kind: 'ui', label: 'UI 测试', configured: true, taskId: 'task', runId: 'run',
    active: false, busy: false, sourceChanged: false, pendingCandidateCount: 1,
    stages: [
      {
        stage: 'ui_surface', label: '元素控件清单', order: 0, state: 'approved', upstreamStages: [],
      },
      {
        stage: 'ui_design', label: 'UI 用例设计', order: 1, state: 'draft', upstreamStages: ['ui_surface'],
      },
      {
        stage: 'ui_yaml', label: '用例 YAML', order: 2, state: 'not_started', upstreamStages: ['ui_surface', 'ui_design'],
      },
    ],
  }
}

const emptyChain = (kind: 'requirement_analysis' | 'function' | 'api', label: string): GenerationChain => ({
  kind, label, configured: false, pendingCandidateCount: 0,
  stages: [{ stage: kind === 'function' ? 'requirement_analysis' : kind === 'api' ? 'interface_extract' : 'extracting_text', label: '首阶段', order: 0, state: 'not_started', upstreamStages: [] }],
})

function sourceOptions(): UiGenerationSourceOptions {
  return { currentProfile: {
    candidateId: 'profile-v2', label: '当前画像', createdAt: '2026-11-09T10:00:00Z',
    repositories: [{
      repositoryId: 'repo-web', pathWithNamespace: 'team/web', role: 'frontend',
      confidence: 0.92, responsibilitySummary: '管理端前端', keyPaths: ['src'],
      branch: 'main', commit: 'a1b2c3d4', isFrontend: true, available: true, profileError: '',
    }],
  } }
}

function mount(documentPreview?: import('react').ReactNode, onReadingNodeChange?: Parameters<typeof RequirementDesignWorkspace>[0]['onReadingNodeChange'], inspectorHost?: HTMLElement | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  const readingNodeChange = onReadingNodeChange ?? vi.fn()
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter>
    <RequirementDesignWorkspace requirementId="req" projectId="project" canWrite documentPreview={documentPreview} onReadingNodeChange={readingNodeChange} inspectorHost={inspectorHost} />
  </MemoryRouter></QueryClientProvider></TestThemeProvider>)
  return () => {
    const reported = (readingNodeChange as ReturnType<typeof vi.fn>).mock.lastCall?.[0] as { leave?: () => void } | undefined
    act(() => { reported?.leave?.() })
  }
}



beforeEach(() => {
  vi.mocked(aiTestingApi.getUiCaseGenerateTask).mockResolvedValue({ name: 'UI', sourceType: 'repository', instruction: '' })
  vi.mocked(generationChainApi.uiSourceOptions).mockResolvedValue(sourceOptions())
  vi.mocked(generationChainApi.uiSourceCheck).mockResolvedValue({
    pinnedCommit: 'a1b2c3d4', currentCommit: 'a1b2c3d4', branch: 'main', changed: false,
  })
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const path = new URL(String(input), 'http://localhost').pathname
    // 需求级软件仓库绑定必须返回仓库绑定结构；落到默认用例行会让 branch 读取崩溃。
    const rows = path.endsWith('/software-repositories') ? []
      : path.endsWith('/function-test-suites') ? [{ suiteId: 'suite', name: '功能' }]
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
  vi.spyOn(api, 'getLlmConnections').mockResolvedValue(Object.assign([{ connectionId: 'llm', name: '本人模型', status: 'active' as const, provider: 'openai', baseUrl: 'https://example.test', authType: 'api_key', account: '', hasAccessToken: true, modelId: 'model' }], { items: [{ connectionId: 'llm', name: '本人模型', status: 'active' as const, provider: 'openai', baseUrl: 'https://example.test', authType: 'api_key', account: '', hasAccessToken: true, modelId: 'model' }], total: 1 }))
  vi.spyOn(api, 'getFunctionalCaseGenerateTaskRun').mockImplementation(async runId => ({ runId, status: 'success', currentStage: 'completed', reviewStatus: 'approved', configJson: {}, importStatus: 'pending', importedTargets: [], importedAt: '' }))
  vi.spyOn(api, 'getFunctionalCaseGenerateTask').mockResolvedValue({ taskId: 'task-function', name: '功能测试', projectId: 'project', instruction: '' })
})

it('候选模式在画布显示当前内容和候选摘要', async () => {
  const base = chain()
  const data = { ...base, candidateMode: true, stages: base.stages.map(stage => ({
    ...stage, blockedReason: '',
  })) }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  mount()
  expect(within(await screen.findByRole('button', { name: '元素控件清单 · 已采用' })).getByText('已有当前采用内容')).toBeInTheDocument()
  expect(within(screen.getByRole('button', { name: 'UI 用例设计 · 有候选' })).getByText('已有候选内容')).toBeInTheDocument()
  profiles.mockRestore()
})

it('单击阶段在画布内打开候选和当前内容', async () => {
  const data = { ...chain(), candidateMode: true }
  const item = { candidateId: 'candidate-1', snapshotId: 'snapshot', candidateToken: 'token', currentAttemptId: 'attempt', disposition: 'available', generationMode: 'current', createdAt: '2026-11-20T10:00:00Z', isCurrent: false }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ currentToken: 'current', candidateId: 'adopted', content: '当前正文', format: 'text', active: false } as never)
  const list = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [item], total: 1, page: 1, pageSize: 20 } as never)
  const detail = vi.spyOn(generationCandidatesApi, 'detail').mockResolvedValue({ ...item, content: '候选正文', format: 'text' } as never)
  mount()
  const user = userEvent.setup()
  const card = await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' })
  await user.click(card)
  expect(card).toHaveAttribute('aria-pressed', 'true')
  const dialog = await screen.findByRole('dialog', { name: 'UI 用例设计 · 候选与当前内容' })
  expect(dialog).toHaveAttribute('aria-modal', 'false')
  expect(dialog.closest('.gc-canvas-stage')).not.toBeNull()
  expect(screen.getByRole('complementary', { name: '阶段详情' })).toBeVisible()
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByRole('region', { name: '当前查看' })).toHaveTextContent('当前采用')
  expect(within(inspector).getAllByText('当前采用').length).toBeGreaterThan(0)
  // 候选切换沿用旧版本选择的位置，正文不再保留常驻候选左栏。
  expect(within(dialog).queryByRole('region', { name: '候选列表' })).not.toBeInTheDocument()
  await user.click(within(inspector).getByRole('button', { name: /候选 candidat/ }))
  await waitFor(() => expect(detail).toHaveBeenCalledWith('req', 'ui', 'ui_design', 'candidate-1'))
  profiles.mockRestore(); current.mockRestore(); list.mockRestore(); detail.mockRestore()
})

it('阶段侧栏渲染到页面级独立容器，不放进画布大容器', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  try {
    mount(undefined, undefined, host)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' }))
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
    await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' }))
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
    expect(within(inspector).queryByRole('button', { name: '返回流程' })).not.toBeInTheDocument()
  } finally { host.remove() }
})

it('执行失败且 Worker 未返回原因时仍展示失败详情和运行信息', async () => {
  const failed = chain()
  failed.candidateMode = true
  failed.stages[0] = {
    stage: 'ui_surface', label: '元素控件清单', order: 0, state: 'failed',
    upstreamStages: [],
    errorMessage: '', failureRunId: 'failed-run-1234', failedAt: '2026-11-03T10:11:48Z',
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), failed],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(failed)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: 'old', content: '保留的当前内容', active: false } as never)
  const candidates = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
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
  profiles.mockRestore(); current.mockRestore(); candidates.mockRestore()
})










async function openUiCandidateWorkspace() {
  const data = { ...chain(), candidateMode: true }
  const candidate = { candidateId: 'candidate-1', snapshotId: 'snapshot', candidateToken: 'token', currentAttemptId: 'attempt', disposition: 'available', generationMode: 'current', createdAt: '2026-11-20T10:00:00Z', isCurrent: false }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ currentToken: 'current', candidateId: null, active: false } as never)
  const list = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 } as never)
  const detail = vi.spyOn(generationCandidatesApi, 'detail').mockResolvedValue({ ...candidate, content: 'name: 旧内容', format: 'yaml' } as never)
  const edit = vi.spyOn(generationCandidatesApi, 'edit').mockResolvedValue({} as never)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' }))
  await user.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  await user.click(await screen.findByRole('button', { name: '编辑' }))
  const editor = await screen.findByRole('textbox', { name: '候选内容' })
  await user.click(editor)
  await user.keyboard('x')
  return { user, edit, restore: () => { profiles.mockRestore(); current.mockRestore(); list.mockRestore(); detail.mockRestore(); edit.mockRestore() } }
}

it('整页候选编辑通过候选接口保存', async () => {
  const { user, edit, restore } = await openUiCandidateWorkspace()
  await user.click(screen.getByRole('button', { name: '保存候选' }))
  await waitFor(() => expect(edit).toHaveBeenCalledWith('req', 'ui', 'ui_design', 'candidate-1', expect.objectContaining({ expectedAttemptId: 'attempt', content: expect.stringContaining('x') })))
  restore()
})

it('候选有未保存修改时阻止切换和浏览器后退', async () => {
  const previousState = window.history.state
  window.history.replaceState({ ...previousState, idx: 3 }, '')
  const go = vi.spyOn(window.history, 'go').mockImplementation(() => undefined)
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  const { user, restore } = await openUiCandidateWorkspace()
  expect(canNavigateAway()).toBe(false)
  expect(window.dispatchEvent(new Event('beforeunload', { cancelable: true }))).toBe(false)
  await user.click(screen.getByRole('button', { name: '查看当前内容' }))
  expect(screen.getByRole('button', { name: '保存候选' })).toBeEnabled()
  window.dispatchEvent(new PopStateEvent('popstate', { state: { idx: 2 } }))
  expect(go).toHaveBeenCalledWith(1)
  confirm.mockRestore(); go.mockRestore(); restore()
  window.history.replaceState(previousState, '')
})

it('单击打开阅读区，返回后收起详情栏', async () => {
  const leave = mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' }))
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
  leave()
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.queryByRole('complementary', { name: '阶段详情' })).not.toBeInTheDocument()
})

it('返回时等待阅读区收回后恢复原画布', async () => {
  const leave = mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' }))
  const reader = await screen.findByRole('dialog')
  const animation = { onfinish: null as (() => void) | null, cancel: vi.fn() }
  const animate = vi.fn(() => animation)
  Object.defineProperty(reader, 'animate', { value: animate, configurable: true })
  leave()
  expect(animate).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(reader.closest('.gc-canvas-stage')?.querySelector('.gc-canvas-map')).toHaveAttribute('inert')
  act(() => { animation.onfinish?.() })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.getByRole('button', { name: 'UI 用例设计 · 有候选' })).toBeVisible()
})

it('键盘 Enter 直接打开阶段', async () => {
  mount()
  const user = userEvent.setup()
  const stage = await screen.findByRole('button', { name: '元素控件清单 · 已采用' })
  stage.focus()
  await user.keyboard('{Enter}')
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
})

it('选择 UI 测试分组显示生成摘要，阶段卡片只显示阶段信息', async () => {
  mount()
  const user = userEvent.setup()
  const stage = await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' })
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

it('UI 分组按需读取源码摘要并提供候选工作区入口', async () => {
  vi.mocked(generationChainApi.chain).mockResolvedValue({
    ...chain(),
    sourceInputs: {
      sourceKind: 'repository',
      repository: {
        repositoryId: 'old', pathWithNamespace: 'team/previous', branch: 'main',
        commit: 'previous123', commitMode: 'profile', profileCandidateId: 'profile-v1',
        resolvedAt: '2026-11-09T10:00:00Z',
      },
      cases: [{ caseId: 'c1', title: '转换成功' }],
    },
  })
  mount()
  const user = userEvent.setup()
  await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' })
  expect(generationChainApi.uiSourceOptions).not.toHaveBeenCalled()
  expect(generationChainApi.chain).not.toHaveBeenCalledWith('req', 'ui')
  await user.click(screen.getByRole('button', { name: '选择UI 测试分组' }))
  await waitFor(() => expect(generationChainApi.uiSourceOptions).toHaveBeenCalledWith('req'))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(await within(inspector).findByText('team/previous')).toBeInTheDocument()
  expect(within(inspector).getByText('1 条')).toBeInTheDocument()
  expect(within(inspector).queryByRole('group', { name: '选择仓库画像版本' })).not.toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: '打开候选工作区' })).toBeInTheDocument()
})

it('UI 测试分组与功能测试使用相同大小', async () => {
  const functional = { ...emptyChain('function', '功能测试'), configured: true, taskId: 'function-task' }
  functional.stages = [
    { stage: 'requirement_analysis', label: '测试范围风险分析', order: 0, state: 'not_started', upstreamStages: [] },
    { stage: 'case_names', label: '测试点', order: 1, state: 'not_started', upstreamStages: [] },
    { stage: 'detailed_cases', label: '完整用例', order: 2, state: 'not_started', upstreamStages: [] },
  ]
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [functional, chain()] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(chain())
  mount()
  await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' })
  const node = (id: string) => document.querySelector<HTMLElement>(`[data-id="${id}"]`)!
  const ui = node('group:ui')
  const functionalGroup = node('group:function')
  expect(ui.style.width).toBe(functionalGroup.style.width)
  expect(ui.style.height).toBe(functionalGroup.style.height)
})

it('以可选依赖虚线连接历史用例核验与完整用例', async () => {
  const analysis = { ...emptyChain('requirement_analysis', '需求分析'), configured: true, stages: [
    { stage: 'historical_requirement_relations', label: '历史需求关联', order: 0, state: 'approved', upstreamStages: [] },
    { stage: 'historical_test_case_verification', label: '历史用例核验', order: 1, state: 'not_started', upstreamStages: ['historical_requirement_relations'] },
  ] } satisfies GenerationChain
  const functional = { ...emptyChain('function', '功能测试'), configured: true, stages: [
    { stage: 'case_names', label: '测试点', order: 0, state: 'approved', upstreamStages: [] },
    { stage: 'detailed_cases', label: '完整用例', order: 1, state: 'not_started', upstreamStages: ['case_names'] },
  ] } satisfies GenerationChain
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [analysis, functional] })
  mount()
  const edge = await screen.findByLabelText('历史用例核验到完整用例的可选输入')
  expect(edge.querySelector('.gc-flow-edge-track')).toHaveStyle({ strokeDasharray: '6 4' })
  expect(edge.querySelector('.gc-flow-edge-stream')).toBeNull()
  expect(document.querySelector('[data-testid="rf__edge-function:1"]')).not.toBeNull()
})

it('单击 API 首阶段后从候选工作区发起生成', async () => {
  const apiChain = { ...emptyChain('api', 'API 测试'), configured: true, candidateMode: true, taskId: 'api-task' }
  apiChain.stages[0] = { ...apiChain.stages[0], stage: 'interface_extract', label: '接口配置提取' }
  apiChain.stages.push({ stage: 'api_design', label: '接口用例设计', order: 1, state: 'not_started', upstreamStages: ['interface_extract'] })
  apiChain.stages.push({ stage: 'generate', label: 'API 用例生成', order: 2, state: 'not_started', upstreamStages: ['interface_extract', 'api_design'] })
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [apiChain] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(apiChain)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ currentToken: 'current', candidateId: null, active: false } as never)
  const list = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const run = vi.spyOn(generationCandidatesApi, 'run').mockResolvedValue({ requestId: 'request', attemptId: 'attempt', replayed: false })
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '接口配置提取 · 未开始' }))
  await screen.findByRole('dialog', { name: '接口配置提取 · 候选与当前内容' })
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  await user.click(within(inspector).getByRole('button', { name: '开始生成' }))
  await waitFor(() => expect(run).toHaveBeenCalledWith('req', 'api', 'interface_extract', expect.objectContaining({ instruction: '只覆盖登录接口', generationMode: 'current' })))
  profiles.mockRestore(); current.mockRestore(); list.mockRestore(); run.mockRestore()
})



it('未配置 UI 时先创建候选链，再打开候选工作区', async () => {
  const unconfigured = { ...chain(), configured: false, taskId: undefined, runId: undefined, stages: [], pendingCandidateCount: 0 }
  const configured = { ...chain(), candidateMode: true, taskId: 'ui-task', runId: undefined }
  let ready = false
  vi.mocked(generationChainApi.overview).mockImplementation(async () => ({ chains: [ready ? configured : unconfigured] }))
  vi.mocked(generationChainApi.chain).mockResolvedValue(configured)
  vi.mocked(requirementDesignApi.configure).mockImplementation(async () => { ready = true; return { taskId: 'ui-task' } as never })
  const profileList = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: null, active: false } as never)
  const candidates = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /开始UI 测试/ }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  await user.click(within(inspector).getByRole('button', { name: '打开候选工作区' }))
  await waitFor(() => expect(requirementDesignApi.configure).toHaveBeenCalledWith('req', 'ui', {
    requestId: expect.any(String), newConfiguration: false,
  }))
  await waitFor(() => expect(generationCandidatesApi.current).toHaveBeenCalledWith('req', 'ui', 'ui_surface'))
  profileList.mockRestore()
  current.mockRestore()
  candidates.mockRestore()
})

it('API 测试从分组侧栏打开接口选择弹框并保存', async () => {
  vi.mocked(requirementDesignApi.configure).mockResolvedValue({ taskId: 'api-task' } as never)
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [{ ...emptyChain('api', 'API 测试'), taskId: '' }] })
  vi.spyOn(interfaceLibraryApi, 'getRequirementSoftwareRepositories').mockResolvedValue([] as never)
  vi.spyOn(interfaceLibraryApi, 'getProjectApiInterfaces').mockResolvedValue(
    Object.assign(
      [
        {
          interfaceId: 'interface-1',
          softwareRepositoryId: 'repository-1',
          softwareRepositoryName: '订单服务',
          name: '创建订单',
          method: 'POST',
          path: '/orders',
          description: '',
          tags: [],
          requirements: [],
          sourceType: 'manual',
        },
      ],
      {
        items: [
          {
            interfaceId: 'interface-1',
            softwareRepositoryId: 'repository-1',
            softwareRepositoryName: '订单服务',
            name: '创建订单',
            method: 'POST',
            path: '/orders',
            description: '',
            tags: [],
            requirements: [],
            sourceType: 'manual',
          },
        ],
        total: 1,
      },
    ) as never,
  )
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: /开始API 测试/ }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByText('尚未选择接口')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(within(inspector).getByRole('button', { name: '选择接口' }))
  const dialog = await screen.findByRole('dialog')
  await user.click(within(dialog).getByLabelText('选择接口'))
  await user.click(await screen.findByText('POST /orders · 订单服务'))
  await user.click(within(dialog).getByRole('button', { name: '保存设置' }))
  await waitFor(() =>
    expect(requirementDesignApi.configure).toHaveBeenCalledWith(
      'req',
      'api',
      expect.objectContaining({ interfaceIds: ['interface-1'] }),
    ),
  )
})





















it('测试点复核失败时展示每条具体问题', async () => {
  const detail = '测试点复核未通过（2 项问题）\n1. 报告生成：缺少成功条件\n2. 语义切片：缺少前置条件'
  const data = chainWith('function', '功能测试', [{
    stage: 'case_names', label: '测试点', order: 0, state: 'failed', errorMessage: detail,
    upstreamStages: [],
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



function reviewArtifact(reviewStatus = 'blocked') {
  return {
    schemaVersion: '1.0',
    artifactType: 'requirement_review',
    reviewStatus,
    summary: {
      scope: 'PRD v1.2 下单流程',
      materialsReviewed: ['PRD.docx'],
      confirmedFacts: ['用户可以在商品详情页点击立即购买'],
      workingAssumptions: ['库存不足指可用库存为 0'],
      hypothesesToVerify: ['支付前是否会重新校验库存'],
      inputGaps: ['缺少库存不足时的接口错误码'],
    },
    issues: [
      {
        id: 'RR-01', topic: '库存不足时的下单行为', type: 'conflict', severity: 'blocker',
        evidence: [{ sourceName: 'PRD.docx', locator: '3.2 下单流程', quote: '库存不足时仍可提交订单' }],
        impact: '实现和测试无法确定库存不足时是创建订单还是拒绝请求。',
        question: '库存不足时到底能不能提交订单？',
        suggestedOwner: 'product', nextAction: '产品确认库存不足场景的业务规则。',
        verifyMethod: 'analysis', failureMode: 'conflict_escape',
      },
    ],
    coverage: {
      structure: [{ name: 'background', status: 'present' }],
      qualityCharacteristics: [{ name: 'unambiguous', status: 'fail', issueIds: ['RR-01'] }],
      smells: [{ type: 'vague', quote: '库存不足时仍可提交订单', issueId: 'RR-01' }],
      behavioralStates: [{ area: 'state', status: 'gap', note: '未说明订单状态' }],
      traceability: [{ kind: 'rule_without_ac', status: 'fail', note: '缺少验收标准', issueId: 'RR-01' }],
      inputAudit: {
        materials: ['PRD.docx'], missing: ['库存不足时的接口错误码'],
        recency: 'PRD 为本次上传版本', comparability: '只评审文档内部一致性',
      },
    },
  }
}

it('候选需求评审展示问题登记，提示不阻断采用', async () => {
  const data = chainWith('requirement_analysis', '需求分析', [
    draftStage('requirement_review', '需求评审', 0),
  ])
  data.candidateMode = true
  const candidate = { candidateId: 'candidate-1', snapshotId: 'snapshot', candidateToken: 'token', currentAttemptId: 'attempt', disposition: 'available', generationMode: 'current', createdAt: '2026-11-20T10:00:00Z', isCurrent: false }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ currentToken: 'current', candidateId: null, active: false } as never)
  const list = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 } as never)
  const detail = vi.spyOn(generationCandidatesApi, 'detail').mockResolvedValue({ ...candidate, content: JSON.stringify(reviewArtifact()), format: 'json' } as never)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '需求评审 · 有候选' }))
  await user.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  const dialog = await screen.findByRole('dialog', { name: '需求评审 · 候选与当前内容' })
  expect(within(dialog).getByText('评审报告仅供人工判断，不阻断材料整理')).toBeInTheDocument()
  await user.click(within(dialog).getByRole('tab', { name: /问题/ }))
  expect(within(dialog).getAllByText('RR-01').length).toBeGreaterThan(0)
  expect(within(dialog).getAllByText(/库存不足时仍可提交订单/).length).toBeGreaterThan(0)
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByRole('button', { name: '采用' })).toBeEnabled()
  await user.click(await within(inspector).findByRole('button', { name: '更多操作' }))
  expect(await screen.findByRole('menuitem', { name: '采用并生成下一阶段' })).toBeEnabled()
  profiles.mockRestore(); current.mockRestore(); list.mockRestore(); detail.mockRestore()
})



function draftStage(stage: string, label: string, order: number, upstreamStages: string[] = []): GenerationChainStage {
  return { stage, label, order, state: 'draft', upstreamStages }
}

function chainWith(kind: GenerationChain['kind'], label: string, stages: GenerationChainStage[]): GenerationChain {
  return {
    kind, label, configured: true, taskId: `task-${kind}`, runId: `run-${kind}`,
    active: false, busy: false, sourceChanged: false, pendingCandidateCount: stages.length, stages,
  }
}



it('需求文档分别连入需求评审和材料整理', async () => {
  const data = chainWith('requirement_analysis', '需求分析', [
    draftStage('requirement_review', '需求评审', 0),
    draftStage('extracting_text', '材料整理', 1),
  ])
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)

  mount()
  await waitFor(() => {
    expect(document.querySelector('[aria-label="Edge from document to requirement_analysis:requirement_review"]')).toBeInTheDocument()
    expect(document.querySelector('[aria-label="Edge from document to requirement_analysis:extracting_text"]')).toBeInTheDocument()
    expect(document.querySelector('[aria-label="Edge from requirement_analysis:requirement_review to requirement_analysis:extracting_text"]')).not.toBeInTheDocument()
  })
})

it('需求分析分组内提供仓库画像候选，进入阅读区后在侧栏运行', async () => {
  const data = chainWith('requirement_analysis', '需求分析', [
    {
      stage: 'extracting_text', label: '材料整理', order: 0, state: 'approved',


      upstreamStages: [],
    },
    {
      ...draftStage('historical_requirement_relations', '历史需求关联', 1),
      upstreamStages: ['extracting_text'],
    },
    draftStage('historical_test_case_verification', '历史用例核验', 2, ['historical_requirement_relations']),
  ])
  data.candidateMode = true
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [data, chainWith('function', '功能测试', [
      { ...draftStage('requirement_analysis', '测试范围与风险分析', 0), upstreamStages: ['extracting_text'] },
    ]), emptyChain('api', 'API 测试'), chain()],
  })
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
  const profileCandidate = { candidateId: 'profile-a', currentAttemptId: 'attempt', createdAt: '2026-11-09T10:00:00Z', isCurrent: true }
  const profile = { repositories: [{ repositoryId: 'repo-1', pathWithNamespace: 'team/repo-1', role: 'backend', responsibilitySummary: '提供登录接口', techStack: ['Java'], keyPaths: ['src'], confidence: 0.9, evidence: ['pom.xml'] }], overallSummary: '当前需求主要涉及后端仓库' }
  vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: 'material-a', invalidatedAt: null } as never)
  vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [profileCandidate], total: 1, page: 1, pageSize: 20 } as never)
  vi.spyOn(profileCandidatesApi, 'current').mockResolvedValue({ candidateId: 'profile-a', currentToken: 'token' } as never)
  vi.spyOn(profileCandidatesApi, 'detail').mockResolvedValue({ ...profileCandidate, content: JSON.stringify(profile), format: 'json' } as never)
  vi.spyOn(interfaceLibraryApi, 'getRequirementSoftwareRepositories').mockResolvedValue([
    {
      softwareRepositoryId: 'repo-1', softwareRepositoryName: 'team/repo-1',
      branch: 'main', baselineBranch: 'main',
    },
  ] as never)

  mount()
  const user = userEvent.setup()
  const card = await screen.findByRole('button', { name: '仓库画像 · 已采用' })
  expect(card).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /生成 UI 用例/ })).not.toBeInTheDocument()
  await waitFor(() => {
    expect(document.querySelector('[aria-label="Edge from requirement_analysis:extracting_text to profile"]')).toBeInTheDocument()
    expect(document.querySelector('[aria-label="Edge from requirement_analysis:extracting_text to function:requirement_analysis"]')).toBeInTheDocument()
    expect(document.querySelector('[aria-label="Edge from requirement_analysis:extracting_text to requirement_analysis:historical_requirement_relations"]')).toBeInTheDocument()
    expect(document.querySelector('[aria-label="Edge from requirement_analysis:historical_requirement_relations to requirement_analysis:historical_test_case_verification"]')).toBeInTheDocument()
    const flowNode = (id: string) => document.querySelector<HTMLElement>(`[data-id="${id}"]`)!
    const position = (node: HTMLElement) => node.style.transform.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px/)!.slice(1).map(Number)
    const group = flowNode('group:function')
    const [groupX, groupY] = position(group)
    const [cardX, cardY] = position(flowNode('requirement_analysis:historical_test_case_verification'))
    expect(cardX).toBeGreaterThanOrEqual(groupX)
    expect(cardY).toBeGreaterThanOrEqual(groupY)
    expect(cardX + 126).toBeLessThan(groupX + Number.parseFloat(group.style.width))
    expect(cardY + 84).toBeLessThan(groupY + Number.parseFloat(group.style.height))
    expect(document.querySelector('[data-testid="rf__edge-profile-to-ui"]')).not.toBeNull()
    expect(document.querySelector('[data-testid="rf__edge-profile-to-api"]')).not.toBeNull()
    expect(document.querySelector('[data-testid="rf__edge-analysis-to-ui"]')).toBeNull()
  })

  await user.click(screen.getByRole('button', { name: '选择API 测试分组' }))
  const apiSource = await screen.findByRole('region', { name: 'API 测试建议后端仓库' })
  expect(await within(apiSource).findByText('team/repo-1')).toBeInTheDocument()
  expect(within(apiSource).getByText(/来自仓库画像 候选/)).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'API 测试接口' })).toBeInTheDocument()

  await user.click(card)
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByText('画像候选')).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: /候选 profile-.*当前/ })).toBeInTheDocument()
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

  mount()
  const card = await screen.findByRole('button', { name: '仓库画像 · 运行中' })
  expect(card).toHaveClass('is-running')
  expect(card).toHaveAttribute('aria-busy', 'true')
  expect(card.querySelector('.gc-running-indicator')).toBeInTheDocument()
})





it('用例图谱节点使用当前完整用例的来源运行', async () => {
  const data = { ...chainWith('function', '功能测试', [
    draftStage('requirement_analysis', '测试范围风险分析', 0),
    {
      stage: 'detailed_cases', label: '完整用例', order: 1, state: 'approved',
      upstreamStages: [],
    },
  ]), candidateMode: true }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [emptyChain('requirement_analysis', '需求分析'), data, emptyChain('api', 'API 测试'), chain()],
  })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({
    candidateId: 'current-cases', currentToken: 'current-token', sourceAttemptId: 'run-version',
  } as never)
  const relations = vi.spyOn(generationCandidatesApi, 'relations').mockResolvedValue({
    candidateId: 'current-cases', currentToken: 'current-token', sourceAttemptId: 'run-version',
    resultYaml: '[]', status: 'not_started', errorMessage: '', caseRelations: null,
  } as never)
  const runRelations = vi.spyOn(generationCandidatesApi, 'runRelations').mockResolvedValue({ attemptId: 'graph', replayed: false })

  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '用例图谱 · 派生' }))
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  const dialog = await screen.findByRole('dialog', { name: '用例图谱' })
  expect(dialog.querySelector('.ant-modal-header')).toBeNull()
  expect(dialog.querySelector('.ai-relations-page-bar')).toBeNull()
  expect(dialog.querySelector('.gc-relations-toolbar')).toBeNull()
  expect(within(inspector).getByRole('heading', { name: '阅读工具' })).toBeInTheDocument()
  await user.click(await within(inspector).findByRole('button', { name: '生成图谱' }))
  await waitFor(() => expect(runRelations).toHaveBeenCalledWith('req', expect.objectContaining({ currentToken: 'current-token', connectionId: 'llm' })))
  profiles.mockRestore(); current.mockRestore(); relations.mockRestore(); runRelations.mockRestore()
})

it('完整用例还没有运行记录时不显示用例图谱节点', async () => {
  const data = chainWith('function', '功能测试', [
    draftStage('requirement_analysis', '测试范围风险分析', 0),
    {
      stage: 'detailed_cases', label: '完整用例', order: 1, state: 'not_started',
      upstreamStages: ['requirement_analysis'],
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









it('画布不再显示缩放按钮、比例和适应画布入口', async () => {
  mount()
  await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' })
  expect(screen.queryByRole('group', { name: '画布缩放' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '放大画布' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '缩小画布' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '适应画布' })).not.toBeInTheDocument()
  expect(screen.queryByRole('group', { name: '筛选生成链' })).not.toBeInTheDocument()
})

it('API 三阶段与功能、UI 测试共用交错布局', async () => {
  const apiChain: GenerationChain = {
    ...emptyChain('api', 'API 测试'),
    configured: true,
    pendingCandidateCount: 1,
    stages: [
      { stage: 'interface_extract', label: '接口配置提取', order: 0, state: 'approved', upstreamStages: [] },
      draftStage('api_design', '接口用例设计', 1, ['interface_extract']),
      { stage: 'generate', label: 'API 用例生成', order: 2, state: 'not_started', upstreamStages: ['interface_extract', 'api_design'] },
    ],
  }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [apiChain] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(apiChain)
  mount()
  await screen.findByRole('button', { name: '接口用例设计 · 有候选' })
  const group = document.querySelector<HTMLElement>('[data-id="group:api"]')!
  expect(Number.parseFloat(group.style.width)).toBeCloseTo(600)
  expect(Number.parseFloat(group.style.height)).toBeCloseTo(280)
  expect(document.querySelector('[aria-label="Edge from api:interface_extract to api:api_design"]')).toBeInTheDocument()
  expect(document.querySelector('[aria-label="Edge from api:api_design to api:generate"]')).toBeInTheDocument()
})

it('API 与 UI 都从仓库画像出线，初始分组不重叠', async () => {
  const analysis = { ...emptyChain('requirement_analysis', '需求分析'), configured: true }
  vi.mocked(generationChainApi.overview).mockResolvedValue({
    chains: [analysis, emptyChain('function', '功能测试'), emptyChain('api', 'API 测试'), chain()],
  })
  mount()
  await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' })
  await waitFor(() => {
    expect(document.querySelector('[aria-label="Edge from requirement_analysis:extracting_text to group:api"]')).not.toBeInTheDocument()
    expect(document.querySelector('[aria-label="Edge from profile to group:api"]')).toBeInTheDocument()
    expect(document.querySelector('[aria-label="Edge from profile to ui:ui_surface"]')).toBeInTheDocument()
  })
  const api = document.querySelector<HTMLElement>('[data-id="group:api"]')!
  const ui = document.querySelector<HTMLElement>('[data-id="group:ui"]')!
  const analysisGroup = document.querySelector<HTMLElement>('[data-id="group:requirement_analysis"]')!
  expect(Number.parseFloat(analysisGroup.style.width)).toBeCloseTo(560)
  expect(Number.parseFloat(analysisGroup.style.height)).toBeCloseTo(320)
  const y = (node: HTMLElement) => Number(node.style.transform.match(/,\s*([\d.]+)px\)/)?.[1])
  expect(y(ui)).toBeGreaterThan(y(api) + Number.parseFloat(api.style.height))
})





it('运行中节点显示状态且保留已采用内容', async () => {
  const data = chain()
  data.candidateMode = true
  data.stages = data.stages.map(stage => stage.stage === 'ui_design' ? { ...stage, state: 'running' } : stage)
  data.active = data.busy = true
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: 'old', currentToken: 'token', content: 'name: 原内容', format: 'yaml', active: true } as never)
  const list = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  mount()
  const running = await screen.findByRole('button', { name: 'UI 用例设计 · 运行中' })
  expect(running).toHaveClass('is-running')
  expect(running).toHaveAttribute('aria-busy', 'true')
  await userEvent.setup().click(running)
  const reading = await screen.findByRole('dialog', { name: 'UI 用例设计 · 候选与当前内容' })
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  expect(within(inspector).getByText('生成中')).toBeInTheDocument()
  expect(within(inspector).getByRole('button', { name: '开始生成' })).toBeDisabled()
  await userEvent.setup().click(within(inspector).getByRole('radio', { name: 'YAML' }).closest('label')!)
  expect(within(reading).getByRole('textbox', { name: '当前内容' })).toHaveTextContent('原内容')
  profiles.mockRestore(); current.mockRestore(); list.mockRestore()
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

it('后续阶段运行时仍可采用前序候选', async () => {
  const running = chain()
  running.candidateMode = true
  running.active = true
  running.busy = true
  running.stages[2] = { ...running.stages[2], state: 'running', activeRunId: 'run' }
  const candidate = { candidateId: 'candidate-1', snapshotId: 'snapshot', candidateToken: 'token', currentAttemptId: 'attempt', disposition: 'available', generationMode: 'current', createdAt: '2026-11-20T10:00:00Z', isCurrent: false }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [running] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(running)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ currentToken: 'current', candidateId: 'adopted', active: false } as never)
  const list = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 } as never)
  const detail = vi.spyOn(generationCandidatesApi, 'detail').mockResolvedValue({ ...candidate, content: 'name: 候选', format: 'yaml' } as never)
  const check = vi.spyOn(generationCandidatesApi, 'checkAdoption').mockResolvedValue({ canAdopt: true, lineageHash: 'lineage', blockingSources: [] })
  const adopt = vi.spyOn(generationCandidatesApi, 'adopt').mockResolvedValue({ requestId: 'req', candidateId: 'candidate-1', contentToken: 'next', replayed: false })
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' }))
  await screen.findByRole('dialog', { name: 'UI 用例设计 · 候选与当前内容' })
  const inspector = screen.getByRole('complementary', { name: '阶段详情' })
  await user.click(await within(inspector).findByRole('button', { name: /候选 candidat/ }))
  await user.click(await within(inspector).findByRole('button', { name: '更多操作' }))
  expect(await screen.findByRole('menuitem', { name: '采用并生成下一阶段' })).toBeEnabled()
  await user.keyboard('{Escape}')
  await user.click(within(inspector).getByRole('button', { name: '采用' }))
  await waitFor(() => expect(adopt).toHaveBeenCalledWith('req', 'ui', 'ui_design', expect.objectContaining({ candidateId: 'candidate-1', expectedAttemptId: 'attempt' })))
  profiles.mockRestore(); current.mockRestore(); list.mockRestore(); detail.mockRestore(); check.mockRestore(); adopt.mockRestore()
})

it('需求文档直接占满画布阅读区，侧栏保持可见，返回后保留流程', async () => {
  const onReadingNodeChange = vi.fn()
  const leave = mount(<div>需求文档阅读内容</div>, onReadingNodeChange)
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
  leave()
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
  const data = { ...chain(), candidateMode: true }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: null, active: false } as never)
  const list = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  vi.stubGlobal('ResizeObserver', class extends OriginalObserver {
    constructor(callback: ResizeObserverCallback) {
      super((entries, observer) => {
        const visibleEntries = entries.filter(entry => !entry.target.closest('.gc-canvas-map[inert]'))
        if (visibleEntries.length) callback(visibleEntries, observer)
      })
    }
  })
  try {
    const leave = mount()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'UI 用例设计 · 有候选' }))
    await screen.findByRole('dialog')
    leave()
    await waitFor(() => {
      const nodes = document.querySelectorAll<HTMLElement>('.react-flow__node')
      expect(nodes.length).toBeGreaterThan(0)
      for (const node of nodes) expect(node).toBeVisible()
    })
  } finally {
    vi.stubGlobal('ResizeObserver', OriginalObserver)
    profiles.mockRestore(); current.mockRestore(); list.mockRestore()
  }
})

it('候选优化保留跨功能的待确认问题与已填写答复', async () => {
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
  const data = chainWith('requirement_analysis', '需求分析', [draftStage('extracting_text', '材料整理', 0)])
  data.candidateMode = true
  const candidate = { candidateId: 'candidate-1', snapshotId: 'snapshot', candidateToken: 'token', currentAttemptId: 'attempt', disposition: 'available', generationMode: 'current', createdAt: '2026-11-20T10:00:00Z', isCurrent: false }
  vi.mocked(generationChainApi.overview).mockResolvedValue({ chains: [data] })
  vi.mocked(generationChainApi.chain).mockResolvedValue(data)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ currentToken: 'current', candidateId: null, active: false } as never)
  const list = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 } as never)
  const detail = vi.spyOn(generationCandidatesApi, 'detail').mockResolvedValue({ ...candidate, content: JSON.stringify(material), format: 'json' } as never)
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '材料整理 · 有候选' }))
  await user.click(await screen.findByRole('button', { name: /候选 candidat/ }))
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
  profiles.mockRestore(); current.mockRestore(); list.mockRestore(); detail.mockRestore()
})

it('完整用例运行时在画布和阅读区展示模块子 Agent 进度', async () => {
  const data = chainWith('function', '功能测试', [{
    stage: 'detailed_cases', label: '完整用例', order: 0, state: 'running', upstreamStages: [], activeRunId: 'modules-run',
    moduleGeneration: {
      attemptId: 'modules-run', sequence: 2, concurrency: 2, status: 'running', modules: [
        { id: '0', module: '文件校验', status: 'completed', caseCount: 3, elapsedMs: 21000, repairAttempt: 0 },
        { id: '1', module: 'IMU 校验', status: 'running', caseCount: 0, elapsedMs: 0, repairAttempt: 0 },
      ],
    },
  }])
  data.active = data.busy = true
  data.candidateMode = true
  const current = vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: null, active: true } as never)
  const candidates = vi.spyOn(generationCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  const profiles = vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0 } as never)
  vi.mocked(repositoryProfileApi.getRepositoryProfileTasks).mockResolvedValue([] as never)
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
  current.mockRestore()
  candidates.mockRestore()
  profiles.mockRestore()
})
