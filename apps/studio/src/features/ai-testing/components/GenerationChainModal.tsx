import {
  CheckCircleFilled,
  ClockCircleOutlined,
  DeleteOutlined,
  DiffOutlined,
  DownOutlined,
  ExclamationCircleOutlined,
  HistoryOutlined,
  ReloadOutlined,
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
import { CaseNameTreeView } from './CaseNamesResultView'
import { GeneratedCasesReviewView } from './GeneratedCasesReviewView'
import { GenerationChainImportModal } from './GenerationChainImportModal'
import { RequirementAnalysisDiagramView } from './RequirementAnalysisView'
import { RequirementMaterialComparison } from './RequirementMaterialComparison'
import { RequirementUnderstandingComparison } from './RequirementUnderstandingComparison'
import { RevisionDivider, RevisionSidePanel } from './RevisionSidePanel'
import { ArtifactModeControls, ArtifactModeSwitch } from './ArtifactViewTabs'
import { useViewMotion } from '@/shared/ui/useViewMotion'
import { UiStageVisual } from './uiStageVisual/UiStageVisual'
import { ChainVisualArtifact } from './ChainVisualArtifact'
import { UiGenerationInputsModal } from './UiGenerationInputsModal'
import { UiGenerationSourceTrace } from './UiGenerationSourceTrace'
import type { GenerationChainWorkspace } from '../hooks/useRequirementGenerationChain'
import type { GenerationChainKind, GenerationChainStage, GenerationChainVersion } from '../api/generationChain.api'
import type { UiGenerationStage } from '../utils/uiGenerationStage'
import { generationChainApi } from '../api/generationChain.api'
import { diffArtifact, diffStats } from '../utils/chainArtifact'
import { generationFailureMeta } from '../utils/generationStageDisplay'
import { GenerationArtifactFrame } from './GenerationArtifactFrame'
import { GenerationArtifactDiff } from './GenerationArtifactDiff'

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

function formatRawArtifact(content: string, label: string) {
  if (label !== 'JSON' || !content.trim()) return content
  try {
    return JSON.stringify(JSON.parse(content), null, 2)
  } catch {
    return content
  }
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
  return <div className="gc-history" role="dialog" aria-label={`${stage.label} 版本历史`}>
    <div className="gc-history-head"><strong>版本历史</strong><span>{versions.length ? `共 ${versions.length} 个已通过版本` : '还没有已通过版本'}</span></div>
    {versions.length ? versions.map(version => <div className={`gc-history-row${activeVersion === version.versionId ? ' is-active' : ''}`} key={version.versionId}>
      <button type="button" className="gc-history-main" onClick={() => onPick(version.versionId)}>
        <span className="gc-version-chip">{version.label}</span>
        <span className="gc-history-copy">
          <strong>{version.summary}</strong>
          <small>{formatTime(version.createdAt)}{version.reviewerUserId ? ` · ${version.reviewerUserId}` : ''}</small>
        </span>
        {version.versionId === latestId ? <Tag color="success">最新</Tag> : null}
      </button>
      {canWrite ? <Popconfirm title={`删除 ${version.label}？`} description="依赖它的待审核产物会作废，已通过的下游版本保留。" okText="删除" cancelText="取消"
        onConfirm={() => onDelete(version.versionId)}>
        <Button size="small" type="text" danger aria-label={`删除版本 ${version.label}`} icon={<DeleteOutlined />} />
      </Popconfirm> : null}
    </div>) : <div className="gc-history-empty">审核通过后才会产生版本。</div>}
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
    slot.className = 'gc-header-tools-slot'
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

  const controls = <div className="gc-title-tools">
    {!inline ? <div className="gc-version-buttons" role="group" aria-label="选择版本">
      {versionOptions.length ? versionOptions.map(option => <button key={option.key} type="button"
        className={`gc-version-button${versionKey === option.key ? ' is-active' : ''}`}
        aria-pressed={versionKey === option.key}
        onClick={() => { setVersionKey(option.key); setDiffOpen(false) }}>
        {option.label}
        {option.key === latestId ? <span className="gc-latest-dot" aria-label="最新版本" /> : null}
      </button>) : <span className="gc-version-empty">还没有产物版本</span>}
    </div> : null}
    {upstreamFields.length ? <Popover trigger="click" placement="bottomLeft" content={
      <div className="gc-upstream-panel">
        {upstreamFields.map(field => <div className="gc-upstream-field" key={field.name}>
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
      <Button size="small" className={`gc-upstream-trigger${upstreamMissing ? ' has-missing' : ''}`} aria-label="选择上游版本">
        <span className="gc-upstream-trigger-text">上游 {upstreamSummary}</span>
        <DownOutlined className="gc-upstream-caret" />
      </Button>
    </Popover> : null}
    <Button size="small" type={isDiff ? 'primary' : 'default'} ghost={!isDiff} icon={<DiffOutlined />}
      aria-pressed={isDiff} disabled={!comparisonId}
      onClick={() => { setDiffOpen(!diffOpen); if (!diffOpen) setMode('raw') }}>
      对比 {comparisonContent ? (versionKey === 'draft' ? stage.draft?.baseVersionLabel : '上一版') : ''}
      {isDiff ? <span className="gc-diff-count"><b>+{diffCounts.add}</b><i>−{diffCounts.remove}</i></span> : null}
    </Button>
    <Popover open={historyOpen} onOpenChange={setHistoryOpen} trigger="click" placement="bottomRight"
      content={<VersionHistory stage={stage} versions={stage.versions} latestId={latestId}
        activeVersion={versionKey} canWrite={canWrite}
        onPick={id => { setVersionKey(id); setDiffOpen(false); setHistoryOpen(false) }}
        onDelete={id => deleteVersion.mutate(id)} />}>
      <Button size="small" icon={<HistoryOutlined />}>版本 {stage.versions.length}</Button>
    </Popover>
  </div>

  return inline ? controls : <><span ref={anchor} hidden />{target ? createPortal(controls, target) : null}</>
}

export function GenerationChainModal({ workspace, requirementId, projectId, open, onClose, onOpenLegacy, embedded = false, inspectorContainer, inspectorActionContainer, readingActionsContainer, showApiRunInInspector = false }: {
  embedded?: boolean
  showApiRunInInspector?: boolean
  inspectorContainer?: HTMLElement | null
  inspectorActionContainer?: HTMLElement | null
  readingActionsContainer?: HTMLElement | null
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
    mode, setMode, revisionOpen, setRevisionOpen,
    revisionInstruction, setRevisionInstruction, upstream,
    runStage, review, revise, importOpen, importVersion,
    importableVersionId, openImport, closeImport, busy, operationPending, detail,
  } = workspace
  const modePanelRef = useViewMotion(mode === 'visual' ? 0 : 1)
  const [inputsOpen, setInputsOpen] = useState(false)
  const access = useProjectAccess(projectId)
  const canWrite = access.can('write')
  const finalStage = Boolean(stage && chain && stage.order === chain.stages.length - 1)
  const invalidDraft = Boolean(stage?.draft?.invalidated)
  const hasDraft = Boolean(stage?.draft && !invalidDraft)
  const viewingDraft = versionKey === 'draft'
  const draftActions = hasDraft && viewingDraft
  // 只要有待审核草稿且有写权限就可输入；工作副本在首次输入时建立，不依赖编辑态初始化时序。
  const draftEditable = Boolean(draftActions && canWrite)
  const rejected = stage?.draft?.status === 'rejected'
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
  // 阶段产物沿用对应页签的阅读容器：材料/理解对照、测试需求分析、测试点、完整用例、API 链路与 UI 三阶段。
  const stageKind = chain?.kind
  const stageName = stage?.stage
  const materialExtraction = stageName === 'extracting_text' && stageKind === 'requirement_analysis'
  const pointsVersionId = stageKind === 'function' && stageName === 'detailed_cases' ? upstreamVersions?.case_names : undefined
  const pointsUpstream = useQuery({
    queryKey: ['generationChain', requirementId, 'function', 'version', pointsVersionId],
    queryFn: () => generationChainApi.version(requirementId, 'function', pointsVersionId!),
    enabled: Boolean(requirementId && pointsVersionId),
  })
  const stageArtifactClass = stageKind === 'requirement_analysis'
    ? 'is-material-comparison'
    : stageKind === 'function'
      ? stageName === 'case_names' ? 'is-case-names' : stageName === 'detailed_cases' ? 'is-detailed-cases' : 'is-requirement-analysis'
      : stageKind === 'api' ? 'is-api-cases' : stageKind === 'ui' ? 'is-ui-stage' : ''
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
    }) : chain.kind !== 'ui' ? <span className="gc-trace-chip">{chain.kind === 'api' ? 'OpenAPI 文档' : '需求材料'} <b>只读来源</b></span> : null}
    {chain.kind === 'ui' ? <UiGenerationSourceTrace source={sourceInputs} loading={Boolean(selectedVersion && versionDetail.isFetching)} /> : null}
    {stage.latestVersion?.imported ? <span className="gc-trace-chip is-ok"><CheckCircleFilled /> 已导入正式资产</span> : null}
  </div>

  const footer = <div className="gc-modal-footer">
    <div className="gc-footer-row">
      <div className="gc-footer-status">
        {!embedded ? trace : null}
        {workspace.editingDirty ? <div className="gc-modal-meta is-warn">修改尚未保存，保存后才能审核。</div> : null}
        {versionKey !== 'draft' && selectedVersion?.createdAt ? <div className="gc-modal-meta">
          <ClockCircleOutlined /> {selectedVersion.label} · {formatTime(selectedVersion.createdAt)} · {selectedVersion.reviewerUserId || '系统'}
          {selectedVersion.imported ? ' · 已导入' : ''}
        </div> : null}
      </div>
      {revisionOpen ? null : <div className="gc-modal-actions">
        {!embedded ? <Button onClick={onClose}>关闭</Button> : null}
        {uiSurface && chain.runId ? <ProjectActionButton action="execute" disabled={busy || chain.busy} onClick={() => setInputsOpen(true)}>更换输入并重新生成</ProjectActionButton> : null}
        {canImport ? <ProjectActionButton action="execute" type="primary" ghost onClick={openImport}>导入此版本</ProjectActionButton> : null}
        {draftActions && canWrite && workspace.editingDirty ? <>
          <Button disabled={workspace.saveDraft.isPending} onClick={workspace.resetEditing}>撤销修改</Button>
          <ProjectActionButton action="write" type="primary" disabled={workspace.saveDraft.isPending} onClick={() => workspace.saveDraft.mutate()}>保存修改</ProjectActionButton>
        </> : null}
        {draftActions ? <ProjectActionButton action="execute" disabled={busy || workspace.editingDirty} title={workspace.editingDirty ? '请先保存修改' : undefined} onClick={workspace.openRevision}>继续优化</ProjectActionButton> : null}
        {draftActions && !rejected ? <ProjectActionButton action="review" danger ghost disabled={!canReject} onClick={() => review.mutate({ action: 'reject' })}>审核不通过</ProjectActionButton> : null}
        {draftActions && !rejected ? <ProjectActionButton action="review" type={finalStage ? 'primary' : 'default'} disabled={!canApprove} title={workspace.editingDirty ? '请先保存修改' : undefined} onClick={() => review.mutate({ action: 'approve' })}>审核通过</ProjectActionButton> : null}
        {draftActions && !rejected && !finalStage ? <ProjectActionButton action="review" type="primary" disabled={!canApprove || busy} title={workspace.editingDirty ? '请先保存修改' : undefined} onClick={() => review.mutate({ action: 'approve', continueAfter: true })}>审核通过并继续 <RightOutlined /></ProjectActionButton> : null}
        {!hasDraft && (!viewingDraft || invalidDraft) ? <Tooltip title={stage.blockedReason || (chain.active ? '当前链路正在执行' : undefined)}>
          <span tabIndex={stage.blockedReason ? 0 : undefined} aria-label={stage.blockedReason}>
            <ProjectActionButton action="execute" operation={stage.latestVersion ? 'run' : 'create'} type="primary"
              disabled={!canRun} loading={runStage.isPending} onClick={() => { if (uiSurface && !chain.runId) setInputsOpen(true); else runStage.mutate() }}>
              {invalidDraft ? '重新生成此阶段' : stage.latestVersion ? uiSurface ? '使用原输入重新生成' : '按所选上游重新生成' : '运行此阶段'}
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
    {!embedded ? <ArtifactModeSwitch
      value={mode}
      onChange={value => { setMode(value as 'visual' | 'raw'); setDiffOpen(false) }}
      options={modeOptions}
      copyText={copyText}
      copyLabel={`复制 ${rawLabel}`}
    /> : null}
  </>
  // 画布内阅读时，视图切换与复制放进页面标题栏；阅读正文不再保留工具行。
  const readingHeaderActions = embedded && open && readingActionsContainer
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
  const inspector = embedded && open && inspectorContainer ? createPortal(<div className="gc-inspector-reading-tools">
    <section className="gc-inspector-section"><h3>阅读工具</h3>{readingControls}</section>
  </div>, inspectorContainer) : null
  const inspectorActions = embedded && (open || (showApiRunInInspector && chain.kind === 'api' && !hasDraft)) && inspectorActionContainer && !revisionOpen ? createPortal(
    <section className="gc-inspector-review gc-inspector-reading-tools">
      <div className="gc-inspector-review-heading"><h3>{revisionOpen ? '继续优化' : '阶段操作'}</h3>
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
    className={`generation-chain-modal${revisionOpen ? ' is-revising' : ''}${embedded ? ' gc-inspector-reading' : ''}`}
    title={embedded ? stage.label : <div className="gc-modal-title">
      <div className="gc-title-main">
        <span className="gc-kicker">{chain.label} / 第 {stage.order + 1} 阶段</span>
        <div className="gc-title-name">
          <strong>{stage.label}</strong>
          <span className={`gc-state ${rejected ? 'is-danger' : stateClass(stage.state)}`}>{rejected ? '已退回' : stateCopy[stage.state] ?? stage.state}</span>
        </div>
      </div>
    </div>}
  >
    {!embedded ? readingControls : null}
    <div className={`gc-workspace revision-workspace${revisionOpen ? ' is-revising' : ''}`}>
      <div className={`${embedded ? "gc-reading-body" : "gc-source"}${revisionOpen ? " revision-source" : ""}`}>
        {chain.sourceChanged ? <Alert showIcon type="warning" title={chain.kind === 'ui' ? '源码包或功能用例已更新。请在元素控件清单更换输入后重新生成；旧版本保留输入快照。' : '需求材料已更新，旧版本保留生成时的材料快照。'} /> : null}
        {invalidDraft ? <Alert showIcon type="warning" title="产物已作废"
          description={stage.draft?.invalidatedReason || '该产物依赖的上游版本已被删除，不能继续审核或优化，请重新生成。'} /> : null}
        {stage.state === 'failed' ? <Alert showIcon type="error"
          title={stage.errorMessage || '阶段执行失败，Worker 未返回具体原因'}
          description={generationFailureMeta(stage) || '请重新执行；若持续失败，请查看 Worker 日志。'} /> : null}
        {stage.blockedReason ? <Alert showIcon type="info" title={stage.blockedReason} /> : null}

        {!embedded ? <div className="gc-artifact-head">
          <div>
            <strong>{versionKey === 'draft' ? '待审核产物' : selectedVersion ? `${selectedVersion.label} 已通过版本` : '阶段产物'}</strong>
            <span>{versionKey === 'draft' ? stage.draft?.summary : selectedVersion?.summary ?? stage.latestVersion?.summary}</span>
          </div>
          {versionDetail.isFetching ? <Spin size="small" /> : null}
        </div> : null}

        <div ref={modePanelRef} className={artifactScrollClass}>
          {isDiff ? <GenerationArtifactDiff before={comparisonContent} after={displayedContent}
            beforeLabel={stage.versions.find(version => version.versionId === comparisonId)?.label ?? '旧版本'}
            afterLabel={versionKey === 'draft' ? '待审核产物' : selectedVersion?.label ?? '当前内容'} /> : mode === 'raw'
            ? <div className="gc-raw-editor">
              <TextCodeEditor language="auto" ariaLabel={`阶段产物 ${rawLabel}`} readOnly={!draftEditable} height="100%" minHeight={0}
                value={workspace.editing?.content ?? (rawContent || '暂无内容')} onChange={workspace.setEditingContent} />
            </div>
            : stageKind === 'requirement_analysis'
              ? materialExtraction
                ? <RequirementMaterialComparison content={workingContent} editable={draftEditable} onChange={workspace.setEditingContent} />
                : <RequirementUnderstandingComparison hideTitle content={workingContent} />
              : stageKind === 'function'
                ? stageName === 'requirement_analysis'
                  ? <RequirementAnalysisDiagramView content={workingContent} />
                  : stageName === 'case_names'
                    ? <CaseNameTreeView content={workingContent} rootTitle={stage.label} expanded editable={draftEditable} onTreeChange={workspace.setEditingContent} />
                    : <GeneratedCasesReviewView content={workingContent} pointsContent={pointsUpstream.data?.content ?? ''} rootTitle={stage.label}
                      onChange={draftEditable ? workspace.setEditingContent : undefined} />
                : stageKind === 'api'
                  ? stageName === 'openapi_extract' ? <ApiConfigDiagramView content={workingContent} /> : <ApiCandidateResultView content={workingContent} />
                  : stageKind === 'ui'
                    ? <div className="ui-generation-stage-visual"><UiStageVisual stage={stageName as UiGenerationStage} content={workingContent} onShowRaw={() => setMode('raw')} /></div>
                    : <ChainVisualArtifact content={workingContent} />}
        </div>

        {!chain.configured ? <div className="gc-empty-panel">
          <ExclamationCircleOutlined />
          <strong>还没有配置{chain.label}任务</strong>
          <span>先设置生成方式和输入材料，再运行首个阶段。</span>
          <Button type="primary" onClick={() => onOpenLegacy(chain.kind)}>前往设置</Button>
        </div> : null}
      </div>

      {revisionOpen ? <><RevisionDivider />{revisionPanel}</> : null}
    </div>

    {stage.state === 'failed' ? <div className="gc-modal-meta is-danger"><ReloadOutlined /> 阶段执行失败，可在继续优化中重新生成。</div> : null}
    {open && inputsOpen && chain.kind === 'ui' ? <UiGenerationInputsModal key={chain.taskId}
      requirementId={requirementId} projectId={projectId} taskId={chain.taskId!}
      refreshInputs={Boolean(chain.runId)} source={chain.sourceInputs}
      onClose={() => setInputsOpen(false)} onSubmit={inputs => runStage.mutateAsync(inputs)} /> : null}
    <GenerationChainImportModal workspace={workspace} open={importOpen} onClose={closeImport} />
  </GenerationArtifactFrame>{inspector}{inspectorActions}{readingHeaderActions}</>
}
