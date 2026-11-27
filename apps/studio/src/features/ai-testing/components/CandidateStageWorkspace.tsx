import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Empty, Input, Modal, Pagination, Radio, Select, Spin, Tag } from 'antd'
import { CheckOutlined, ClockCircleOutlined, InfoCircleOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { api, listItems } from '@/services/api'
import { useProjectAccess } from '@/domain/projects/hooks/useProjectAccess'
import { CANDIDATE_ACTIVE_POLL_INTERVAL, CANDIDATE_IDLE_POLL_INTERVAL } from '@/domain/runs/polling'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { randomId } from '@/shared/utils/crypto'
import { notify } from '@/shared/utils/toast'
import { UNSAVED_NAVIGATION_EVENT } from '@/shared/utils/unsavedChanges'
import { getErrorMessage, formatCompactTime } from '@/utils/format'
import { generationCandidatesApi } from '../api/generationCandidates.api'
import { useRevisionAttachments } from '../hooks/useRevisionAttachments'
import { useGenerationStageLabels } from '../hooks/useRequirementGenerationChain'
import type {
  AdoptionCheck, CandidateAdoptBody, CandidateChainKind, CandidateRunBody,
  CandidateSourceSelection, CandidateSummary, CurrentImportPreview, CurrentSourceSelection,
} from '../api/generationCandidates.contract'
import type { GenerationChainStage, UiGenerationRunInputs, UiGenerationSourceCheck } from '../api/generationChain.api'
import { GenerationArtifactFrame } from './GenerationArtifactFrame'
import { CandidateStageActions } from './CandidateStageActions'
import { RevisionSidePanel } from './RevisionSidePanel'
import { UiGenerationInputsModal } from './UiGenerationInputsModal'
import { UiGenerationSourceTrace } from './UiGenerationSourceTrace'
import { TraceablePointsView } from './TraceablePointsView'
import { GeneratedCasesReviewView } from './GeneratedCasesReviewView'
import { RequirementMaterialComparison } from './RequirementMaterialComparison'
import { HistoricalRelationView } from './HistoricalRelationView'
import { HistoricalCaseVerificationView } from './HistoricalCaseVerificationView'
import { RequirementReviewView } from './RequirementReviewView'
import { RequirementAnalysisDiagramView } from './RequirementAnalysisView'
import { CandidateImportModal } from './CandidateImportModal'
import { ApiCandidateResultView, ApiConfigDiagramView } from './ApiConfigDiagramView'
import { ApiDesignDiagramView } from './ApiDesignDiagramView'
import { UiStageVisual } from './uiStageVisual/UiStageVisual'
import type { UiGenerationStage } from '../utils/uiGenerationStage'
import { ModuleGenerationProgressPanel } from './ModuleGenerationProgressPanel'
import { buildRevisionTemplate, createQuestionRevisionDraft, getRevisionQuestions, revisionInstructionText } from '../utils/functionalRevision'
import { formatJsonArtifact } from '../utils/artifactFormat'
import { stageContentStats } from '../utils/stageContentStats'
import type { UiGenerationSourceOptionsState } from './UiGenerationSourceConfig'
import chainStyles from '../styles/generation-chain.module.css'
import canvasStyles from '../styles/generation-canvas.module.css'
import candidateStyles from '../styles/candidate-workspace.module.css'
import caseArtifactStyles from '../styles/artifact-cases.module.css'
import uiStageStyles from '../styles/ui-stage-visual.module.css'

type SourceChoice = CandidateSourceSelection | CurrentSourceSelection
const PAGE_SIZE = 20
const CONTINUATION_STAGES = new Set(['requirement_review', 'requirement_analysis', 'case_names', 'interface_extract', 'api_design', 'ui_surface', 'ui_design', 'historical_requirement_relations'])

function sourceKind(stage: string, ownKind: CandidateChainKind): CandidateChainKind {
  return stage === 'extracting_text' ? 'requirement_analysis' : ownKind
}

function label(candidate: CandidateSummary) {
  return `候选 ${candidate.candidateId.slice(0, 8)} · ${formatCompactTime(candidate.createdAt)}`
}

function candidateModeLabel(candidate: CandidateSummary) {
  if (candidate.generationMode === 'trial') return '试生成'
  if (candidate.derivedFromCandidateId) return '编辑派生'
  return '生成'
}

function canRenderVisual(kind: CandidateChainKind, content: string) {
  if (kind !== 'requirement_analysis' && kind !== 'function') return true
  try {
    JSON.parse(content)
    return true
  } catch {
    return false
  }
}

/** A single stage workspace; it reads current content and candidates separately. */
export function CandidateStageWorkspace({ requirementId, projectId, kind, stage, open, onClose, chooseConnection, chooseGitlab, gitlabDialog, uiSourceOptions, onOpenProfile, inspectorContainer, inspectorActionContainer }: {
  requirementId: string
  projectId: string
  kind: CandidateChainKind
  stage: GenerationChainStage
  open: boolean
  inspectorContainer?: HTMLElement | null
  inspectorActionContainer?: HTMLElement | null
  onClose: () => void
  chooseConnection: () => Promise<{ connectionId: string; instruction: string }>
  chooseGitlab?: (projectId: string) => Promise<string>
  gitlabDialog?: ReactNode
  uiSourceOptions?: UiGenerationSourceOptionsState
  onOpenProfile?: () => void
}) {
  const client = useQueryClient()
  const access = useProjectAccess(projectId)
  const stageLabel = useGenerationStageLabels(requirementId, open)
  const [uiInputsOpen, setUiInputsOpen] = useState(false)
  const [uiSourceCheck, setUiSourceCheck] = useState<(UiGenerationSourceCheck & { candidateId: string }) | null>(null)
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState('current')
  const [edit, setEdit] = useState<string | null>(null)
  const [editBaseline, setEditBaseline] = useState('')
  const [revisionOpen, setRevisionOpen] = useState(false)
  const [revisionInstruction, setRevisionInstruction] = useState('')
  const [revisionInitial, setRevisionInitial] = useState('')
  const revisionCandidate = useRef('')
  const revisionAttachments = useRevisionAttachments()
  const [viewMode, setViewMode] = useState<'visual' | 'raw'>('visual')
  const [choices, setChoices] = useState<Record<string, SourceChoice>>({})
  const [sourcePages, setSourcePages] = useState<Record<string, number>>({})
  const [generateOpen, setGenerateOpen] = useState(false)
  const [connectionId, setConnectionId] = useState('')
  const [instruction, setInstruction] = useState('')
  const [pendingModel, setPendingModel] = useState<{ connectionId: string; instruction: string } | null>(null)
  const [check, setCheck] = useState<AdoptionCheck | null>(null)
  const [targetId, setTargetId] = useState('')
  const [preview, setPreview] = useState<CurrentImportPreview | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const importPreviewRequest = useRef(0)
  const pendingIds = useRef<Record<string, { key: string; id: string }>>({})
  const closeConfirmed = useRef(false)
  const wasActive = useRef(false)
  const current = useQuery({
    queryKey: ['candidateWorkflow', requirementId, kind, stage.stage, 'current'],
    queryFn: () => generationCandidatesApi.current(requirementId, kind, stage.stage),
    enabled: open,
    refetchInterval: query => query.state.data?.active ? CANDIDATE_ACTIVE_POLL_INTERVAL : CANDIDATE_IDLE_POLL_INTERVAL,
  })
  const candidates = useQuery({
    queryKey: ['candidateWorkflow', requirementId, kind, stage.stage, 'list', page],
    queryFn: () => generationCandidatesApi.list(requirementId, kind, stage.stage, page, PAGE_SIZE),
    enabled: open,
    refetchInterval: current.data?.active ? CANDIDATE_ACTIVE_POLL_INTERVAL : false,
  })
  const refetchCandidates = candidates.refetch
  useEffect(() => {
    if (current.data?.active) {
      wasActive.current = true
    } else if (current.data && wasActive.current) {
      wasActive.current = false
      void refetchCandidates()
      void client.invalidateQueries({ queryKey: ['generationChain', requirementId] })
    }
  }, [current.data?.active, current.data, refetchCandidates, client, requirementId])
  const detail = useQuery({
    queryKey: ['candidateWorkflow', requirementId, kind, stage.stage, 'detail', selectedId],
    queryFn: () => generationCandidatesApi.detail(requirementId, kind, stage.stage, selectedId),
    enabled: open && selectedId !== 'current',
  })
  const sources = useQueries({
    queries: stage.upstreamStages.map(name => {
      const upstreamKind = sourceKind(name, kind)
      const sourcePage = sourcePages[name] ?? 1
      return {
        queryKey: ['candidateWorkflow', requirementId, upstreamKind, name, 'sources', sourcePage],
        queryFn: async () => {
          const [slot, list] = await Promise.all([
            generationCandidatesApi.current(requirementId, upstreamKind, name),
            generationCandidatesApi.list(requirementId, upstreamKind, name, sourcePage, PAGE_SIZE),
          ])
          return { slot, list }
        },
        enabled: open,
      }
    }),
  })
  const finalStage = (kind === 'function' && stage.stage === 'detailed_cases')
    || (kind === 'api' && stage.stage === 'generate') || (kind === 'ui' && stage.stage === 'ui_yaml')
  const targets = useQuery({
    queryKey: ['candidateWorkflow', requirementId, kind, 'targets'],
    queryFn: async () => kind === 'api'
      ? listItems(await api.getApiCollections(requirementId)).map(item => ({ value: item.collectionId ?? '', label: item.name }))
      : listItems(await api.getUiTestSuites(requirementId)).map(item => ({ value: item.suiteId ?? '', label: item.name })),
    enabled: open && finalStage && kind !== 'function',
  })
  const candidate = detail.data
  const content = selectedId === 'current' ? current.data?.content : candidate?.content
  const contentFormat = selectedId === 'current' ? current.data?.format : candidate?.format
  const normalizedFormat = contentFormat?.toLowerCase()
  const rawModeLabel = normalizedFormat === 'yaml' ? 'YAML' : normalizedFormat === 'json' ? 'JSON' : '原文'
  const materialContent = selectedId === 'current' ? current.data?.materialContent : candidate?.materialContent
  const sourceTrace = selectedId === 'current' ? current.data?.sourceTrace : candidate?.sourceTrace
  const visualEditable = kind === 'requirement_analysis' && stage.stage === 'extracting_text'
    || kind === 'function' && (stage.stage === 'case_names' || stage.stage === 'detailed_cases')
  const editingDirty = edit !== null && edit !== editBaseline
  const revisionDirty = Boolean(
    (revisionInstruction !== revisionInitial && revisionInstructionText(revisionInstruction))
    || revisionAttachments.attachments.length,
  )
  useEffect(() => {
    if (!editingDirty && !revisionDirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    const navigation = (event: Event) => {
      if (!closeConfirmed.current && !window.confirm('有未保存的修改，确定放弃并离开吗？')) event.preventDefault()
    }
    const historyIndex = window.history.state?.idx
    let restoringHistory = false
    const popState = (event: PopStateEvent) => {
      if (restoringHistory) { restoringHistory = false; event.stopImmediatePropagation(); return }
      const nextIndex = event.state?.idx
      if (typeof historyIndex !== 'number' || typeof nextIndex !== 'number' || nextIndex === historyIndex) return
      if (!window.confirm('有未保存的修改，确定放弃并离开吗？')) {
        event.stopImmediatePropagation(); restoringHistory = true; window.history.go(historyIndex - nextIndex)
      }
    }
    window.addEventListener('beforeunload', warn)
    window.addEventListener(UNSAVED_NAVIGATION_EVENT, navigation)
    window.addEventListener('popstate', popState, true)
    return () => {
      window.removeEventListener('beforeunload', warn)
      window.removeEventListener(UNSAVED_NAVIGATION_EVENT, navigation)
      window.removeEventListener('popstate', popState, true)
    }
  }, [editingDirty, revisionDirty])
  const trialAvailable = stage.upstreamStages.length > 0 && !['historical_requirement_relations', 'historical_test_case_verification'].includes(stage.stage)
  function sourceChoiceAt(name: string, index: number): SourceChoice | undefined {
    const chosen = choices[name]
    if (chosen) return chosen
    const info = sources[index]
    if (!info.data?.slot.candidateId || info.data.slot.invalidatedAt) return undefined
    return { chainKind: sourceKind(name, kind), stage: name, sourceKind: 'current', expectedCurrentToken: info.data.slot.currentToken }
  }
  const selectedSourceList = stage.upstreamStages.map((name, index) => sourceChoiceAt(name, index)).filter((choice): choice is SourceChoice => Boolean(choice))
  const runMode = selectedSourceList.some(choice => choice.sourceKind === 'candidate') ? 'trial' : 'current'
  const upstreamLoading = sources.some(source => source.isPending)
  const upstreamFailed = sources.some(source => source.isError)
  const missingCurrentUpstream = sources.some(source => !source.data?.slot.candidateId || source.data.slot.invalidatedAt)
  const llmConnections = useQuery({ queryKey: ['llmConnections', projectId, 'select'], queryFn: () => api.getLlmConnections(projectId), enabled: generateOpen })
  const activeModels = listItems(llmConnections.data).filter(item => item.status === 'active')
  const selectedModelId = activeModels.some(item => item.connectionId === connectionId) ? connectionId
    : activeModels.length === 1 ? activeModels[0].connectionId : ''
  const runBlocked = upstreamLoading || upstreamFailed || !selectedModelId || llmConnections.isPending || llmConnections.isError || (runMode === 'current'
    ? missingCurrentUpstream
    : selectedSourceList.length !== stage.upstreamStages.length)
  const generateActionDisabled = !current.data || current.data.active || (!trialAvailable && (upstreamLoading || upstreamFailed || missingCurrentUpstream))
  function idFor(action: string, body: unknown) {
    const key = JSON.stringify(body)
    if (pendingIds.current[action]?.key !== key) pendingIds.current[action] = { key, id: randomId() }
    return pendingIds.current[action].id
  }
  function refresh() {
    void client.invalidateQueries({ queryKey: ['candidateWorkflow', requirementId] })
    void client.invalidateQueries({ queryKey: ['candidateRelations', requirementId] })
    void client.invalidateQueries({ queryKey: ['generationChain', requirementId] })
  }
  const operation = useMutation({
    mutationFn: async (action: () => Promise<void>) => action(),
    onError: err => notify.error({ title: '操作未完成', description: getErrorMessage(err) }),
    onSuccess: () => refresh(),
  })
  function perform(action: () => Promise<void>) { operation.mutate(action) }
  function changeSelection(id: string) {
    if ((editingDirty || revisionDirty) && !window.confirm('有未保存的修改，确定放弃吗？')) return
    closeImport()
    setEdit(null); setRevisionOpen(false); setRevisionInstruction(''); setRevisionInitial(''); revisionCandidate.current = ''; revisionAttachments.clearAttachments(); setCheck(null); setUiSourceCheck(null); setSelectedId(id)
  }
  useEffect(() => {
    if (selectedId !== 'current' && selectedId === current.data?.candidateId && !editingDirty && !revisionDirty) setSelectedId('current')
  }, [selectedId, current.data?.candidateId, editingDirty, revisionDirty])
  function close() {
    if ((editingDirty || revisionDirty) && !window.confirm('有未保存的修改，确定放弃吗？')) return
    closeConfirmed.current = true
    closeImport()
    setEdit(null); setRevisionOpen(false); setRevisionInstruction(''); setRevisionInitial(''); revisionCandidate.current = ''; revisionAttachments.clearAttachments()
    onClose()
    queueMicrotask(() => { closeConfirmed.current = false })
  }
  async function executeRun(inputs?: UiGenerationRunInputs, modelOverride?: { connectionId: string; instruction: string }) {
      if (runMode === 'trial' && selectedSourceList.length !== stage.upstreamStages.length) throw new Error('请为每个上游阶段选择一份来源')
      const model = modelOverride ?? await chooseConnection()
      if (kind === 'ui' && !chooseGitlab) throw new Error('GitLab 授权选择不可用，请刷新页面')
      const gitlabConnectionId = kind === 'ui' ? await chooseGitlab!(projectId) : undefined
      const input = { connectionId: model.connectionId, instruction: model.instruction, generationMode: runMode,
        ...(inputs ? { functionCaseIds: inputs.functionCaseIds, sourceRepositoryId: inputs.sourceRepositoryId, sourceProfileCandidateId: inputs.sourceProfileCandidateId, sourceCommitMode: inputs.sourceCommitMode } : {}),
        ...(gitlabConnectionId ? { gitlabConnectionId } : {}),
        ...(runMode === 'trial' ? { sourceSelections: selectedSourceList } : {}) } as CandidateRunBody
      const requestId = idFor('run', input)
      await generationCandidatesApi.run(requirementId, kind, stage.stage, { ...input, requestId })
      delete pendingIds.current.run
      notify.success({ title: '已开始生成', description: '当前采用内容和已有候选会保留。' })
  }
  function run() {
    if (!trialAvailable) {
      if (kind === 'ui' && stage.stage === 'ui_surface') { setUiInputsOpen(true); return }
      perform(() => executeRun())
      return
    }
    setChoices({})
    setSourcePages({})
    setConnectionId('')
    setInstruction('')
    setPendingModel(null)
    setGenerateOpen(true)
  }
  function startGeneration() {
    if (!selectedModelId) return
    const model = { connectionId: selectedModelId, instruction }
    setGenerateOpen(false)
    if (kind === 'ui' && stage.stage === 'ui_surface') { setPendingModel(model); setUiInputsOpen(true); return }
    perform(() => executeRun(undefined, model))
  }
  function adoptionBody(): CandidateAdoptBody {
    if (!candidate?.currentAttemptId || !current.data?.currentToken) throw new Error('候选或当前内容已变化，请刷新后重试')
    const identity = { candidateId: candidate.candidateId, expectedCandidateToken: candidate.candidateToken,
      expectedAttemptId: candidate.currentAttemptId, expectedCurrentToken: current.data.currentToken }
    return { action: 'adopt', ...identity, requestId: idFor('adopt', identity) }
  }
  function adopt(continueAfter = false) {
    perform(async () => {
      let body = adoptionBody()
      const checked = await generationCandidatesApi.checkAdoption(requirementId, kind, stage.stage, body)
      setCheck(checked)
      if (!checked.canAdopt) return
      if (continueAfter) {
        const model = await chooseConnection()
        if (kind === 'ui' && !chooseGitlab) throw new Error('GitLab 授权选择不可用，请刷新页面')
        const gitlabConnectionId = kind === 'ui' ? await chooseGitlab!(projectId) : undefined
        const continuation = { continueAfter: true, connectionId: model.connectionId, instruction: model.instruction, ...(gitlabConnectionId ? { gitlabConnectionId } : {}) }
        body = { ...body, ...continuation, requestId: idFor('adopt-continue', { ...body, ...continuation }) }
      }
      const result = await generationCandidatesApi.adopt(requirementId, kind, stage.stage, body)
      delete pendingIds.current[continueAfter ? 'adopt-continue' : 'adopt']
      setCheck(null); setSelectedId('current'); setPreview(null)
      if (result.continuationError) notify.warning({ title: '已采用该候选，下一阶段未启动', description: result.continuationError })
      else notify.success({ title: '已采用该候选', description: continueAfter ? '下一阶段已开始生成。' : '正式用例尚未改变。' })
    })
  }
  function save() {
    perform(async () => {
      if (!candidate?.currentAttemptId || edit === null) throw new Error('候选已变化，请刷新后重试')
      const body = { expectedCandidateToken: candidate.candidateToken, expectedAttemptId: candidate.currentAttemptId, content: edit }
      if (candidate.frozenAt || candidate.isCurrent || candidate.disposition !== 'available') {
        const requestId = idFor('derive', body)
        const result = await generationCandidatesApi.derive(requirementId, kind, stage.stage, candidate.candidateId, { ...body, requestId })
        delete pendingIds.current.derive
        setSelectedId(result.candidateId); notify.success({ title: '已保存为新候选', description: '原内容保持不变。' })
      } else {
        await generationCandidatesApi.edit(requirementId, kind, stage.stage, candidate.candidateId, body)
        notify.success({ title: '候选已保存' })
      }
      setEdit(null)
    })
  }
  function startEdit() {
    if (!candidate) return
    const formatted = formatJsonArtifact(candidate.content)
    setEditBaseline(formatted)
    setEdit(formatted)
  }
  function cancelEdit() {
    if (!editingDirty || window.confirm('放弃未保存的修改？')) setEdit(null)
  }
  function revise(connectionId: string) {
    perform(async () => {
      const instruction = revisionInstructionText(revisionInstruction)
      if (!candidate?.currentAttemptId || !instruction) throw new Error('候选或优化指令已变化，请刷新后重试')
      if (kind === 'ui' && !chooseGitlab) throw new Error('GitLab 授权选择不可用，请刷新页面')
      const gitlabConnectionId = kind === 'ui' ? await chooseGitlab!(projectId) : undefined
      const body = { expectedCandidateToken: candidate.candidateToken, expectedAttemptId: candidate.currentAttemptId,
        connectionId, instruction, attachmentFileIds: revisionAttachments.attachments.map(item => item.fileId),
        ...(gitlabConnectionId ? { gitlabConnectionId } : {}) }
      await generationCandidatesApi.revise(requirementId, kind, stage.stage, candidate.candidateId, { ...body, requestId: idFor('revise', { ...body, candidateId: candidate.candidateId }) })
      delete pendingIds.current.revise; setRevisionOpen(false); setRevisionInstruction(''); setRevisionInitial(''); revisionCandidate.current = ''; revisionAttachments.clearAttachments()
      notify.success({ title: '已开始优化', description: '将生成新候选；原候选和当前内容会保留。' })
    })
  }
  function openRevision() {
    if (!candidate) return
    if (revisionCandidate.current !== candidate.candidateId) {
      const questions = getRevisionQuestions(candidate.content)
      const initial = stage.stage === 'requirement_review' ? ''
        : kind === 'requirement_analysis' && questions.length ? createQuestionRevisionDraft(questions)
          : buildRevisionTemplate(questions, stage.label, '答复')
      revisionCandidate.current = candidate.candidateId
      setRevisionInitial(initial)
      setRevisionInstruction(initial)
    }
    setRevisionOpen(true)
  }
  function dispose(action: 'reject' | 'delete') {
    perform(async () => {
      if (!candidate) throw new Error('候选已变化，请刷新后重试')
      const body = { action, expectedCandidateToken: candidate.candidateToken } as const
      const requestId = idFor('dispose', { ...body, candidateId: candidate.candidateId })
      await generationCandidatesApi.dispose(requirementId, kind, stage.stage, candidate.candidateId, { ...body, requestId })
      delete pendingIds.current.dispose; setSelectedId('current'); notify.success({ title: action === 'reject' ? '已拒绝此候选' : '已删除此候选' })
    })
  }
  function checkUiSource() {
    perform(async () => {
      const id = selectedId === 'current' ? current.data?.candidateId : candidate?.candidateId
      if (!id || !chooseGitlab) throw new Error('候选或 GitLab 授权不可用，请刷新后重试')
      const selected = selectedId === 'current'
        ? await generationCandidatesApi.detail(requirementId, kind, stage.stage, id)
        : candidate
      if (!selected || (selectedId === 'current' && !selected.isCurrent)) throw new Error('当前内容已变化，请刷新后重试')
      const gitlabConnectionId = await chooseGitlab(projectId)
      const result = await generationCandidatesApi.checkUiSource(requirementId, stage.stage, id, {
        expectedCandidateToken: selected.candidateToken, gitlabConnectionId,
      })
      setUiSourceCheck({ ...result, candidateId: id })
    })
  }
  function openImport() {
    setPreview(null)
    setImportOpen(true)
    if (kind === 'function') previewImport()
  }
  function closeImport() {
    importPreviewRequest.current += 1
    setImportOpen(false)
    setPreview(null)
  }
  function changeImportTarget(value: string) {
    importPreviewRequest.current += 1
    setTargetId(value)
    setPreview(null)
  }
  function previewImport() {
    if (kind !== 'function' && !targetId) return
    const request = ++importPreviewRequest.current
    setPreview(null)
    perform(async () => {
      if (!current.data?.candidateId) throw new Error('请先采用要导入的内容')
      if (kind !== 'function' && !targetId) throw new Error('请先选择正式导入目标')
      const result = await generationCandidatesApi.previewImport(requirementId, kind, stage.stage,
        { expectedCurrentToken: current.data.currentToken, targetId })
      if (request === importPreviewRequest.current) setPreview(result)
    })
  }
  function importCurrent() {
    perform(async () => {
      if (!preview || preview.previewExpiresAt <= Math.floor(Date.now() / 1000) || preview.currentToken !== current.data?.currentToken) throw new Error('当前内容或预览已变化，请重新预览')
      const body = { expectedCurrentToken: preview.currentToken, expectedLineageHash: preview.fullLineageHash,
        previewToken: preview.previewToken, targetId, confirmOverwrite: preview.requiresConfirmation }
      try {
        const result = await generationCandidatesApi.importCurrent(requirementId, kind, stage.stage, { ...body, requestId: idFor('import', body) })
        if (result.requiresConfirmation) throw new Error('导入目标已发生冲突，请重新预览')
        delete pendingIds.current.import
        importPreviewRequest.current += 1
        setPreview(null)
        setImportOpen(false)
        notify.success({ title: '已导入正式用例', description: `共 ${result.changedCaseIds.length} 条。` })
      } catch (error) {
        setPreview(null)
        throw error
      }
    })
  }
  const loading = operation.isPending
  // 画布内阅读时，候选内容与阶段操作分别挂到详情侧栏的内容区和底部操作区。
  const sidebarMode = Boolean(inspectorContainer && inspectorActionContainer)
  const selectedIsCurrent = selectedId === 'current'
  const selectedCandidateId = selectedIsCurrent ? current.data?.candidateId ?? '' : candidate?.candidateId ?? selectedId
  const selectedMode = selectedIsCurrent ? undefined : candidate ? candidateModeLabel(candidate) : undefined
  const visibleCandidates = (candidates.data?.items ?? []).filter(item => !item.isCurrent && item.candidateId !== current.data?.candidateId)
  const otherCandidates = visibleCandidates.filter(item => item.candidateId !== selectedId)
  const currentSummary = (candidates.data?.items ?? []).find(item => item.isCurrent || item.candidateId === current.data?.candidateId)
  const otherCount = Math.max(0, (candidates.data?.total ?? 0) - (current.data?.candidateId ? 1 : 0) - (!selectedIsCurrent && candidate ? 1 : 0))
  const selectedMeta = selectedIsCurrent
    ? current.data?.candidateId
      ? `当前采用内容${currentSummary ? ` · ${formatCompactTime(currentSummary.createdAt)}` : ''}`
      : '尚未采用'
    : candidate ? `${formatCompactTime(candidate.createdAt)} · 未采用` : '读取候选…'
  const contentStats = useMemo(() => stageContentStats(stage.stage, content, materialContent), [content, materialContent, stage.stage])
  const hasVisualView = kind !== 'requirement_analysis' || stage.stage === 'requirement_review' || stage.stage === 'extracting_text' || stage.stage === 'historical_requirement_relations' || stage.stage === 'historical_test_case_verification'
  const rawView = Boolean(content) && (!hasVisualView || (edit !== null && !visualEditable) || viewMode === 'raw' || !canRenderVisual(kind, edit ?? content ?? ''))
  const readingRaw = rawView && edit === null
  const edgeToEdgeRaw = readingRaw && sidebarMode
  // 范围分析、历史需求关联、历史用例核验、测试点与完整用例图谱在画布阅读态自带左右分栏和滚动，不再叠加外层 16px 内距。
  const edgeToEdgeRail = sidebarMode && !rawView && ((kind === 'function' && stage.stage === 'requirement_analysis') || stage.stage === 'historical_requirement_relations' || stage.stage === 'historical_test_case_verification')
  const edgeToEdgeGraph = sidebarMode && !rawView && kind === 'function' && (stage.stage === 'case_names' || stage.stage === 'detailed_cases')
  const selectedUiSourceInputs = selectedIsCurrent ? current.data?.sourceInputs : candidate?.sourceInputs
  const sourceTraceView = <div className="gc-candidate-source">
    <span className="gc-candidate-source-prefix">基于</span>
    {sourceTrace?.length ? sourceTrace.map(item => <span key={`${item.chainKind}:${item.stage}`} className="gc-trace-chip" title={`${stageLabel(item.stage)} · ${item.sourceKind === 'current' ? '当前采用内容' : '候选'} ${item.candidateId}`}>
      {stageLabel(item.stage)}<b>{item.sourceKind === 'current' ? '当前' : '候选'} {item.candidateId.slice(0, 8)}</b>
    </span>) : stage.upstreamStages.length ? (selectedId !== 'current' && detail.isPending ? <span className="gc-trace-chip">读取来源…</span> : <span className="gc-trace-chip is-danger">来源信息不完整</span>) : <span className="gc-trace-chip">{kind === 'api' ? '接口库接口' : kind === 'ui' ? '源码输入' : '需求材料'}</span>}
    <span className="gc-candidate-source-prefix">产出</span>
  </div>
  const focusCard = <section className="gc-candidate-focus" aria-label="当前查看">
    <div className="gc-candidate-focus-head">
      <span className={`gc-candidate-focus-kind${selectedIsCurrent ? ' is-current' : ''}`}><span aria-hidden="true" />{selectedIsCurrent ? '当前采用' : '候选'}</span>
      <span className="gc-candidate-focus-id">{selectedCandidateId ? <span className="gc-candidate-mono">{selectedCandidateId.slice(0, 8)}</span> : '—'}</span>
      {selectedMode && selectedMode !== '生成' ? <span className={`gc-candidate-pill${selectedMode === '试生成' ? ' is-trial' : ''}`}>{selectedMode}</span> : null}
      {selectedIsCurrent && current.data?.invalidatedAt ? <span className="gc-candidate-pill is-warn">已采用 · 待更新</span> : null}
      {selectedIsCurrent && current.data?.active ? <span className="gc-candidate-pill is-trial">生成中</span> : null}
      {!selectedIsCurrent && candidate?.disposition === 'rejected' ? <span className="gc-candidate-pill is-danger">已拒绝</span> : null}
    </div>
    <div className="gc-candidate-focus-meta">{selectedMeta}</div>
    <div className="gc-candidate-focus-tools">
      {content && hasVisualView && (edit === null || visualEditable) ? <Radio.Group className="gc-candidate-view-switch" size="small" value={viewMode} onChange={event => setViewMode(event.target.value)} options={[{ label: '可视化', value: 'visual' }, { label: rawModeLabel, value: 'raw' }]} optionType="button" /> : <span />}
    </div>
    {sourceTraceView}
    {contentStats ? <div className="gc-candidate-stats" aria-label="内容概况">{contentStats.map(([value, unit]) => <span key={unit}><b>{value}</b> {unit}</span>)}</div> : null}
    {selectedIsCurrent && current.data?.invalidatedAt && current.data.invalidatedReason ? <p className="gc-candidate-reason">{current.data.invalidatedReason}</p> : null}
    {kind === 'ui' && selectedUiSourceInputs ? <div className="gc-candidate-ui-source"><UiGenerationSourceTrace source={selectedUiSourceInputs} /><Button size="small" disabled={loading} onClick={checkUiSource}>检查分支更新</Button></div> : null}
    {uiSourceCheck && uiSourceCheck.candidateId === (selectedIsCurrent ? current.data?.candidateId : candidate?.candidateId) ? <Alert showIcon type={uiSourceCheck.changed ? 'warning' : 'info'} title={uiSourceCheck.changed ? '分支已有新提交，候选仍使用冻结的 commit。' : '分支 HEAD 与冻结 commit 一致。'} description={`冻结：${uiSourceCheck.pinnedCommit}；当前：${uiSourceCheck.currentCommit}`} /> : null}
  </section>
  const adoptedCard = <button type="button" className={`gc-candidate-adopted${selectedIsCurrent ? ' is-selected' : ''}`} aria-label="查看当前内容" aria-pressed={selectedIsCurrent} onClick={() => changeSelection('current')}>
    <span className="gc-candidate-adopted-main">
      <span className="gc-candidate-adopted-label"><CheckOutlined aria-hidden />当前采用</span>
      <span className="gc-candidate-adopted-id">{current.data?.candidateId ? <span className="gc-candidate-mono">{current.data.candidateId.slice(0, 8)}</span> : '尚未采用'}</span>
      {currentSummary ? <span className="gc-candidate-adopted-time">{formatCompactTime(currentSummary.createdAt)}</span> : null}
      {current.data?.invalidatedAt ? <Tag color="warning">已采用 · 待更新</Tag> : null}
      {current.data?.active ? <Tag color="processing">生成中</Tag> : null}
    </span>
    <span className="gc-candidate-adopted-action">{selectedIsCurrent ? '查看中' : '查看'}</span>
  </button>
  const candidateGrid = <section className="gc-candidate-candidates" aria-label="候选版本">
    <div className="gc-candidate-section-head"><h3>其他候选</h3><span>{candidates.isPending ? '' : `${otherCount} 个`}</span></div>
    {candidates.isPending ? <Spin size="small" /> : null}
    {candidates.error ? <Alert type="error" showIcon title={getErrorMessage(candidates.error)} action={<Button size="small" onClick={() => void candidates.refetch()}>重试</Button>} /> : null}
    {otherCandidates.length ? <div className="gc-candidate-grid" role="group" aria-label="选择候选版本">
      {otherCandidates.map(item => <button key={item.candidateId} type="button" className="gc-candidate-tile" onClick={() => changeSelection(item.candidateId)}
        title={`${label(item)}${item.disposition === 'rejected' ? ' · 已拒绝' : ''}`}>
        <span className="gc-candidate-tile-name">候选 {item.candidateId.slice(0, 8)}</span>
        <span className="gc-candidate-tile-meta">{candidateModeLabel(item)} · {formatCompactTime(item.createdAt)}</span>
        {item.disposition === 'rejected' ? <span className="gc-candidate-tile-state">已拒绝</span> : null}
      </button>)}
    </div> : !candidates.isPending ? <p className="gc-candidate-empty">暂无其他候选，生成后会显示在这里。</p> : null}
    {(candidates.data?.total ?? 0) > PAGE_SIZE ? <Pagination size="small" current={page} pageSize={PAGE_SIZE} total={candidates.data?.total} onChange={setPage} showSizeChanger={false} /> : null}
  </section>
  const currentTools = <>
    {focusCard}
    {!selectedIsCurrent ? adoptedCard : null}
    {current.error ? <Alert showIcon type="error" title="当前内容读取失败" description={getErrorMessage(current.error)} action={<Button size="small" onClick={() => void current.refetch()}>重试</Button>} /> : null}
    {candidateGrid}
  </>
  const sourceLabel = sourceTrace?.length
    ? sourceTrace.map(item => stageLabel(item.stage)).join(' · ')
    : stage.upstreamStages.length ? '上游候选' : kind === 'api' ? '接口库' : kind === 'ui' ? '源码仓库' : '需求材料'
  const generationLabel = selectedIsCurrent
    ? current.data?.candidateId ? '当前采用内容' : '—'
    : candidate?.generationMode === 'trial' ? '候选试生成'
      : candidate?.derivedFromCandidateId ? '编辑派生'
        : stage.upstreamStages.length ? '当前上游' : '直接生成'
  const basisSources = selectedIsCurrent ? current.data?.basisSources : candidate?.basisSources
  const basisLabel = basisSources?.length
    ? `${basisSources.slice(0, 3).map(item => `${stageLabel(item.stage)} ${item.candidateId.slice(0, 8)}`).join(' · ')}${basisSources.length > 3 ? ` 等 ${basisSources.length} 项` : ''}`
    : '依据未记录'
  const basisTitle = basisSources?.length
    ? basisSources.map(item => `${stageLabel(item.stage)} · 候选 ${item.candidateId} · 快照 ${item.snapshotId}`).join('\n')
    : undefined
  const sourceCard = <section className="gc-candidate-info-card" aria-label="来源与依据">
    <div className="gc-candidate-info-head"><InfoCircleOutlined aria-hidden />来源与依据</div>
    <div className="gc-candidate-info-row"><span>来源</span><strong>{sourceLabel}</strong></div>
    {!selectedIsCurrent ? <div className="gc-candidate-info-row"><span>生成方式</span><strong>{generationLabel}</strong></div> : null}
    <div className="gc-candidate-info-row"><span>依据</span><strong title={basisTitle}>{basisLabel}</strong></div>
  </section>
  const recentCandidates = [...(candidates.data?.items ?? [])].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 3)
  const activityCard = recentCandidates.length ? <section className="gc-candidate-info-card" aria-label="最近生成">
    <div className="gc-candidate-info-head"><ClockCircleOutlined aria-hidden />最近生成</div>
    {recentCandidates.map(item => <div className="gc-candidate-activity-row" key={item.candidateId}>
      <span className="gc-candidate-activity-time">{formatCompactTime(item.createdAt)}</span>
      <span className="gc-candidate-activity-mode">{candidateModeLabel(item)}</span>
      <span className="gc-candidate-activity-id">{item.candidateId.slice(0, 8)}</span>
      {item.isCurrent ? <span className="gc-candidate-activity-current">当前</span> : null}
    </div>)}
  </section> : null
  const generationCard = access.can('execute') ? <section className="gc-candidate-gen-card" aria-label="生成新版本">
    <div className="gc-candidate-gen-head">
      <span className="gc-candidate-gen-icon"><ThunderboltOutlined aria-hidden /></span>
      <div className="gc-candidate-gen-copy"><strong>生成新版本</strong><span>{trialAvailable ? '默认当前上游，也可直接改选候选' : '基于当前输入生成，已有内容会保留'}</span></div>
      <Button loading={loading} disabled={generateActionDisabled} onClick={run}>开始生成</Button>
    </div>
  </section> : null
  const generationTools = <>
    <div className="gc-candidate-info-group">
      {sourceCard}
      {activityCard}
    </div>
    <div className={`gc-candidate-generate${sidebarMode ? ' is-sidebar' : ''}`}>
      <p className="gc-candidate-note">生成结果先进入候选，确认采用后用于下游。</p>
      {generationCard}
    </div>
  </>
  const canAdopt = Boolean(candidate && access.can('review') && candidate.disposition === 'available' && !candidate.isCurrent)
  const canContinue = Boolean(candidate && access.can('review') && access.can('execute') && CONTINUATION_STAGES.has(stage.stage) && candidate.disposition === 'available' && !candidate.isCurrent)
  const canEdit = Boolean(candidate && access.can('write') && candidate.currentAttemptId)
  const canRevise = Boolean(candidate && access.can('execute') && candidate.disposition === 'available' && candidate.currentAttemptId)
  const canDispose = Boolean(candidate && access.can('write') && !candidate.isCurrent)
  const candidateActions = candidate ? <section className="gc-candidate-dock" aria-label="阶段操作">
    <CandidateStageActions
      candidate={candidate}
      continueLabel={stage.stage === 'historical_requirement_relations' ? '采用并核验历史用例' : '采用并生成下一阶段'}
      canAdopt={canAdopt} canContinue={canContinue} canEdit={canEdit} canRevise={canRevise} canDispose={canDispose}
      loading={loading} editing={edit !== null} revisionOpen={revisionOpen} revisionDirty={revisionDirty} currentActive={Boolean(current.data?.active)}
      onAdopt={adopt} onEdit={startEdit} onSave={save} onCancelEdit={cancelEdit} onRevise={openRevision} onDispose={dispose}
    />
    {check && !check.canAdopt ? <Alert showIcon type="warning" title="还不能采用" description={<ul>{check.blockingSources.map(item => <li key={`${item.chainKind}:${item.stage}`}>{stageLabel(item.stage)}：内容或来源已变化，请刷新后重试</li>)}</ul>} /> : null}
  </section> : null
  const canImportCurrent = Boolean(access.can('execute') && finalStage && selectedIsCurrent && current.data?.candidateId && !current.data.invalidatedAt)
  const importTargetText = kind === 'function' ? '按模块归入功能测试集' : '导入到所选正式目标'
  const importDock = canImportCurrent ? <section className="gc-candidate-dock" aria-label="导入正式用例">
    <div className="gc-candidate-dock-head">
      <span className="gc-candidate-dock-label">导入正式用例</span>
      <span className="gc-candidate-dock-hint">最终阶段</span>
    </div>
    <p className="m-0 text-[11px] leading-[1.55] text-app-surface-text-muted">{importTargetText}；先预览同名冲突，确认后写入正式用例库。</p>
    <Button className="gc-candidate-primary" type="primary" block loading={loading} onClick={openImport}>预览并导入</Button>
  </section> : null
  const inspectorDock = candidateActions ?? (selectedIsCurrent ? importDock : null)
  return <><GenerationArtifactFrame hideHeader={sidebarMode} open={open} onCancel={close} title={`${stage.label} · 候选与当前内容`} className={`${chainStyles.scope} ${canvasStyles.scope} ${candidateStyles.scope} ${caseArtifactStyles.scope} ${uiStageStyles.scope} generation-chain-modal`} footer={null}>
    <div className={`flex min-h-0 flex-1 flex-col gap-3 overflow-auto ${edgeToEdgeRaw || edgeToEdgeRail || edgeToEdgeGraph ? 'p-0' : 'p-4'}`}>
      {stage.state === 'failed' ? <Alert showIcon type="error" title={stage.errorMessage || '阶段执行失败，Worker 未返回具体原因'} /> : null}
      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          {stage.moduleGeneration && (stage.state === 'running' || stage.state === 'failed') ? <ModuleGenerationProgressPanel key={stage.moduleGeneration.attemptId} progress={stage.moduleGeneration} /> : null}
          {detail.isPending && selectedId !== 'current' ? <Spin /> : null}
          {detail.error && selectedId !== 'current' ? <Alert showIcon type="error" title="候选读取失败" description={getErrorMessage(detail.error)} action={<Button onClick={() => void detail.refetch()}>重试</Button>} /> : null}
          {content ? <div className="min-h-0 flex-1 flex flex-col">
            <div className={readingRaw ? 'gc-reading-body min-h-0 flex-1 flex flex-col' : 'flex min-h-0 min-w-0 w-full flex-1 flex-col'}>
              {rawView ? (edit === null
                ? <div className="gc-artifact-scroll is-raw"><TextCodeEditor value={formatJsonArtifact(content)} readOnly ariaLabel={selectedId === 'current' ? '当前内容' : '候选内容'} language="auto" /></div>
                : <TextCodeEditor value={edit} onChange={setEdit} readOnly={false} ariaLabel={selectedId === 'current' ? '当前内容' : '候选内容'} language="auto" />)
                : kind === 'requirement_analysis'
                  ? stage.stage === 'requirement_review' ? <RequirementReviewView content={content} /> : stage.stage === 'historical_requirement_relations' ? <HistoricalRelationView content={content} materialContent={materialContent} projectId={projectId} /> : stage.stage === 'historical_test_case_verification' ? <HistoricalCaseVerificationView content={content} materialContent={materialContent} projectId={projectId} /> : <RequirementMaterialComparison content={edit ?? content} editable={edit !== null} onChange={edit !== null ? setEdit : undefined} />
                  : kind === 'function'
                    ? stage.stage === 'requirement_analysis' ? <RequirementAnalysisDiagramView content={content} materialContent={materialContent ?? undefined} />
                      : stage.stage === 'case_names' ? <TraceablePointsView content={edit ?? content} materialContent={materialContent ?? undefined} rootTitle={stage.label} onChange={edit !== null ? setEdit : undefined} />
                        : <GeneratedCasesReviewView content={edit ?? content} rootTitle={stage.label} onChange={edit !== null ? setEdit : undefined} />
                    : kind === 'api'
                      ? stage.stage === 'interface_extract' ? <ApiConfigDiagramView content={content} />
                        : stage.stage === 'api_design' ? <ApiDesignDiagramView content={content} onShowRaw={() => setViewMode('raw')} />
                          : <ApiCandidateResultView content={content} />
                      : <UiStageVisual stage={stage.stage as UiGenerationStage} content={content} onShowRaw={() => setViewMode('raw')} />}</div>
          </div> : !detail.isPending && !current.isPending ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="此阶段还没有可查看的内容" /> : null}
          {revisionOpen && candidate ? <RevisionSidePanel projectId={projectId} value={revisionInstruction} onChange={setRevisionInstruction} loading={loading}
            {...(kind === 'ui' ? {} : { attachments: revisionAttachments.attachments, onAddAttachment: revisionAttachments.addAttachment, onRemoveAttachment: revisionAttachments.removeAttachment })}
            onSubmit={revise} onCancel={() => setRevisionOpen(false)} /> : null}
        </section>
    </div>
  </GenerationArtifactFrame>
    {sidebarMode && open && inspectorContainer ? createPortal(currentTools, inspectorContainer) : null}
    {sidebarMode && open && inspectorContainer && generationTools ? createPortal(generationTools, inspectorContainer) : null}
    {sidebarMode && open && inspectorActionContainer && inspectorDock ? createPortal(inspectorDock, inspectorActionContainer) : null}
    <CandidateImportModal
      open={importOpen}
      kind={kind}
      candidateId={current.data?.candidateId ?? undefined}
      targetId={targetId}
      targetOptions={targets.data ?? []}
      targetsLoading={targets.isPending}
      targetsError={targets.error ? getErrorMessage(targets.error) : null}
      preview={preview}
      loading={loading}
      onTargetChange={changeImportTarget}
      onPreview={previewImport}
      onImport={importCurrent}
      onClose={closeImport}
    />
    {gitlabDialog}
    {generateOpen && trialAvailable ? <Modal open centered destroyOnHidden width={520} title="生成新版本" okText="开始生成" cancelText="取消"
      onCancel={() => setGenerateOpen(false)} onOk={startGeneration} confirmLoading={loading}
      okButtonProps={{ disabled: runBlocked }} mask={{ closable: false }}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          {upstreamLoading ? <span className={candidateStyles.dialogHint}>正在读取上游来源…</span> : null}
          {stage.upstreamStages.map((name, index) => {
            const info = sources[index]
            const upstreamKind = sourceKind(name, kind)
            const chosen = sourceChoiceAt(name, index)
            const options = [
              ...(info.data?.slot.candidateId && !info.data.slot.invalidatedAt ? [{ value: 'current', label: '当前采用内容' }] : []),
              ...(info.data?.list.items ?? []).filter(item => item.disposition === 'available').map(item => ({ value: item.candidateId, label: label(item) })),
            ]
            return <div className="flex flex-col gap-1" key={name}><span className={candidateStyles.dialogHint}>{stageLabel(name)}</span><Select className="w-full" aria-label={`选择 ${stageLabel(name)} 来源`} placeholder="请选择一份来源" loading={info.isPending} value={chosen?.sourceKind === 'current' ? 'current' : chosen?.candidateId} options={options} onChange={value => {
              if (value === 'current' && info.data?.slot.currentToken) setChoices(old => ({ ...old, [name]: { chainKind: upstreamKind, stage: name, sourceKind: 'current', expectedCurrentToken: info.data!.slot.currentToken } }))
              else { const item = info.data?.list.items.find(candidateItem => candidateItem.candidateId === value); if (item) setChoices(old => ({ ...old, [name]: { chainKind: upstreamKind, stage: name, sourceKind: 'candidate', candidateId: item.candidateId, snapshotId: item.snapshotId, expectedCandidateToken: item.candidateToken } })) }
            }} />{(info.data?.list.total ?? 0) > PAGE_SIZE ? <Pagination size="small" current={sourcePages[name] ?? 1} pageSize={PAGE_SIZE} total={info.data?.list.total} onChange={next => setSourcePages(old => ({ ...old, [name]: next }))} showSizeChanger={false} /> : null}{info.error ? <span className={candidateStyles.dialogHint}>来源读取失败：{getErrorMessage(info.error)}</span> : null}</div>
          })}
          {upstreamFailed ? <Alert showIcon type="error" title="上游来源读取失败，请刷新后重试。" />
            : !upstreamLoading && runMode === 'current' && missingCurrentUpstream ? <Alert showIcon type="info" title="请先采用有效的上游内容，或选择候选进行试生成。" /> : null}
        </div>
        <section className="flex flex-col gap-2 border-t border-[var(--app-surface-divider)] pt-4">
          <strong className="text-[12.5px] font-semibold text-[var(--app-surface-text)]">使用的模型</strong>
          {llmConnections.isPending ? <span className={candidateStyles.dialogHint}>正在读取本人 LLM 授权…</span>
            : llmConnections.error ? <Alert showIcon type="error" title={getErrorMessage(llmConnections.error)} />
              : activeModels.length === 0 ? <Alert showIcon type="warning" title="暂无可用的本人 LLM 授权，请先在基础服务中配置。" />
                : <Select className="w-full" aria-label="本次使用的模型" placeholder="请选择本人 LLM 授权" value={selectedModelId || undefined} options={activeModels.map(item => ({ value: item.connectionId, label: item.modelId ? `${item.name} · ${item.modelId}` : item.name }))} onChange={setConnectionId} />}
          <label className="flex flex-col gap-1">
            <span className={candidateStyles.dialogHint}>生成要求（选填）</span>
            <Input.TextArea aria-label="生成要求（选填）" value={instruction} onChange={event => setInstruction(event.target.value)} autoSize={{ minRows: 3, maxRows: 8 }} placeholder="补充本次生成需要关注的内容" />
          </label>
        </section>
      </div>
    </Modal> : null}
    {uiInputsOpen && kind === 'ui' && stage.stage === 'ui_surface' ? <UiGenerationInputsModal
      requirementId={requirementId} refreshInputs={false} candidateMode sourceOptions={uiSourceOptions ?? { loading: false }}
      busy={loading} onOpenProfile={onOpenProfile} onClose={() => setUiInputsOpen(false)}
      onSubmit={inputs => operation.mutateAsync(() => executeRun(inputs, pendingModel ?? undefined))} /> : null}
  </>
}
