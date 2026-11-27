import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { canNavigateAway } from '@/shared/utils/unsavedChanges'
import { notify } from '@/shared/utils/toast'
import { generationCandidatesApi } from '../api/generationCandidates.api'
import type { CandidateSummary, CurrentStage } from '../api/generationCandidates.contract'
import type { GenerationChainStage } from '../api/generationChain.api'
import { CandidateStageWorkspace } from './CandidateStageWorkspace'
import readableMaterial from '@/domain/requirements/fixtures/readable-material.example.json?raw'
import { parseQuestionRevisionDraft, updateQuestionRevisionDraft } from '../utils/functionalRevision'

vi.mock('@/domain/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))
vi.mock('@/domain/projects/hooks/useProjectRequirementOptions', () => {
  const none = new Map<string, string>()
  return {
    useProjectRequirementOptions: () => ({ requirementNameMap: none, requirementSprintMap: none, sprintNameMap: none }),
  }
})
vi.mock('./UiGenerationInputsModal', () => ({
  UiGenerationInputsModal: ({ onSubmit }: { onSubmit: (inputs: unknown) => Promise<unknown> }) =>
    <button onClick={() => void onSubmit({ functionCaseIds: ['case-a'], sourceProfileCandidateId: 'profile-a', sourceRepositoryId: 'repo-a', sourceCommitMode: 'profile' })}>确认 UI 输入</button>,
}))
vi.mock('./RevisionSidePanel', () => ({
  RevisionSidePanel: ({ value, onChange, onAddAttachment, onSubmit, onCancel }: { value: string; onChange: (value: string) => void; onAddAttachment?: (item: { fileId: string; name: string }) => void; onSubmit: (connectionId: string) => void; onCancel: () => void }) =>
    <div>{parseQuestionRevisionDraft(value) ? <textarea aria-label="补充答复" value={parseQuestionRevisionDraft(value)!.answers[0]} onChange={event => { const draft = parseQuestionRevisionDraft(value)!; onChange(updateQuestionRevisionDraft({ ...draft, answers: [event.target.value, ...draft.answers.slice(1)] })) }} /> : <textarea aria-label="优化指令" value={value} onChange={event => onChange(event.target.value)} />}{onAddAttachment ? <button onClick={() => onAddAttachment({ fileId: 'image', name: 'image.png' })}>添加图片</button> : null}<button onClick={onCancel}>取消优化</button><button onClick={() => onSubmit('llm')}>提交优化</button></div>,
}))
vi.mock('@/shared/components/TextCodeEditor/TextCodeEditor', () => ({
  TextCodeEditor: ({ value, onChange, readOnly, ariaLabel }: { value: string; onChange?: (value: string) => void; readOnly: boolean; ariaLabel: string }) =>
    <textarea aria-label={ariaLabel} value={value} readOnly={readOnly} onChange={event => onChange?.(event.target.value)} />,
}))
vi.mock('@/shared/utils/toast', () => ({
  notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))
vi.mock('../api/generationCandidates.api', () => ({
  generationCandidatesApi: {
    current: vi.fn(), list: vi.fn(), detail: vi.fn(), run: vi.fn(), revise: vi.fn(), checkUiSource: vi.fn(), checkAdoption: vi.fn(), adopt: vi.fn(),
    edit: vi.fn(), derive: vi.fn(), dispose: vi.fn(), previewImport: vi.fn(), importCurrent: vi.fn(),
  },
}))

let workspaceInspector: HTMLDivElement

beforeEach(() => {
  workspaceInspector = document.createElement('div')
  document.body.append(workspaceInspector)
  vi.spyOn(api, 'getLlmConnections').mockResolvedValue({ items: [{ connectionId: 'llm', name: '本人模型', modelId: 'model', status: 'active' }], total: 1 } as never)
})
afterEach(() => {
  cleanup()
  workspaceInspector.remove()
  document.querySelectorAll('[data-test-inspector]').forEach(element => element.remove())
  document.querySelectorAll('.ant-modal-root').forEach(element => element.remove())
  vi.clearAllMocks(); vi.restoreAllMocks(); vi.unstubAllGlobals()
})
const stage: GenerationChainStage = { stage: 'extracting_text', label: '材料整理', order: 1, state: 'approved',  upstreamStages: [] }
const current: CurrentStage = { stage: 'extracting_text', currentToken: 'current-token', candidateId: 'old', content: 'current body', format: 'text', invalidatedAt: null, invalidatedReason: null, active: false }
const candidate: CandidateSummary = { candidateId: 'candidate-b', snapshotId: 'snapshot-b', candidateToken: 'token-b', currentAttemptId: 'attempt-b', derivedFromCandidateId: null, disposition: 'available', generationMode: 'trial', frozenAt: null, createdBy: 'u', createdAt: '2026-11-20T10:00:00Z', isCurrent: false }
// Stage names come from the server-labelled overview, as the canvas already has it cached.
const STAGE_NAMES: Record<string, string> = {
  requirement_review: '需求评审', extracting_text: '材料整理', historical_requirement_relations: '历史需求关联', historical_test_case_verification: '历史用例核验',
  requirement_analysis: '测试范围风险分析', case_names: '测试点', detailed_cases: '完整用例', interface_extract: '接口配置提取', api_design: '接口用例设计',
  generate: 'API 用例生成', ui_surface: '元素控件清单', ui_design: 'UI 用例设计', ui_yaml: '用例 YAML',
}
function createClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(['generationChain', 'req', 'overview'], {
    chains: [['requirement_analysis', '需求分析'], ['function', '功能测试'], ['api', 'API 测试'], ['ui', 'UI 测试']].map(([kind, label]) => ({
      kind, label, configured: true, pendingCandidateCount: 0,
      stages: Object.entries(STAGE_NAMES).map(([name, text], order) => ({ stage: name, label: text, order, state: 'approved', upstreamStages: [] })),
    })),
  })
  return client
}

function setup(overrides: Partial<CurrentStage> = {}, workspaceStage = stage) {
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, ...overrides })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content: 'candidate body', format: 'text' })
  const client = createClient()
  const onClose = vi.fn()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="requirement_analysis" stage={workspaceStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={onClose} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  return { client, onClose }
}

async function findGenerateDialog() {
  const title = await screen.findByText('生成新版本', { selector: '.ant-modal-title' })
  return title.closest('[role="dialog"]') as HTMLElement
}

it('keeps the adopted content visible during generation and separately lists candidates', async () => {
  setup({ active: true })
  expect(await screen.findByDisplayValue('current body')).toBeInTheDocument()
  expect(screen.getByText('生成中')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '开始生成' })).toBeDisabled()
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  expect(await screen.findByDisplayValue('candidate body')).toBeInTheDocument()
})

it('shows the adopted candidate in the current card', async () => {
  const adopted = { ...candidate, candidateId: 'adopted-1', isCurrent: true }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, candidateId: 'adopted-1' })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [adopted, candidate], total: 2, page: 1, pageSize: 20 })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="requirement_analysis" stage={stage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  const currentCard = await screen.findByRole('region', { name: '当前查看' })
  await waitFor(() => expect(currentCard).toHaveTextContent('adopted-'))
  expect(currentCard).toHaveTextContent('当前采用')
  expect(currentCard).toHaveTextContent('当前采用内容')
  expect(screen.queryByRole('button', { name: '查看当前内容' })).not.toBeInTheDocument()
  const candidateBar = await screen.findByRole('group', { name: '选择候选版本' })
  expect(candidateBar).not.toHaveTextContent('已采用')
  expect(candidateBar).toHaveTextContent('候选 candidat')
  expect(screen.queryByRole('button', { name: /候选 adopted/ })).not.toBeInTheDocument()
  expect(await screen.findByDisplayValue('current body')).toBeInTheDocument()
})

it('refreshes candidates when a running attempt completes', async () => {
  const next = { ...candidate, candidateId: 'new-result', currentAttemptId: 'new-attempt' }
  vi.mocked(generationCandidatesApi.list)
    .mockResolvedValueOnce({ items: [], total: 0, page: 1, pageSize: 20 })
    .mockResolvedValue({ items: [next], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, active: true })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="requirement_analysis" stage={stage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  expect(await screen.findByText('生成中')).toBeInTheDocument()
  expect(await screen.findByText('暂无其他候选，生成后会显示在这里。')).toBeInTheDocument()
  act(() => client.setQueryData(['candidateWorkflow', 'req', 'requirement_analysis', 'extracting_text', 'current'], { ...current, active: false }))
  expect(await screen.findByRole('button', { name: /候选 new-resu/ })).toBeInTheDocument()
  expect(screen.getByDisplayValue('current body')).toBeInTheDocument()
  expect(generationCandidatesApi.list).toHaveBeenCalledTimes(2)
})

it('places the generation action after the latest activity', async () => {
  setup()
  const recent = await screen.findByRole('region', { name: '最近生成' })
  const generation = screen.getByRole('region', { name: '生成新版本' })
  expect(recent.compareDocumentPosition(generation) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

it('allows a new run while an existing candidate is awaiting a decision', async () => {
  setup()
  vi.mocked(generationCandidatesApi.run).mockResolvedValue({ requestId: 'request', attemptId: 'next', replayed: false })
  expect(await screen.findByRole('button', { name: /候选 candidat/ })).toBeInTheDocument()
  expect(screen.queryByRole('combobox', { name: /选择 .* 来源/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '开始生成' }))
  await waitFor(() => expect(generationCandidatesApi.run).toHaveBeenCalledWith(
    'req', 'requirement_analysis', 'extracting_text', expect.objectContaining({ generationMode: 'current' }),
  ))
})

it('shows the adopted material visually and can switch to its raw content', async () => {
  setup({ content: readableMaterial, format: 'json' })
  expect(await screen.findByRole('region', { name: '材料整理结果' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('radio', { name: 'JSON' }))
  const rawEditor = screen.getByLabelText('当前内容') as HTMLTextAreaElement
  expect(rawEditor.closest('.gc-reading-body > .gc-artifact-scroll.is-raw')).toBeInTheDocument()
  expect(JSON.parse(rawEditor.value)).toEqual(JSON.parse(readableMaterial))
})

it('shows historical relation candidates and adopted results as a visual reading that can switch to JSON', async () => {
  const content = JSON.stringify({ schemaVersion: '0.1', requirementId: 'req', materialSnapshotId: 'material', artifactType: 'historical_requirement_relation_analysis', relations: [], openQuestions: [] }, null, 2)
  setup({ stage: 'historical_requirement_relations', content, format: 'json' }, { ...stage, stage: 'historical_requirement_relations', label: '历史需求关联' })
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content, format: 'json' })

  expect(await screen.findByRole('complementary', { name: '历史需求关联导航' })).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: '当前内容' })).not.toBeInTheDocument()
  expect(screen.getByRole('region', { name: '当前查看' })).toHaveTextContent('0 条关联')
  fireEvent.click(screen.getByRole('radio', { name: 'JSON' }))
  expect((screen.getByRole('textbox', { name: '当前内容' }) as HTMLTextAreaElement).value).toBe(content)
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  expect(await screen.findByRole('textbox', { name: '候选内容' })).toHaveValue(content)
  fireEvent.click(screen.getByRole('radio', { name: '可视化' }))
  expect(await screen.findByRole('complementary', { name: '历史需求关联导航' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '采用' })).toBeEnabled()
})

it('shows historical test case verification candidates and adopted results as a visual reading that can switch to JSON', async () => {
  const content = JSON.stringify({ schemaVersion: '0.1', requirementId: 'req', materialSnapshotId: 'material', artifactType: 'historical_test_case_verification_result', impactResultId: 'impact-result', batches: [] }, null, 2)
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue({ items: [], total: 0 } as never)
  setup({ stage: 'historical_test_case_verification', content, format: 'json' }, { ...stage, stage: 'historical_test_case_verification', label: '历史用例核验' })
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content, format: 'json' })

  expect(await screen.findByRole('complementary', { name: '历史用例核验导航' })).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: '当前内容' })).not.toBeInTheDocument()
  expect(screen.getByRole('region', { name: '当前查看' })).toHaveTextContent('0 条待维护用例')
  fireEvent.click(screen.getByRole('radio', { name: 'JSON' }))
  expect((screen.getByRole('textbox', { name: '当前内容' }) as HTMLTextAreaElement).value).toBe(content)
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  expect(await screen.findByRole('textbox', { name: '候选内容' })).toHaveValue(content)
  fireEvent.click(screen.getByRole('radio', { name: '可视化' }))
  expect(await screen.findByRole('complementary', { name: '历史用例核验导航' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '采用' })).toBeEnabled()
})

it('lets historical test case verification fill the canvas reading pane edge to edge', async () => {
  const verificationStage: GenerationChainStage = { ...stage, stage: 'historical_test_case_verification', label: '历史用例核验' }
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue({ items: [], total: 0 } as never)
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, stage: verificationStage.stage, content: JSON.stringify({ batches: [] }), format: 'json' })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
  const client = createClient()
  const inspector = document.createElement('div')
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="requirement_analysis" stage={verificationStage} open
    inspectorContainer={inspector} inspectorActionContainer={inspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)

  const rail = await screen.findByRole('complementary', { name: '历史用例核验导航' })
  expect(rail.closest('.p-0')).toBeInTheDocument()
  expect(rail.closest('.p-4')).toBeNull()
})

it.each([
  ['api', 'interface_extract', '接口配置提取', JSON.stringify({ login: { method: 'POST', path: '/v1/login', headers: { 'Content-Type': 'application/json' }, json: { name: 'string' }, response: { code: 'integer' } } }), '/v1/login'],
  ['api', 'api_design', '接口用例设计', JSON.stringify({ schemaVersion: 'api_test_design/1.0', interfaces: { get_task: { method: 'GET', path: '/tasks', cases: [{ id: 'c1', title: '查询任务', category: 'positive', priority: 'P0', intent: '查询任务', basis: { kind: 'positive', section: '', field: '', constraint: '' }, patch: {}, expected: { statusClass: '2xx', assertions: [] } }], uncovered: [] } } }), '查询任务'],
  ['api', 'generate', 'API 用例生成', '- name: 查询任务\n  method: GET\n  path: /api/tasks\n', '查询任务'],
  ['ui', 'ui_surface', '元素控件清单', JSON.stringify({ schemaVersion: 'ui_test_surface/1.0', pages: [{ pageId: 'page', title: '数据检索', route: '/search' }], controls: [], unknowns: [], interactions: [] }), '数据检索'],
  ['ui', 'ui_design', 'UI 用例设计', JSON.stringify({ schemaVersion: 'ui_test_scenarios/2.0', cases: [{ caseId: 'case-1', name: '验证搜索', goal: '搜索', coverage: 'full', sourceTitle: '验证搜索', preconditions: [], limitations: [], steps: [] }], capabilities: { assertions: [], operations: [] } }), '验证搜索'],
  ['ui', 'ui_yaml', '用例 YAML', '- name: 验证搜索\n  enabled: true\n  stepsJson:\n    - orderNo: 1\n      stepName: 打开页面\n      keyword: open\n', '验证搜索'],
] as const)('renders %s stage %s in the candidate workspace', async (kind, stageName, label, body, expected) => {
  const visualStage: GenerationChainStage = { ...stage, stage: stageName, label, upstreamStages: [] }
  const format = body.trimStart().startsWith('{') || body.trimStart().startsWith('[') ? 'json' : 'yaml'
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, stage: stageName, content: body, format })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind={kind} stage={visualStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  expect((await screen.findAllByText(expected)).length).toBeGreaterThan(0)
  fireEvent.click(screen.getByRole('radio', { name: format === 'yaml' ? 'YAML' : 'JSON' }))
  const raw = (screen.getByLabelText('当前内容') as HTMLTextAreaElement).value
  if (body.startsWith('{')) expect(JSON.parse(raw)).toEqual(JSON.parse(body))
  else expect(raw.trim()).toBe(body.trim())
})

it.each([
  ['requirement_analysis', '测试范围风险分析', { schemaVersion: '1.0', artifactType: 'test_scope_impact_risk', testObjects: [{ id: 'TO1', name: '导出转换数据', type: '功能', description: '选择类型导出', sourceBlockIds: ['b1'], basisStatus: 'confirmed' }], impactAreas: [], risks: [], openQuestions: [] }, '导出转换数据'],
  ['case_names', '测试点', { artifactType: 'traceable_test_points', schemaVersion: '1.0', reviewStatus: 'independent_reviewed', testPoints: [{ id: 'P1', module: '导出', dimension: '功能场景', name: '【导出】验证导出成功', materialBlockIds: ['b1'] }], coverageGaps: [] }, '功能场景'],
  ['detailed_cases', '完整用例', { cases: [{ case_module: '导出', case_name: '导出成功', priority: 'P0', steps: '1. 点击导出', expected: '成功' }] }, '导出'],
] as const)('renders functional stage %s in the candidate workspace', async (stageName, label, artifact, expected) => {
  const functionalStage: GenerationChainStage = { ...stage, stage: stageName, label, upstreamStages: [] }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, stage: stageName, content: JSON.stringify(artifact), format: 'json' })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={functionalStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  expect((await screen.findAllByText(expected)).length).toBeGreaterThan(0)
})

it('lets scope analysis fill the canvas reading pane edge to edge', async () => {
  const scopeStage: GenerationChainStage = { ...stage, stage: 'requirement_analysis', label: '测试范围风险分析', upstreamStages: [] }
  const artifact = {
    schemaVersion: '1.0', artifactType: 'test_scope_impact_risk',
    testObjects: [{ id: 'TO1', name: '导出转换数据', type: '功能', description: '选择类型导出', sourceBlockIds: ['b1'], basisStatus: 'confirmed' }],
    impactAreas: [], risks: [], openQuestions: [],
  }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, stage: 'requirement_analysis', content: JSON.stringify(artifact), format: 'json' })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
  const client = createClient()
  const inspector = document.createElement('div')
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={scopeStage} open
    inspectorContainer={inspector} inspectorActionContainer={inspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)

  const detail = await screen.findByRole('region', { name: '测试对象详情' })
  const root = detail.closest('.testScopeRoot')
  expect(root?.closest('.p-0')).toBeInTheDocument()
  expect(root?.closest('.p-4')).toBeNull()
})

it('does not offer a next-stage action for a final candidate', async () => {
  const final: GenerationChainStage = { ...stage, stage: 'generate', label: 'API 用例生成', upstreamStages: [] }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue(current)
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content: 'name: example', format: 'yaml' })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="api" stage={final} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  expect(await screen.findByRole('button', { name: '采用' })).toBeEnabled()
  fireEvent.click(await screen.findByRole('button', { name: '更多操作' }))
  expect(screen.queryByRole('menuitem', { name: '采用并生成下一阶段' })).not.toBeInTheDocument()
})

it('shows the frozen source selection for the selected current content or candidate', async () => {
  const downstream: GenerationChainStage = { ...stage, stage: 'case_names', label: '测试点', upstreamStages: ['requirement_analysis'] }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({
    ...current, stage: 'case_names',
    sourceTrace: [{ chainKind: 'function', stage: 'requirement_analysis', sourceKind: 'current', candidateId: 'current-source', snapshotId: 'snapshot-current' }],
  })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({
    ...candidate, content: 'candidate body', format: 'text',
    sourceTrace: [{ chainKind: 'function', stage: 'requirement_analysis', sourceKind: 'candidate', candidateId: 'candidate-source', snapshotId: 'snapshot-candidate' }],
  })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={downstream} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  expect(await screen.findByTitle(/当前采用内容 current-source/)).toBeInTheDocument()
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  expect(await screen.findByTitle(/候选 candidate-source/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '查看当前内容' }))
  expect(await screen.findByTitle(/当前采用内容 current-source/)).toBeInTheDocument()
})

it('shows the requirement material as the source for a first stage', async () => {
  setup()
  expect((await screen.findAllByText('需求材料')).length).toBeGreaterThan(0)
  expect(screen.getByText('基于')).toBeInTheDocument()
})

it('marks an invalidated current item as needing an update', async () => {
  setup({ invalidatedAt: '2026-11-20T10:00:00Z', invalidatedReason: '历史来源需要重新核验' })
  expect(await screen.findByText('已采用 · 待更新')).toBeInTheDocument()
  expect(screen.getByText('历史来源需要重新核验')).toBeInTheDocument()
})

it('shows the frozen basis without an upstream alignment row or current generation mode', async () => {
  setup({
    candidateId: 'adopted-1',
    basisSources: [
      { chainKind: 'requirement_analysis', stage: 'extracting_text', sourceKind: 'current', candidateId: 'material-old-source', snapshotId: 'snapshot-old', direct: true },
      { chainKind: 'function', stage: 'requirement_analysis', sourceKind: 'current', candidateId: 'analysis-old-source', snapshotId: 'snapshot-analysis', direct: true },
    ],
  })
  expect(await screen.findByText(/材料整理 material/)).toBeInTheDocument()
  expect(screen.getByText('依据')).toBeInTheDocument()
  expect(screen.queryByText('上游对齐')).not.toBeInTheDocument()
  expect(screen.queryByText('生成方式')).not.toBeInTheDocument()
  expect(screen.getByTitle(/候选 material-old-source · 快照 snapshot-old/)).toBeInTheDocument()
  expect(screen.getByDisplayValue('current body')).toBeInTheDocument()
})

it('names basis stages from the server overview, including stages added after the client shipped', async () => {
  setup({
    candidateId: 'adopted-1',
    basisSources: [
      { chainKind: 'requirement_analysis', stage: 'historical_requirement_relations', sourceKind: 'current', candidateId: 'history-source', snapshotId: 'snapshot-history', direct: true },
      { chainKind: 'api', stage: 'api_design', sourceKind: 'current', candidateId: 'design-source', snapshotId: 'snapshot-design', direct: true },
    ],
  })
  expect(await screen.findByText(/历史需求关联 history- · 接口用例设计 design-/)).toBeInTheDocument()
})

it('checks adoption and explains a concurrent change without adopting', async () => {
  setup()
  vi.mocked(generationCandidatesApi.checkAdoption).mockResolvedValue({ canAdopt: false, lineageHash: 'lineage', blockingSources: [{ chainKind: 'requirement_analysis', stage: 'extracting_text', reason: 'concurrent_change' }] })
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '采用' }))
  expect(await screen.findByText('材料整理：内容或来源已变化，请刷新后重试')).toBeInTheDocument()
  expect(generationCandidatesApi.adopt).not.toHaveBeenCalled()
})

it('adopts a candidate whose frozen basis uses an upstream no longer selected', async () => {
  setup({
    candidateId: 'adopted-1',
    basisSources: [{ chainKind: 'requirement_analysis', stage: 'extracting_text', sourceKind: 'current', candidateId: 'material-old-source', snapshotId: 'snapshot-old', direct: true }],
  })
  vi.mocked(generationCandidatesApi.checkAdoption).mockResolvedValue({ canAdopt: true, lineageHash: 'lineage', blockingSources: [] })
  vi.mocked(generationCandidatesApi.adopt).mockResolvedValue({ requestId: 'request', candidateId: 'candidate-b', contentToken: 'token-new', replayed: false })
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '采用' }))
  await waitFor(() => expect(generationCandidatesApi.adopt).toHaveBeenCalled())
})

it('rejects a candidate while retaining the adopted content', async () => {
  setup()
  vi.mocked(generationCandidatesApi.dispose).mockResolvedValue({ requestId: 'request', candidateId: 'candidate-b', candidateToken: 'new-token', disposition: 'rejected' })
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '更多操作' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: '拒绝候选' }))
  fireEvent.click(await screen.findByRole('button', { name: /确\s*定|OK/ }))
  await waitFor(() => expect(generationCandidatesApi.dispose).toHaveBeenCalledWith(
    'req', 'requirement_analysis', 'extracting_text', 'candidate-b',
    expect.objectContaining({ action: 'reject', expectedCandidateToken: 'token-b' }),
  ))
  expect(await screen.findByDisplayValue('current body')).toBeInTheDocument()
})

it('deletes a candidate and returns to the adopted content', async () => {
  setup()
  vi.mocked(generationCandidatesApi.dispose).mockResolvedValue({ requestId: 'request', candidateId: 'candidate-b', candidateToken: null, disposition: 'deleted' })
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '更多操作' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: '删除候选' }))
  fireEvent.click(await screen.findByRole('button', { name: /确\s*定|OK/ }))
  await waitFor(() => expect(generationCandidatesApi.dispose).toHaveBeenCalledWith(
    'req', 'requirement_analysis', 'extracting_text', 'candidate-b',
    expect.objectContaining({ action: 'delete', expectedCandidateToken: 'token-b' }),
  ))
  expect(await screen.findByDisplayValue('current body')).toBeInTheDocument()
})

it('submits revision of the selected candidate with its uploaded images', async () => {
  setup()
  vi.mocked(generationCandidatesApi.revise).mockResolvedValue({ requestId: 'r', attemptId: 'next', replayed: false })
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '继续优化' }))
  fireEvent.change(screen.getByRole('textbox', { name: '优化指令' }), { target: { value: '按截图补充' } })
  fireEvent.click(screen.getByRole('button', { name: '添加图片' }))
  fireEvent.click(screen.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(notify.success).toHaveBeenCalledWith({ title: '已开始优化', description: '将生成新候选；原候选和当前内容会保留。' }))
  expect(generationCandidatesApi.revise).toHaveBeenCalledWith('req', 'requirement_analysis', 'extracting_text', 'candidate-b', expect.objectContaining({
    expectedCandidateToken: 'token-b', expectedAttemptId: 'attempt-b', connectionId: 'llm', instruction: '按截图补充', attachmentFileIds: ['image'],
  }))
})

it('retains answers to pending questions and submits only the readable instruction', async () => {
  setup()
  const material = { ...JSON.parse(readableMaterial), questions: [{ id: 'Q1', question: '何时生效？', status: 'open' }] }
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content: JSON.stringify(material), format: 'json' })
  vi.mocked(generationCandidatesApi.revise).mockResolvedValue({ attemptId: 'next', requestId: 'req', replayed: false })
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '继续优化' }))
  fireEvent.change(screen.getByLabelText('补充答复'), { target: { value: '立即生效' } })
  fireEvent.click(screen.getByRole('button', { name: '取消优化' }))
  fireEvent.click(screen.getByRole('button', { name: '继续优化' }))
  expect(screen.getByLabelText('补充答复')).toHaveValue('立即生效')
  fireEvent.click(screen.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(generationCandidatesApi.revise).toHaveBeenCalledWith(
    'req', 'requirement_analysis', 'extracting_text', 'candidate-b',
    expect.objectContaining({ instruction: expect.stringContaining('何时生效？\n答复：立即生效') }),
  ))
})

it('uses free-form instructions when revising requirement review', async () => {
  const reviewStage: GenerationChainStage = { ...stage, stage: 'requirement_review', label: '需求评审' }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue(current)
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content: JSON.stringify({ questions: [{ id: 'Q1', question: '待补充？' }] }), format: 'json' })
  vi.mocked(generationCandidatesApi.revise).mockResolvedValue({ attemptId: 'next', requestId: 'req', replayed: false })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="requirement_analysis" stage={reviewStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '继续优化' }))
  expect(screen.queryByLabelText('补充答复')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('优化指令'), { target: { value: '补充返回规则' } })
  fireEvent.click(screen.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(generationCandidatesApi.revise).toHaveBeenCalledWith(
    'req', 'requirement_analysis', 'requirement_review', 'candidate-b',
    expect.objectContaining({ instruction: '补充返回规则' }),
  ))
})

it('keeps an unfinished revision when navigation is canceled', async () => {
  setup()
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '继续优化' }))
  fireEvent.change(screen.getByRole('textbox', { name: '优化指令' }), { target: { value: '未提交的要求' } })
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  expect(canNavigateAway()).toBe(false)
  expect(confirm).toHaveBeenCalledOnce()
  expect(screen.getByDisplayValue('未提交的要求')).toBeInTheDocument()
})

it('reports adoption separately when starting the next stage fails', async () => {
  const pointStage: GenerationChainStage = { ...stage, stage: 'case_names', label: '测试点', upstreamStages: ['requirement_analysis'] }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, stage: 'case_names' })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content: 'candidate body', format: 'text' })
  vi.mocked(generationCandidatesApi.checkAdoption).mockResolvedValue({ canAdopt: true, lineageHash: 'lineage', blockingSources: [] })
  vi.mocked(generationCandidatesApi.adopt).mockResolvedValue({ requestId: 'r', candidateId: 'candidate-b', contentToken: 'new', replayed: false, continuationError: '上游已变化，请刷新后重试' })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={pointStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '补充场景' })} /></QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '更多操作' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: '采用并生成下一阶段' }))
  await waitFor(() => expect(notify.warning).toHaveBeenCalledWith({ title: '已采用该候选，下一阶段未启动', description: '上游已变化，请刷新后重试' }))
  expect(generationCandidatesApi.adopt).toHaveBeenCalledWith('req', 'function', 'case_names', expect.objectContaining({
    continueAfter: true, connectionId: 'llm', instruction: '补充场景', expectedCurrentToken: 'current-token',
  }))
})

it.each([
  ['interface_extract', '接口配置提取'],
  ['api_design', '接口用例设计'],
])('adopts API stage %s before starting the next stage', async (stageName, label) => {
  const apiStage: GenerationChainStage = { ...stage, stage: stageName, label, upstreamStages: [] }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, stage: stageName })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content: 'candidate body', format: 'text' })
  vi.mocked(generationCandidatesApi.checkAdoption).mockResolvedValue({ canAdopt: true, lineageHash: 'lineage', blockingSources: [] })
  vi.mocked(generationCandidatesApi.adopt).mockResolvedValue({ requestId: 'r', candidateId: 'candidate-b', contentToken: 'new', replayed: false, continuationAttemptId: 'next' })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="api" stage={apiStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '覆盖边界' })} /></QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '更多操作' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: '采用并生成下一阶段' }))
  await waitFor(() => expect(generationCandidatesApi.adopt).toHaveBeenCalledWith(
    'req', 'api', stageName, expect.objectContaining({
      candidateId: 'candidate-b', expectedCurrentToken: 'current-token', expectedAttemptId: 'attempt-b',
      continueAfter: true, connectionId: 'llm', instruction: '覆盖边界',
    }),
  ))
  expect(generationCandidatesApi.checkAdoption).toHaveBeenCalledOnce()
})

it('keeps unsaved candidate edits when navigation is canceled', async () => {
  setup()
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '编辑' }))
  fireEvent.change(screen.getByLabelText('候选内容'), { target: { value: 'unsaved change' } })
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  expect(canNavigateAway()).toBe(false)
  expect(confirm).toHaveBeenCalledOnce()
  expect(screen.getByDisplayValue('unsaved change')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('button', { name: '保存候选' })).toBeEnabled())
})

it('edits and saves candidate material through the visual view', async () => {
  setup()
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content: readableMaterial, format: 'json' })
  vi.mocked(generationCandidatesApi.edit).mockResolvedValue({} as never)
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '编辑' }))
  const field = await screen.findByRole('textbox', { name: '保存 功能使用与业务规则 内容 1' })
  fireEvent.change(field, { target: { value: '更新后的规则' } })
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  expect(canNavigateAway()).toBe(false)
  expect(confirm).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button', { name: '保存候选' }))
  await waitFor(() => expect(generationCandidatesApi.edit).toHaveBeenCalledWith(
    'req', 'requirement_analysis', 'extracting_text', 'candidate-b',
    expect.objectContaining({ content: expect.stringContaining('更新后的规则') }),
  ))
})

it('edits a generated test case through the candidate visual form', async () => {
  vi.stubGlobal('DOMMatrixReadOnly', class { m22 = 1 })
  vi.stubGlobal('ResizeObserver', class {
    callback: ResizeObserverCallback
    constructor(callback: ResizeObserverCallback) { this.callback = callback }
    observe(target: Element) { queueMicrotask(() => this.callback([{ target, contentRect: { width: 400, height: 100 } } as ResizeObserverEntry], this as unknown as ResizeObserver)) }
    unobserve() {}
    disconnect() {}
  })
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(400)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(100)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, width: 1200, height: 800, top: 0, right: 1200, bottom: 800, left: 0, toJSON: () => ({}) } as DOMRect)
  const caseStage: GenerationChainStage = { ...stage, stage: 'detailed_cases', label: '完整用例' }
  const body = JSON.stringify({ cases: [{ case_id: 'case-1', case_module: '模块', case_title: '原名称' }] })
  vi.mocked(generationCandidatesApi.current).mockResolvedValue(current)
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content: body, format: 'json' })
  vi.mocked(generationCandidatesApi.edit).mockResolvedValue({} as never)
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={caseStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '编辑' }))
  fireEvent.change(await screen.findByRole('textbox', { name: '用例名称' }), { target: { value: '新名称' } })
  fireEvent.click(screen.getByRole('button', { name: '保存候选' }))
  await waitFor(() => expect(generationCandidatesApi.edit).toHaveBeenCalledWith(
    'req', 'function', 'detailed_cases', 'candidate-b',
    expect.objectContaining({ content: expect.stringContaining('新名称') }),
  ))
})

it('formats compact JSON without treating formatting as an unsaved edit', async () => {
  setup()
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content: '{"questions":[]}', format: 'json' })
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('radio', { name: 'JSON' }))
  expect(screen.getByLabelText('候选内容')).toHaveValue('{\n  "questions": []\n}')
  fireEvent.click(screen.getByRole('button', { name: '编辑' }))
  expect(canNavigateAway()).toBe(true)
  expect(confirm).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('候选内容'), { target: { value: '{"questions":[1]}' } })
  expect(canNavigateAway()).toBe(false)
})

it('passes an explicitly selected candidate as the trial upstream', async () => {
  const sourceStage: GenerationChainStage = { ...stage, stage: 'case_names', label: '测试点', upstreamStages: ['requirement_analysis'] }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue(current)
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.run).mockResolvedValue({ requestId: 'request', attemptId: 'attempt', replayed: false })
  const chooseConnection = vi.fn(async () => ({ connectionId: 'separate-dialog', instruction: '' }))
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={sourceStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={chooseConnection} /></QueryClientProvider>)
  const generateButton = await screen.findByRole('button', { name: '开始生成' })
  await waitFor(() => expect(generateButton).toBeEnabled())
  fireEvent.click(generateButton)
  const dialog = await findGenerateDialog()
  const select = await within(dialog).findByRole('combobox', { name: '选择 测试范围风险分析 来源' })
  await waitFor(() => expect(select.closest('.ant-select')).toHaveTextContent('当前采用内容'))
  fireEvent.mouseDown(select)
  fireEvent.click(await screen.findByText(/候选 candidat.*11\/20/, { selector: '.ant-select-item-option-content' }))
  const confirm = within(dialog).getByRole('button', { name: '开始生成' })
  await waitFor(() => expect(confirm).toBeEnabled())
  fireEvent.click(confirm)
  await waitFor(() => expect(generationCandidatesApi.run).toHaveBeenCalledWith('req', 'function', 'case_names', expect.objectContaining({
    connectionId: 'llm', generationMode: 'trial', sourceSelections: [expect.objectContaining({ sourceKind: 'candidate', candidateId: 'candidate-b', snapshotId: 'snapshot-b', expectedCandidateToken: 'token-b' })],
  })))
  expect(chooseConnection).not.toHaveBeenCalled()
})

it('defaults to the current upstream without a separate source mode choice', async () => {
  const sourceStage: GenerationChainStage = { ...stage, stage: 'case_names', label: '测试点', upstreamStages: ['requirement_analysis'] }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue(current)
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.run).mockResolvedValue({ requestId: 'request', attemptId: 'attempt', replayed: false })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={sourceStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'separate-dialog', instruction: '' })} /></QueryClientProvider>)
  const generateButton = await screen.findByRole('button', { name: '开始生成' })
  await waitFor(() => expect(generateButton).toBeEnabled())
  fireEvent.click(generateButton)
  const dialog = await findGenerateDialog()
  const select = await within(dialog).findByRole('combobox', { name: '选择 测试范围风险分析 来源' })
  await waitFor(() => expect(select.closest('.ant-select')).toHaveTextContent('当前采用内容'))
  expect(within(dialog).queryByRole('radio', { name: /使用当前上游|选择指定候选/ })).not.toBeInTheDocument()
  const confirm = within(dialog).getByRole('button', { name: '开始生成' })
  await waitFor(() => expect(confirm).toBeEnabled())
  fireEvent.click(confirm)
  await waitFor(() => expect(generationCandidatesApi.run).toHaveBeenCalledWith('req', 'function', 'case_names', expect.objectContaining({
    connectionId: 'llm', generationMode: 'current',
  })))
  const body = vi.mocked(generationCandidatesApi.run).mock.calls[0][3]
  expect(body).not.toHaveProperty('sourceSelections')
})

it('blocks normal generation without an adopted upstream but allows a candidate trial', async () => {
  const pointStage: GenerationChainStage = { ...stage, stage: 'case_names', label: '测试点', upstreamStages: ['requirement_analysis'] }
  vi.mocked(generationCandidatesApi.current).mockImplementation(async (_r, _k, name) => ({ ...current, stage: name, candidateId: null, invalidatedAt: null }))
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.run).mockResolvedValue({ requestId: 'request', attemptId: 'attempt', replayed: false })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={pointStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  const generateButton = await screen.findByRole('button', { name: '开始生成' })
  await waitFor(() => expect(generateButton).toBeEnabled())
  fireEvent.click(generateButton)
  const dialog = await findGenerateDialog()
  expect(within(dialog).getByText('请先采用有效的上游内容，或选择候选进行试生成。')).toBeInTheDocument()
  const confirm = () => within(dialog).getByRole('button', { name: '开始生成' })
  expect(confirm()).toBeDisabled()
  fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: '选择 测试范围风险分析 来源' }))
  fireEvent.click(await screen.findByText(/候选 candidat.*11\/20/, { selector: '.ant-select-item-option-content' }))
  await waitFor(() => expect(confirm()).toBeEnabled())
  fireEvent.click(confirm())
  await waitFor(() => expect(generationCandidatesApi.run).toHaveBeenCalledWith(
    'req', 'function', 'case_names', expect.objectContaining({ generationMode: 'trial' }),
  ))
})

it('UI 首阶段把当前画像、仓库、正式用例和个人授权作为候选输入', async () => {
  const uiStage: GenerationChainStage = { ...stage, stage: 'ui_surface', label: '元素控件清单' }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, stage: 'ui_surface' })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.run).mockResolvedValue({ requestId: 'request', attemptId: 'attempt', replayed: false })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="ui" stage={uiStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} chooseGitlab={async () => 'gitlab'} /></QueryClientProvider>)
  await waitFor(() => expect(screen.getByRole('button', { name: '开始生成' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: '开始生成' }))
  fireEvent.click(screen.getByRole('button', { name: '确认 UI 输入' }))
  await waitFor(() => expect(generationCandidatesApi.run).toHaveBeenCalledWith('req', 'ui', 'ui_surface', expect.objectContaining({
    sourceProfileCandidateId: 'profile-a', sourceRepositoryId: 'repo-a', sourceCommitMode: 'profile', functionCaseIds: ['case-a'], gitlabConnectionId: 'gitlab',
  })))
})

it('检查候选冻结 commit，不改变候选来源', async () => {
  const uiStage: GenerationChainStage = { ...stage, stage: 'ui_surface', label: '元素控件清单' }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, stage: 'ui_surface' })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.detail).mockResolvedValue({ ...candidate, content: 'candidate body', format: 'text', sourceInputs: {
    sourceKind: 'repository', repository: { repositoryId: 'repo-a', pathWithNamespace: 'team/ui', branch: 'main', commit: 'fixed', commitMode: 'profile', profileCandidateId: '', resolvedAt: '' }, cases: [], sourceBatchId: 'batch-a',
  } })
  vi.mocked(generationCandidatesApi.checkUiSource).mockResolvedValue({ pinnedCommit: 'fixed', currentCommit: 'new', branch: 'main', changed: true })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="ui" stage={uiStage} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} chooseGitlab={async () => 'gitlab'} /></QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: /候选 candidat/ }))
  fireEvent.click(await screen.findByRole('button', { name: '检查分支更新' }))
  expect(await screen.findByText('分支已有新提交，候选仍使用冻结的 commit。')).toBeInTheDocument()
  expect(generationCandidatesApi.checkUiSource).toHaveBeenCalledWith('req', 'ui_surface', 'candidate-b', { expectedCandidateToken: 'token-b', gitlabConnectionId: 'gitlab' })
})

it('shows both sides of an import conflict before confirming the overwrite', async () => {
  const final: GenerationChainStage = { ...stage, stage: 'detailed_cases', label: '详细用例' }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue(current)
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.previewImport).mockResolvedValue({
    currentToken: 'current-token', fullLineageHash: 'lineage', contentHash: 'content', basisHash: 'basis',
    candidateId: 'old', targetId: '', previewToken: 'preview',
    previewExpiresAt: Math.floor(Date.now() / 1000) + 60, requiresConfirmation: true,
    conflicts: [{ normalizedName: '登录', existingCase: { title: '已有用例' }, generatedCase: { title: '新用例' } }],
  })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={final} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: '预览并导入' }))
  expect(await screen.findByText('登录')).toBeInTheDocument()
  expect(screen.getByText(/已有用例/, { selector: 'pre' })).toBeInTheDocument()
  expect(screen.getByText(/新用例/, { selector: 'pre' })).toBeInTheDocument()
  expect(generationCandidatesApi.importCurrent).not.toHaveBeenCalled()
})

it('requires a formal target before previewing an API import', async () => {
  const final: GenerationChainStage = { ...stage, stage: 'generate', label: 'API 用例生成', upstreamStages: [] }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({ ...current, stage: 'generate', content: 'name: example', format: 'yaml' })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
  vi.spyOn(api, 'getApiCollections').mockResolvedValue({ items: [{ collectionId: 'collection-a', name: '接口用例集' }] } as never)
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="api" stage={final} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)

  fireEvent.click(await screen.findByRole('button', { name: '预览并导入' }))
  expect(await screen.findByRole('combobox', { name: '正式导入目标' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '预览导入' })).toBeDisabled()
  expect(generationCandidatesApi.previewImport).not.toHaveBeenCalled()
})

it('does not offer import for stale adopted current content', async () => {
  const final: GenerationChainStage = { ...stage, stage: 'detailed_cases', label: '完整用例' }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({
    ...current,
    stage: 'detailed_cases',
    invalidatedAt: '2026-11-24T10:00:00Z',
    invalidatedReason: '上游内容已变化',
    content: JSON.stringify({ cases: [{ case_module: '导出', case_name: '导出成功', priority: 'P0', steps: '1. 点击导出', expected: '成功' }] }),
    format: 'json',
  })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={final} open inspectorContainer={workspaceInspector} inspectorActionContainer={workspaceInspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)

  expect(await screen.findByText(/已采用 · 待更新/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '预览并导入' })).not.toBeInTheDocument()
})

it('moves the final-stage import entry into the sidebar footer and previews in a modal', async () => {
  const final: GenerationChainStage = { ...stage, stage: 'detailed_cases', label: '完整用例', upstreamStages: [] }
  vi.mocked(generationCandidatesApi.current).mockResolvedValue({
    ...current, stage: 'detailed_cases',
    content: JSON.stringify({ cases: [{ case_module: '导出', case_name: '导出成功', priority: 'P0', steps: '1. 点击导出', expected: '成功' }] }),
    format: 'json',
  })
  vi.mocked(generationCandidatesApi.list).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
  vi.mocked(generationCandidatesApi.previewImport).mockResolvedValue({
    currentToken: 'current-token', fullLineageHash: 'lineage', contentHash: 'content', basisHash: 'basis',
    candidateId: 'old', targetId: '', previewToken: 'preview',
    previewExpiresAt: Math.floor(Date.now() / 1000) + 60, requiresConfirmation: true,
    conflicts: [{ normalizedName: '登录', existingCase: { title: '已有用例' }, generatedCase: { title: '新用例' } }],
  })
  const inspector = document.createElement('div')
  inspector.dataset.testInspector = 'true'
  document.body.append(inspector)
  const client = createClient()
  render(<QueryClientProvider client={client}><CandidateStageWorkspace requirementId="req" projectId="project" kind="function" stage={final} open
    inspectorContainer={inspector} inspectorActionContainer={inspector} onClose={() => {}} chooseConnection={async () => ({ connectionId: 'llm', instruction: '' })} /></QueryClientProvider>)

  const trigger = await within(inspector).findByRole('button', { name: '预览并导入' })
  expect(within(inspector).getByRole('region', { name: '导入正式用例' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '预览导入' })).not.toBeInTheDocument()
  fireEvent.click(trigger)
  expect(await screen.findByText('登录')).toBeInTheDocument()
  expect(generationCandidatesApi.previewImport).toHaveBeenCalledWith('req', 'function', 'detailed_cases', { expectedCurrentToken: 'current-token', targetId: '' })
})
