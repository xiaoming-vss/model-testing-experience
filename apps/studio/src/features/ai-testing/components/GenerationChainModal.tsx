import { TraceablePointsView } from './TraceablePointsView'
import {
  CheckCircleFilled,
  ClockCircleOutlined,
  DeleteOutlined,
  DiffOutlined,
  DownOutlined,
  ExclamationCircleOutlined,
  HistoryOutlined,
  RightOutlined,
} from '@ant-design/icons'
import { Alert, Button, Popconfirm, Popover, Select, Spin, Tag, Tooltip } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { ApiCandidateResultView, ApiConfigDiagramView } from './ApiConfigDiagramView'
import { ApiDesignDiagramView } from './ApiDesignDiagramView'
import { GeneratedCasesReviewView } from './GeneratedCasesReviewView'
import { GC_STATE_CLASS } from './generationClasses'
import { GenerationChainImportModal } from './GenerationChainImportModal'
import { RequirementAnalysisDiagramView } from './RequirementAnalysisView'
import { RequirementMaterialComparison } from './RequirementMaterialComparison'
import { RequirementReviewView } from './RequirementReviewView'
import { RevisionDivider, RevisionSidePanel } from './RevisionSidePanel'
import { ArtifactModeControls, ArtifactModeSwitch } from './ArtifactViewTabs'
import { useViewMotion } from '@/shared/ui/useViewMotion'
import { UiStageVisual } from './uiStageVisual/UiStageVisual'
import { ChainVisualArtifact } from './ChainVisualArtifact'
import { UiGenerationInputsModal } from './UiGenerationInputsModal'
import { UiGenerationSourceTrace } from './UiGenerationSourceTrace'
import type { UiGenerationSourceOptionsState } from './UiGenerationSourceConfig'
import type { GenerationChainWorkspace } from '../hooks/useRequirementGenerationChain'
import type { GenerationChainKind, GenerationChainStage, GenerationChainVersion } from '../api/generationChain.api'
import type { UiGenerationStage } from '../utils/uiGenerationStage'
import { generationChainApi } from '../api/generationChain.api'
import { diffArtifact, diffStats } from '../utils/chainArtifact'
import { formatRawArtifact } from '../utils/artifactFormat'
import { GenerationArtifactFrame } from './GenerationArtifactFrame'
import { GenerationArtifactDiff } from './GenerationArtifactDiff'
import { ModuleGenerationProgressPanel } from './ModuleGenerationProgressPanel'
import chainStyles from '../styles/generation-chain.module.css'
import canvasStyles from '../styles/generation-canvas.module.css'
import caseArtifactStyles from '../styles/artifact-cases.module.css'
import uiStageStyles from '../styles/ui-stage-visual.module.css'

const artifactScopes = [
  chainStyles.scope,
  canvasStyles.scope,
  caseArtifactStyles.scope,
  uiStageStyles.scope,
].join(' ')

function formatTime(value?: string | null) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  return parsed.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const stateCopy: Record<string, string> = {
  approved: '已通过',
  draft: '待审核',
  invalid: '已作废',
  running: '运行中',
  failed: '执行失败',
  not_started: '未开始',
  imported: '已导入',
}

function stateClass(state?: string) {
  if (state === 'approved' || state === 'imported') return 'is-ok'
  if (state === 'draft' || state === 'running' || state === 'invalid') return 'is-warn'
  if (state === 'failed') return 'is-danger'
  return 'is-muted'
}

function VersionHistory({ stage, versions, onPick, onDelete, activeVersion, latestId, canWrite }: {
  stage: GenerationChainStage
  versions: GenerationChainVersion[]
  onPick: (versionId: string) => void
  onDelete: (versionId: string) => void
  activeVersion: string
  latestId?: string
  canWrite: boolean
}) {
  return <div className="gc-history w-[min(380px,82vw)] max-h-[360px] overflow-auto" role="dialog" aria-label={`${stage.label} 版本历史`}>
    <div className="gc-history-head flex items-baseline justify-between gap-2 px-1 pb-2 pt-0.5"><strong className="text-[12px]">版本历史</strong><span className="text-[11px] text-[var(--app-surface-text-muted)]">{versions.length ? `共 ${versions.length} 个已通过版本` : '还没有已通过版本'}</span></div>
    {versions.length ? versions.map(version => <div className={`gc-history-row flex items-center gap-1.5 border-t border-[var(--app-surface-divider)] p-1${activeVersion === version.versionId ? ' is-active bg-[var(--app-accent-surface)]' : ''}`} key={version.versionId}>
      <button type="button" className="gc-history-main flex min-w-0 flex-1 cursor-pointer items-center gap-[7px] rounded-[6px] border-0 bg-transparent p-1 text-left font-[inherit] text-inherit hover:bg-[var(--app-surface-hover)]" onClick={() => onPick(version.versionId)}>
        <span className="gc-version-chip flex-none rounded-[5px] bg-[var(--app-surface-chip)] px-[5px] font-mono text-[10px] text-[var(--app-accent)]">{version.label}</span>
        <span className="gc-history-copy flex min-w-0 flex-1 flex-col gap-px">
          <strong className="overflow-hidden text-ellipsis whitespace-nowrap text-[11px]">{version.summary}</strong>
          <small className="text-[10px] text-[var(--app-surface-text-muted)]">{formatTime(version.createdAt)}{version.reviewerUserId ? ` · ${version.reviewerUserId}` : ''}</small>
        </span>
        {version.versionId === latestId ? <Tag color="success">最新</Tag> : null}
      </button>
      {canWrite ? <Popconfirm title={`删除 ${version.label}？`} description="依赖它的待审核产物会作废，已通过的下游版本保留。" okText="删除" cancelText="取消"
        onConfirm={() => onDelete(version.versionId)}>
        <Button size="small" type="text" danger aria-label={`删除版本 ${version.label}`} icon={<DeleteOutlined />} />
      </Popconfirm> : null}
    </div>) : <div className="gc-history-empty px-2 py-[18px] text-center text-[12px] text-[var(--app-surface-text-muted)]">审核通过后才会产生版本。</div>}
  </div>
}

/** 把版本、上游与对比操作挂到弹窗标题栏，阅读区只剩产物本身。 */
function useModalHeaderSlot() {
  const anchor = useRef<HTMLSpanElement>(null)
  const [target, setTarget] = useState<HTMLElement | null>(null)
  useLayoutEffect(() => {
    const header = anchor.current?.closest('.ant-modal')?.querySelector('.ant-modal-header')
    if (!header) return
    const slot = document.createElement('div')
    slot.className = 'gc-header-tools-slot flex min-w-0 items-center'
    header.append(slot)
    setTarget(slot)
    return () => { slot.remove() }
  }, [])
  return { anchor, target }
}

function ChainHeaderControls({ workspace, canWrite, inline = false }: {
  inline?: boolean
  workspace: GenerationChainWorkspace
  canWrite: boolean
}) {
  const { anchor, target } = useModalHeaderSlot()
  const {
    chain, stage, versionOptions, versionKey, setVersionKey, setDiffOpen, diffOpen, setMode,
    comparisonId, comparisonContent, displayedContent, historyOpen, setHistoryOpen,
    upstream, setUpstream, deleteVersion, busy,
  } = workspace
  const diffLines = useMemo(() => diffArtifact(comparisonContent, displayedContent), [comparisonContent, displayedContent])
  const diffCounts = useMemo(() => diffStats(diffLines), [diffLines])
  if (!stage || !chain) return <span ref={anchor} hidden />

  const latestId = stage.latestVersion?.versionId
  const stageRunning = stage.state === 'running'
  const hasDraft = Boolean(stage.draft && !stage.draft.invalidated)
  const isDiff = diffOpen && Boolean(comparisonId)
  const upstreamFields = stage.upstreamStages.map(name => {
    const upstreamStage = workspace.upstreamStages.find(item => item.stage === name)
    const selectedId = upstream[name]
    const selectedUpstream = upstreamStage?.versions.find(item => item.versionId === selectedId)
    return {
      name,
      label: upstreamStage?.label ?? name,
      latestUpstreamId: upstreamStage?.latestVersion?.versionId,
      options: (upstreamStage?.versions ?? [])
        .filter(version => chain.kind !== 'ui' || !(version.sourceBatchId || version.sourceRunId) || (version.sourceBatchId || version.sourceRunId) === (chain.sourceBatchId || chain.runId))
        .map(version => ({
        value: version.versionId,
        label: `${version.label} · ${version.summary}`,
      })),
      selectedLabel: selectedUpstream?.label ?? (selectedId ? '上游已删除' : '未选择'),
      missing: Boolean(selectedId) && !selectedUpstream,
    }
  })
  const upstreamSummary = upstreamFields.map(field => `${field.label} ${field.selectedLabel}`).join(' · ')
  const upstreamMissing = upstreamFields.some(field => field.missing)

  const controls = <div className="gc-title-tools flex min-w-0 flex-wrap items-center gap-1.5">
    {!inline && versionOptions.length ? <div className="gc-version-buttons flex min-w-0 flex-wrap items-center gap-1" role="group" aria-label="选择版本">
      {versionOptions.map(option => <button key={option.key} type="button"
        className={`gc-version-button inline-flex h-[27px] cursor-pointer items-center gap-1 rounded-[7px] border px-[9px] font-mono text-[11px] ${versionKey === option.key ? 'is-active border-[var(--app-accent-border)] bg-[var(--app-accent-surface)] font-semibold text-[var(--app-accent)]' : 'border-[var(--app-surface-border)] bg-[var(--app-surface)] text-[var(--app-surface-text-muted)] hover:border-[var(--app-accent-border)] hover:text-[var(--app-accent)]'}`}
        aria-pressed={versionKey === option.key}
        onClick={() => { setVersionKey(option.key); setDiffOpen(false) }}>
        {option.label}
        {option.key === latestId ? <span className="gc-latest-dot h-[5px] w-[5px] rounded-full bg-[var(--app-result-success)]" aria-label="最新版本" /> : null}
      </button>)}
    </div> : null}
    {upstreamFields.length ? <Popover trigger="click" placement="bottomLeft" content={
      <div className="gc-upstream-panel flex w-[min(380px,80vw)] flex-col gap-2.5">
        {upstreamFields.map(field => <div className="gc-upstream-field flex flex-col gap-1 text-[11px] text-[var(--app-surface-text-muted)]" key={field.name}>
          <span>上游 · {field.label}</span>
          <Select size="small" value={upstream[field.name]} options={field.options} placeholder="请选择已通过版本"
            aria-label={`上游 · ${field.label}`}
            disabled={hasDraft || busy}
            getPopupContainer={trigger => (trigger.closest('.gc-upstream-panel') as HTMLElement | null) ?? document.body}
            onChange={value => setUpstream(previous => ({ ...previous, [field.name]: value }))}
            optionRender={option => <span>{option.label}{option.value === field.latestUpstreamId ? ' · 最新' : ' · 历史'}</span>} />
        </div>)}
      </div>
    }>
      <Button size="small" className={`gc-upstream-trigger inline-flex max-w-[min(460px,40vw)] items-center gap-1.5${upstreamMissing ? ' has-missing border-[var(--app-danger-border)] text-[var(--app-profile-danger-text)]' : ''}`} aria-label="选择上游版本">
        <span className="gc-upstream-trigger-text min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">上游 {upstreamSummary}</span>
        <DownOutlined className="gc-upstream-caret text-[10px]" />
      </Button>
    </Popover> : null}
    {comparisonId ? <Button size="small" type={isDiff ? 'primary' : 'default'} ghost={!isDiff} icon={<DiffOutlined />}
      aria-pressed={isDiff}
      onClick={() => { setDiffOpen(!diffOpen); if (!diffOpen) setMode('raw') }}>
      对比 {comparisonContent ? (versionKey === 'draft' ? stage.draft?.baseVersionLabel : '上一版') : ''}
      {isDiff ? <span className="gc-diff-count ml-1 inline-flex gap-1 font-mono text-[10px] [&_b]:font-semibold [&_b]:text-[var(--app-result-success-text)] [&_i]:font-semibold [&_i]:not-italic [&_i]:text-[var(--app-profile-danger-text)]"><b>+{diffCounts.add}</b><i>−{diffCounts.remove}</i></span> : null}
    </Button> : null}
    {!stageRunning && stage.versions.length ? <Popover open={historyOpen} onOpenChange={setHistoryOpen} trigger="click" placement="bottomRight"
      content={<VersionHistory stage={stage} versions={stage.versions} latestId={latestId}
        activeVersion={versionKey} canWrite={canWrite}
        onPick={id => { setVersionKey(id); setDiffOpen(false); setHistoryOpen(false) }}
        onDelete={id => deleteVersion.mutate(id)} />}>
      <Button size="small" icon={<HistoryOutlined />}>版本 {stage.versions.length}</Button>
    </Popover> : null}
  </div>

  return inline ? controls : <><span ref={anchor} hidden />{target ? createPortal(controls, target) : null}</>
}

export function GenerationChainModal({ workspace, requirementId, projectId, open, onClose, onOpenLegacy, embedded = false, inspectorContainer, inspectorActionContainer, readingActionsContainer, showApiRunInInspector = false, uiSourceOptions, onOpenProfile }: {
  embedded?: boolean
  showApiRunInInspector?: boolean
  inspectorContainer?: HTMLElement | null
  inspectorActionContainer?: HTMLElement | null
  readingActionsContainer?: HTMLElement | null
  uiSourceOptions?: UiGenerationSourceOptionsState
  onOpenProfile?: () => void
  workspace: GenerationChainWorkspace
  requirementId: string
  projectId: string
  open: boolean
  onClose: () => void
  onOpenLegacy: (kind: GenerationChainKind) => void
}) {
  const {
    chain, stage, selected, versionKey, selectedVersion,
    versionDetail, displayedContent, workingContent, comparisonContent, comparisonId, diffOpen, setDiffOpen,
    mode, setMode, revisionOpen: workspaceRevisionOpen, setRevisionOpen,
    revisionInstruction, setRevisionInstruction, upstream,
    runStage, review, revise, importOpen, importVersion,
    importableVersionId, openImport, closeImport, busy, operationPending, detail,
  } = workspace
  const stageRunning = stage?.state === 'running'
  const revisionOpen = workspaceRevisionOpen && !stageRunning
  const stageHasContent = !stageRunning && workingContent.trim().length > 0
  const stageHasArtifact = !stageRunning && Boolean(stage?.draft || stage?.versions.length || stageHasContent)
  const modePanelRef = useViewMotion(mode === 'visual' ? 0 : 1)
  const [inputsOpen, setInputsOpen] = useState(false)
  const access = useProjectAccess(projectId)
  const canWrite = access.can('write')
  const finalStage = Boolean(stage && chain && stage.order === chain.stages.length - 1)
  const invalidDraft = !stageRunning && Boolean(stage?.draft?.invalidated)
  const hasDraft = !stageRunning && Boolean(stage?.draft && !invalidDraft)
  const viewingDraft = versionKey === 'draft'
  const draftActions = hasDraft && viewingDraft
  // 只要有待审核草稿且有写权限就可输入；工作副本在首次输入时建立，不依赖编辑态初始化时序。
  const draftEditable = Boolean(draftActions && canWrite)
  const rejected = !stageRunning && stage?.draft?.status === 'rejected'
  const upstreamVersions = versionKey === 'draft' ? stage?.draft?.upstreamVersions : versionDetail.data?.upstreamVersions
  const sourceInputs = versionKey === 'draft' ? stage?.draft?.sourceInputs : selectedVersion ? versionDetail.data?.sourceInputs : chain?.sourceInputs
  const uiSurface = chain?.kind === 'ui' && stage?.stage === 'ui_surface'
  const canRun = Boolean(chain?.configured && stage && !busy && !stage.blockedReason && !hasDraft)
  const canApprove = Boolean(draftActions && !rejected && !workspace.editingDirty && !operationPending && stage?.state !== 'running')
  const canReject = Boolean(draftActions && !rejected && !operationPending && stage?.state !== 'running')
  const canImport = Boolean(
    finalStage
    && versionKey !== 'draft'
    && importableVersionId
    && chain?.kind !== 'requirement_analysis'
    && !busy
    && !importVersion.isPending,
  )
  const isDiff = diffOpen && Boolean(comparisonId)
  // 阶段产物沿用对应页签的阅读容器：材料/理解对照、测试范围风险分析、测试点、完整用例、API 链路与 UI 三阶段。
  const stageKind = chain?.kind
  const stageName = stage?.stage
  const reviewStage = stageKind === 'requirement_analysis' && stageName === 'requirement_review'
  const analysisVersionId = stageKind === 'function' && stageName === 'case_names' ? upstreamVersions?.requirement_analysis : undefined
  const analysisUpstream = useQuery({
    queryKey: ['generationChain', requirementId, 'function', 'version', analysisVersionId],
    queryFn: () => generationChainApi.version(requirementId, 'function', analysisVersionId!),
    enabled: Boolean(requirementId && analysisVersionId),
  })
  const materialVersionId = stageKind === 'function' && stageName === 'requirement_analysis'
    ? upstreamVersions?.extracting_text : analysisUpstream.data?.upstreamVersions?.extracting_text
  const materialUpstream = useQuery({
    queryKey: ['generationChain', requirementId, 'requirement_analysis', 'version', materialVersionId],
    queryFn: () => generationChainApi.version(requirementId, 'requirement_analysis', materialVersionId!),
    enabled: Boolean(requirementId && materialVersionId),
  })
  const stageArtifactClass = stageKind === 'requirement_analysis'
    ? reviewStage ? 'is-requirement-review' : 'is-material-comparison'
    : stageKind === 'function'
      ? stageName === 'case_names' ? 'is-case-names' : stageName === 'detailed_cases' ? 'is-detailed-cases' : 'is-requirement-analysis'
      : stageKind === 'api' ? stageName === 'api_design' ? 'is-api-design' : 'is-api-cases' : stageKind === 'ui' ? 'is-ui-stage' : ''
  const rawLabel = workingContent.trim().startsWith('{') || workingContent.trim().startsWith('[') ? 'JSON' : 'YAML'
  const rawContent = useMemo(() => formatRawArtifact(workingContent, rawLabel), [workingContent, rawLabel])
  const copyText = mode === 'raw' ? rawContent : undefined

  if (!selected) return null
  if (detail.isPending && !stage) {
    return <GenerationArtifactFrame embedded={embedded} open={open} onCancel={onClose} footer={null} width={720} centered><Spin /></GenerationArtifactFrame>
  }
  if (detail.error && !stage) {
    return <GenerationArtifactFrame embedded={embedded} open={open} onCancel={onClose} footer={null} width={720} centered>
      <Alert showIcon type="error" title="阶段详情读取失败" description={String(detail.error)}
        action={<Button onClick={() => void detail.refetch()}>重试</Button>} />
    </GenerationArtifactFrame>
  }
  if (!stage || !chain) return null

  const trace = <div className="gc-trace">
    <span>追溯</span>
    {stage.upstreamStages.length ? stage.upstreamStages.map(name => {
      const upstreamStage = workspace.upstreamStages.find(item => item.stage === name)
      const selectedId = versionKey === 'draft' || !versionKey ? upstream[name] : upstreamVersions?.[name]
      const version = upstreamStage?.versions.find(item => item.versionId === selectedId)
      if (versionKey && versionKey !== 'draft' && !version) return null
      const missing = selectedId && !version
      return <span className={`gc-trace-chip${missing ? ' is-danger' : ''}`} key={name}>
        {upstreamStage?.label ?? name}
        <b>{version?.label ?? (missing ? '上游已删除' : '未选择')}</b>
      </span>
    }) : chain.kind !== 'ui' ? <span className="gc-trace-chip">{chain.kind === 'api' ? '接口库接口' : '需求材料'} <b>只读来源</b></span> : null}
    {chain.kind === 'ui' ? <UiGenerationSourceTrace source={sourceInputs} loading={Boolean(selectedVersion && versionDetail.isFetching)} /> : null}
    {!stageRunning && stage.latestVersion?.imported ? <span className="gc-trace-chip is-ok"><CheckCircleFilled /> 已导入正式资产</span> : null}
  </div>

  const footer = <div className="gc-modal-footer flex flex-col gap-2">
    <div className="gc-footer-row flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div className="gc-footer-status flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1.5">
        {!embedded ? trace : null}
        {!stageRunning && workspace.editingDirty ? <div className="gc-modal-meta is-warn flex flex-wrap items-center gap-1.5 p-0 text-[11px] text-[var(--app-status-warning-text)]">修改尚未保存，保存后才能审核。</div> : null}
        {versionKey !== 'draft' && selectedVersion?.createdAt ? <div className="gc-modal-meta flex flex-wrap items-center gap-1.5 p-0 text-[11px] text-[var(--app-surface-text-muted)]">
          <ClockCircleOutlined /> {selectedVersion.label} · {formatTime(selectedVersion.createdAt)} · {selectedVersion.reviewerUserId || '系统'}
          {selectedVersion.imported ? ' · 已导入' : ''}
        </div> : null}
      </div>
      {revisionOpen ? null : <div className="gc-modal-actions ml-auto flex flex-wrap items-center justify-end gap-2">
        {!embedded ? <Button onClick={onClose}>关闭</Button> : null}
        {uiSurface && chain.runId ? <ProjectActionButton action="execute" disabled={busy} onClick={() => setInputsOpen(true)}>更换输入并重新生成</ProjectActionButton> : null}
        {canImport ? <ProjectActionButton action="execute" type="primary" ghost onClick={openImport}>导入此版本</ProjectActionButton> : null}
        {draftActions && canWrite && workspace.editingDirty ? <>
          <Button disabled={workspace.saveDraft.isPending} onClick={workspace.resetEditing}>撤销修改</Button>
          <ProjectActionButton action="write" type="primary" disabled={workspace.saveDraft.isPending} onClick={() => workspace.saveDraft.mutate()}>保存修改</ProjectActionButton>
        </> : null}
        {draftActions ? <ProjectActionButton action="execute" disabled={busy || workspace.editingDirty} title={workspace.editingDirty ? '请先保存修改' : undefined} onClick={workspace.openRevision}>继续优化</ProjectActionButton> : null}
        {draftActions && !rejected ? <ProjectActionButton action="review" danger ghost disabled={!canReject} onClick={() => review.mutate({ action: 'reject' })}>审核不通过</ProjectActionButton> : null}
        {draftActions && !rejected ? <ProjectActionButton action="review" type={finalStage ? 'primary' : 'default'} disabled={!canApprove} title={workspace.editingDirty ? '请先保存修改' : undefined} onClick={() => review.mutate({ action: 'approve' })}>审核通过</ProjectActionButton> : null}
        {draftActions && !rejected && !finalStage ? <ProjectActionButton action="review" type="primary" disabled={!canApprove || busy} title={workspace.editingDirty ? '请先保存修改' : undefined} onClick={() => review.mutate({ action: 'approve', continueAfter: true })}>审核通过并继续 <RightOutlined /></ProjectActionButton> : null}
        {!hasDraft && (!viewingDraft || invalidDraft) ? <Tooltip title={stage.blockedReason || (stage.state === 'running' ? '当前阶段正在执行' : undefined)}>
          <span tabIndex={stage.blockedReason ? 0 : undefined} aria-label={stage.blockedReason}>
            <ProjectActionButton action="execute" operation={stage.latestVersion ? 'run' : 'create'} type="primary"
              disabled={!canRun} loading={runStage.isPending} onClick={() => {
                if (uiSurface && !chain.runId) setInputsOpen(true)
                else runStage.mutate()
              }}>
              {invalidDraft ? '重新生成此阶段' : stage.latestVersion ? uiSurface ? '使用原输入重新生成' : '按所选上游重新生成' : stage.state === 'failed' ? '重新运行' : '运行此阶段'}
            </ProjectActionButton>
          </span>
        </Tooltip> : null}
      </div>}
    </div>
  </div>

  const artifactScrollClass = `gc-artifact-scroll${!isDiff && mode === 'raw' ? ' is-raw' : ''}${!isDiff && mode !== 'raw' && stageArtifactClass ? ` ${stageArtifactClass}` : ''}`
  const modeOptions = [{ label: '可视化', value: 'visual' }, { label: rawLabel, value: 'raw' }]
  // 画布内阅读时，视图切换与复制跟随正文放在右上角；侧栏只保留版本、上游与对比。
  const readingModeControls = <ArtifactModeControls
    value={mode}
    onChange={value => { setMode(value as 'visual' | 'raw'); setDiffOpen(false) }}
    options={modeOptions}
    copyText={copyText}
    copyLabel={`复制 ${rawLabel}`}
  />
  const readingControls = <>
    <ChainHeaderControls inline={embedded} workspace={workspace} canWrite={canWrite} />
    {!embedded && stageHasArtifact ? <ArtifactModeSwitch
      value={mode}
      onChange={value => { setMode(value as 'visual' | 'raw'); setDiffOpen(false) }}
      options={modeOptions}
      copyText={copyText}
      copyLabel={`复制 ${rawLabel}`}
    /> : null}
  </>
  // 画布内阅读时，视图切换与复制放进页面标题栏；阅读正文不再保留工具行。
  const readingHeaderActions = embedded && open && readingActionsContainer && stageHasArtifact
    ? createPortal(readingModeControls, readingActionsContainer)
    : null
  const revisionPanel = <>
      {revisionOpen ? <RevisionSidePanel projectId={projectId} value={revisionInstruction} sourceEditable={false}
        onChange={setRevisionInstruction} loading={revise.isPending}
        attachments={workspace.revisionAttachments.attachments}
        onAddAttachment={workspace.revisionAttachments.addAttachment}
        onRemoveAttachment={workspace.revisionAttachments.removeAttachment}
        onSubmit={connectionId => revise.mutate(connectionId)}
        onCancel={() => setRevisionOpen(false)} /> : null}
  </>
  const inspector = embedded && open && inspectorContainer && (stageHasArtifact || stage.upstreamStages.length) ? createPortal(<div className="gc-inspector-reading-tools">
    <section className="gc-inspector-section"><h3>阅读工具</h3>{readingControls}</section>
  </div>, inspectorContainer) : null
  const inspectorActions = embedded && (open || (showApiRunInInspector && chain.kind === 'api' && !hasDraft)) && inspectorActionContainer && !revisionOpen ? createPortal(
    <section className="gc-inspector-review gc-inspector-reading-tools flex flex-col gap-3 border-t border-[var(--app-surface-border)] bg-[var(--app-list-toolbar-bg)] p-4">
      <div className="gc-inspector-review-heading flex items-center justify-between gap-2"><h3 className="m-0 text-[12px] font-semibold">{revisionOpen ? '继续优化' : '阶段操作'}</h3>
        {versionDetail.isFetching ? <Spin size="small" /> : null}
      </div>
      {footer}
    </section>, inspectorActionContainer) : null

  return <><GenerationArtifactFrame embedded={embedded} hideHeader={embedded}
    open={open}
    onCancel={onClose}
    footer={embedded ? null : footer}
    width={stageKind === 'api' ? 'min(1620px, calc(100vw - 72px))' : 'min(2000px, calc(100vw - 56px))'}
    centered
    destroyOnHidden
    rootClassName={artifactScopes}
    className={`generation-chain-modal${revisionOpen ? ' is-revising' : ''}${embedded ? ' gc-inspector-reading' : ''}`}
    title={embedded ? stage.label : <div className="gc-modal-title flex min-w-0 flex-wrap items-center gap-3">
      <div className="gc-title-main flex min-w-0 flex-col gap-px">
        <span className="gc-kicker mb-0 block text-[11px] uppercase tracking-[0.08em] text-[var(--gc-muted)]">{chain.label} / 第 {stage.order + 1} 阶段</span>
        <div className="gc-title-name flex flex-wrap items-center gap-2">
          <strong className="text-[16px] leading-[1.35]">{stage.label}</strong>
          <span className={`${GC_STATE_CLASS} ${rejected ? 'is-danger' : stateClass(stage.state)}`}>{rejected ? '已退回' : stateCopy[stage.state] ?? stage.state}</span>
        </div>
      </div>
    </div>}
  >
    {!embedded ? readingControls : null}
    <div className={`gc-workspace revision-workspace flex h-full min-h-0 min-w-0 flex-1 gap-0${revisionOpen ? ' is-revising' : ''}`}>
      <div className={`${embedded ? "gc-reading-body" : "gc-source"}${embedded ? ' flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden' : ' flex h-full min-h-0 w-full min-w-0 flex-1 flex-col px-6 pt-3'}${revisionOpen ? " revision-source" : ""}`}>
        {chain.sourceChanged ? <Alert showIcon type="warning" title={chain.kind === 'ui' ? '来源仓库或功能用例已更新。请在元素控件清单更换输入后重新生成；旧版本保留输入快照。' : '需求材料已更新，旧版本保留生成时的材料快照。'} /> : null}
        {invalidDraft ? <Alert showIcon type="warning" title="产物已作废"
          description={stage.draft?.invalidatedReason || '该产物依赖的上游版本已被删除，不能继续审核或优化，请重新生成。'} /> : null}
        {stage.state === 'failed' ? <Alert showIcon type="error" style={{ whiteSpace: 'pre-line' }}
          title={stage.errorMessage || '阶段执行失败，Worker 未返回具体原因'} /> : null}
        {stage.blockedReason ? <Alert showIcon type="info" title={stage.blockedReason} /> : null}

        {!embedded && !stageRunning ? <div className="gc-artifact-head flex flex-none flex-wrap items-center gap-2 pb-[7px] pt-[9px]">
          <div className="flex min-w-0 items-baseline gap-2">
            <strong className="text-[12px]">{versionKey === 'draft' ? '待审核产物' : selectedVersion ? `${selectedVersion.label} 已通过版本` : '阶段产物'}</strong>
            <span className="overflow-hidden text-ellipsis whitespace-nowrap text-[11px] text-[var(--app-surface-text-muted)]">{versionKey === 'draft' ? stage.draft?.summary : selectedVersion?.summary ?? stage.latestVersion?.summary}</span>
          </div>
          {versionDetail.isFetching ? <Spin size="small" /> : null}
        </div> : null}

        {stage.moduleGeneration && (stage.state === 'running' || stage.state === 'failed' || !stageHasContent ||
          (versionKey === 'draft' && stage.draft?.attemptId === stage.moduleGeneration.attemptId)) ?
          <ModuleGenerationProgressPanel key={stage.moduleGeneration.attemptId} progress={stage.moduleGeneration} /> : null}
        <div ref={modePanelRef} className={artifactScrollClass}>
          {reviewStage && !stageHasContent && !stageRunning ? <div className="mx-auto flex w-full max-w-[720px] flex-1 flex-col gap-2 p-6">
            <p className="mb-1 mt-0 text-[13px] leading-[1.7] text-app-surface-text-muted">运行需求评审后，这里会显示问题登记表、覆盖度和评审结论。评审仅提示问题，不阻断材料整理。</p>
          </div> : !stageHasContent ? (stage.state === 'running' && !stage.moduleGeneration ? <div className="gc-stage-loading flex h-full min-h-[240px] flex-1 flex-col items-center justify-center gap-2.5 p-6 text-[12px] text-[var(--app-surface-text-muted)]" role="status" aria-live="polite">
            <Spin /><span>正在生成{stage.label}</span>
          </div> : null) : isDiff ? <GenerationArtifactDiff before={comparisonContent} after={displayedContent}
            beforeLabel={stage.versions.find(version => version.versionId === comparisonId)?.label ?? '旧版本'}
            afterLabel={versionKey === 'draft' ? '待审核产物' : selectedVersion?.label ?? '当前内容'} /> : mode === 'raw'
            ? <div className="gc-raw-editor">
              <TextCodeEditor language="auto" ariaLabel={`阶段产物 ${rawLabel}`} readOnly={!draftEditable} height="100%" minHeight={0}
                value={workspace.editing?.content ?? (rawContent || '暂无内容')} onChange={workspace.setEditingContent} />
            </div>
            : stageKind === 'requirement_analysis'
              ? reviewStage
                ? <RequirementReviewView content={workingContent} />
                : <RequirementMaterialComparison content={workingContent} editable={draftEditable} onChange={workspace.setEditingContent} />
              : stageKind === 'function'
                ? stageName === 'requirement_analysis'
                  ? <RequirementAnalysisDiagramView content={workingContent} materialContent={materialUpstream.data?.content} />
                  : stageName === 'case_names'
                    ? <TraceablePointsView content={workingContent} materialContent={materialUpstream.data?.content} onChange={draftEditable ? workspace.setEditingContent : undefined} rootTitle={stage.label} />
                    : <GeneratedCasesReviewView content={workingContent} rootTitle={stage.label}
                      onChange={draftEditable ? workspace.setEditingContent : undefined} />
                : stageKind === 'api'
                  ? stageName === 'interface_extract'
                    ? <ApiConfigDiagramView content={workingContent} />
                    : stageName === 'api_design'
                      ? <ApiDesignDiagramView content={workingContent} onShowRaw={() => setMode('raw')} />
                      : <ApiCandidateResultView content={workingContent} />
                  : stageKind === 'ui'
                    ? <div className="ui-generation-stage-visual"><UiStageVisual stage={stageName as UiGenerationStage} content={workingContent} onShowRaw={() => setMode('raw')} /></div>
                    : <ChainVisualArtifact content={workingContent} />}
        </div>

        {!chain.configured ? <div className="gc-empty-panel mt-3 flex flex-col items-start gap-1.5 rounded-[10px] border border-dashed border-[var(--app-surface-border)] p-[18px] text-[var(--app-surface-text-muted)]">
          <ExclamationCircleOutlined />
          <strong className="text-[13px] text-[var(--app-surface-text)]">还没有配置{chain.label}任务</strong>
          <span className="text-[12px]">先设置生成方式和输入材料，再运行首个阶段。</span>
          <Button type="primary" onClick={() => onOpenLegacy(chain.kind)}>前往设置</Button>
        </div> : null}
      </div>

      {revisionOpen ? <><RevisionDivider />{revisionPanel}</> : null}
    </div>

    {open && inputsOpen && chain.kind === 'ui' ? <UiGenerationInputsModal key={chain.taskId}
      requirementId={requirementId}
      refreshInputs={Boolean(chain.runId)} source={chain.sourceInputs} busy={stageRunning}
      sourceOptions={uiSourceOptions ?? { loading: false }}
      onOpenProfile={onOpenProfile}
      onClose={() => setInputsOpen(false)} onSubmit={inputs => runStage.mutateAsync(inputs)} /> : null}
    <GenerationChainImportModal workspace={workspace} open={importOpen && !stageRunning} onClose={closeImport} />
  </GenerationArtifactFrame>{inspector}{inspectorActions}{readingHeaderActions}</>
}
