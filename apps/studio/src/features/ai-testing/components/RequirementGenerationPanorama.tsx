import { CloseOutlined, EllipsisOutlined, FileTextOutlined, HistoryOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { getErrorMessage } from '@/utils/format'
import { randomId } from '@/shared/utils/crypto'
import { message } from '@/shared/utils/feedback'
import { canNavigateAway } from '@/shared/utils/unsavedChanges'
import { requirementDesignApi } from '../api/requirementDesign.api'
import { generationCandidatesApi } from '../api/generationCandidates.api'
import { useRequirementGenerationChain } from '../hooks/useRequirementGenerationChain'
import { useRequirementRepositoryProfileWorkspace } from '../hooks/useRequirementRepositoryProfileWorkspace'
import { useUiGenerationSourceOptions, useUiGenerationSourceSnapshot } from '../hooks/useUiGenerationSourceOptions'
import type { GenerationChain, GenerationChainKind, GenerationChainStage } from '../api/generationChain.api'
import { GenerationArtifactFrame } from './GenerationArtifactFrame'
import { GenerationChainModal } from './GenerationChainModal'
import { RequirementRepositoryProfileInspector } from './RequirementRepositoryProfileInspector'
import { RequirementRepositoryProfileReading } from './RequirementRepositoryProfileReading'
import { UiGenerationSourcePanel } from './UiGenerationSourcePanel'
import { ApiGenerationSourcePanel } from './ApiGenerationSourcePanel'
import { FunctionalCaseRelationsModal } from './FunctionalCaseRelationsModal'
import { RequirementGenerationCanvas } from './RequirementGenerationCanvas'
import { animateInspectorContents, animateReadingExit, setReadingOrigin } from './readingTransition'
import { generationFailureMeta } from '../utils/generationStageDisplay'
import { getRunPipelineModel } from '../utils/runPipeline'

const laneOrder: GenerationChainKind[] = ['requirement_analysis', 'function', 'api', 'ui']
/** 侧栏可交给页面级容器渲染，避免被画布大容器包裹；未提供 host 时保持内嵌。 */
function InspectorPortal({ host, children }: { host?: HTMLElement | null; children: ReactNode }) {
  return host ? createPortal(children, host) : <>{children}</>
}
type SpecialKind = 'content' | 'codeRisk' | 'repositoryProfile' | 'relations'
export type RequirementReadingNodeKind = 'document' | 'stage' | 'relations'
/** 阅读态交给页面标题栏的面包屑末项；leave 用于点上级需求名时退回生成流程。 */
export type RequirementReadingNode = { label: string; leave?: () => void; kind?: RequirementReadingNodeKind }
export function RequirementGenerationPanorama({ requirementId, projectId, canWrite, onOpenTab, documentPreview, onReadingNodeChange, inspectorHost }: {
  canWrite: boolean
  documentPreview?: ReactNode
  requirementId: string; projectId: string
  onOpenTab: (tab: 'content' | GenerationChainKind | 'codeRisk') => void
  onReadingNodeChange?: (node: RequirementReadingNode | null) => void
  inspectorHost?: HTMLElement | null
}) {
  const stageRef = useRef<HTMLDivElement>(null)
  const inspectorRef = useRef<HTMLElement>(null)
  const wasReading = useRef(false)
  const originRef = useRef<HTMLElement | undefined>(undefined)
  const exitAnimation = useRef<Animation | null>(null)
  useEffect(() => () => { exitAnimation.current?.cancel() }, [])
  const workspace = useRequirementGenerationChain({ requirementId, projectId, enabled: Boolean(projectId) })
  const { overview, openStage, refresh, chain, stage, selected } = workspace
  const guardChanges = () => canNavigateAway()
  const [inspectorActionContainer, setInspectorActionContainer] = useState<HTMLDivElement | null>(null)
  const [inspectorContainer, setInspectorContainer] = useState<HTMLDivElement | null>(null)
  const [documentOpen, setDocumentOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [relationsOpen, setRelationsOpen] = useState(false)
  const [profileReadingOpen, setProfileReadingOpen] = useState(false)
  const [special, setSpecial] = useState<SpecialKind | null>(null)
  const [sourceSelected, setSourceSelected] = useState<'ui' | 'api' | null>(null)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false)
  const inspectorId = useId()
  const readingOpen = modalOpen || relationsOpen || documentOpen || profileReadingOpen
  useEffect(() => { if (!readingOpen || !inspectorOpen) setInspectorCollapsed(false) }, [readingOpen, inspectorOpen])
  const [uiConfigurationRequestId] = useState(() => randomId())
  const profileWorkspace = useRequirementRepositoryProfileWorkspace(
    requirementId,
    projectId,
    Boolean(requirementId && projectId),
  )
  const uiSourceOptionsEnabled = Boolean(requirementId && projectId) && (sourceSelected === 'ui' || selected?.kind === 'ui')
  const uiSourceOptions = useUiGenerationSourceOptions(requirementId, uiSourceOptionsEnabled)
  const uiSourceOptionsState = {
    data: uiSourceOptions.data,
    loading: uiSourceOptions.isLoading,
    error: uiSourceOptions.error,
    reload: () => { void uiSourceOptions.refetch() },
  }
  useLayoutEffect(() => {
    const isReading = modalOpen || relationsOpen || documentOpen || profileReadingOpen
    if (isReading) setReadingOrigin(stageRef.current, originRef.current)
    if (wasReading.current !== isReading) animateInspectorContents(inspectorRef.current)
    wasReading.current = isReading
  }, [modalOpen, relationsOpen, documentOpen, profileReadingOpen])
  const chains = useMemo(() => overview.data?.chains ?? [], [overview.data?.chains])
  const sourceChain = chains.find(item => item.kind === sourceSelected)
  const showUiSourceSnapshot = inspectorOpen && sourceSelected === 'ui' && Boolean(sourceChain?.runId)
  const uiSourceSnapshot = useUiGenerationSourceSnapshot(requirementId, showUiSourceSnapshot)
  const [initializing, setInitializing] = useState(false)
  const [initializationError, setInitializationError] = useState<unknown>()
  const [initializationAttempt, setInitializationAttempt] = useState(0)
  const initializingRef = useRef(false)
  useEffect(() => {
    if (!canWrite || !overview.data || initializingRef.current) return
    const missing = overview.data.chains.filter(item =>
      !item.configured && (item.kind === 'requirement_analysis' || item.kind === 'function'))
    if (!missing.length) return
    initializingRef.current = true
    setInitializing(true)
    setInitializationError(undefined)
    void (async () => {
      try {
        for (const item of missing) await requirementDesignApi.configure(requirementId, item.kind, { newConfiguration: false })
        const result = await overview.refetch()
        if (result.error) throw result.error
      } catch (error) {
        setInitializationError(error)
      } finally {
        initializingRef.current = false
        setInitializing(false)
      }
    })()
  // The overview data may update during refetch; retries are initiated explicitly.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requirementId, canWrite, Boolean(overview.data), initializationAttempt])
  const visibleChains = laneOrder.map(kind => chains.find(item => item.kind === kind)).filter(Boolean) as GenerationChain[]
  const selectStage = (kind: GenerationChainKind, entry: GenerationChainStage) => {
    if (!guardChanges()) return false
    setInspectorOpen(true)
    setSourceSelected(null)
    setSpecial(null); setDocumentOpen(false); setRelationsOpen(false); setModalOpen(false); setProfileReadingOpen(false)
    if (special || selected?.kind !== kind || selected.stage !== entry.stage) openStage(kind, entry.stage)
    return true
  }
  const openStageContent = (kind: GenerationChainKind, entry: GenerationChainStage, origin?: HTMLElement) => {
    originRef.current = origin
    setReadingOrigin(stageRef.current, origin)
    if (!selectStage(kind, entry)) return
    setModalOpen(true)
  }
  const closeReading = (finish: () => void) => {
    if (exitAnimation.current) return
    setReadingOrigin(stageRef.current, originRef.current)
    exitAnimation.current = animateReadingExit(stageRef.current, () => {
      exitAnimation.current = null
      finish()
      setInspectorOpen(false)
    })
  }
  const closeStageReading = () => { if (guardChanges()) closeReading(() => {
    setModalOpen(false); setRelationsOpen(false); setInspectorOpen(false); refresh()
  }) }
  const closeProfileReading = () => closeReading(() => { setProfileReadingOpen(false); setInspectorOpen(false) })
  // 面包屑点「需求名」一级：退出阅读态，回到生成流程。
  const leaveReading = () => { if (guardChanges()) closeReading(() => {
    setModalOpen(false); setRelationsOpen(false); setDocumentOpen(false); setInspectorOpen(false); refresh()
  }) }
  const leaveReadingRef = useRef<() => void>(() => {})
  useEffect(() => { leaveReadingRef.current = leaveReading })
  const leaveReadingAction = useCallback(() => leaveReadingRef.current(), [])
  // 进入阅读态时把当前产物交给页面标题栏，作为面包屑的最后一级。
  useEffect(() => {
    if (!onReadingNodeChange) return
    if (profileReadingOpen) { onReadingNodeChange({ label: '仓库画像', leave: () => setProfileReadingOpen(false) }); return }
    if (documentOpen) { onReadingNodeChange({ label: '需求文档', leave: leaveReadingAction, kind: 'document' }); return }
    if (relationsOpen) { onReadingNodeChange({ label: '用例图谱', leave: leaveReadingAction, kind: 'relations' }); return }
    if (modalOpen && stage) { onReadingNodeChange({ label: stage.label, leave: leaveReadingAction, kind: 'stage' }); return }
    onReadingNodeChange(null)
  }, [onReadingNodeChange, profileReadingOpen, documentOpen, relationsOpen, modalOpen, stage, leaveReadingAction])
  const selectSpecial = (value: SpecialKind) => {
    if (!guardChanges()) return false
    setInspectorOpen(true)
    setSourceSelected(null)
    setSpecial(value); setDocumentOpen(false); setModalOpen(false); setRelationsOpen(false); setProfileReadingOpen(false)
    return true
  }
  const openSpecial = (value: SpecialKind, origin?: HTMLElement) => {
    originRef.current = origin
    setReadingOrigin(stageRef.current, origin)
    if (!selectSpecial(value)) return
    if (value === 'content') {
      if (documentPreview) setDocumentOpen(true)
      else onOpenTab('content')
    }
    if (value === 'relations') setRelationsOpen(true)
    if (value === 'codeRisk') onOpenTab(value)
    if (value === 'repositoryProfile') setProfileReadingOpen(true)
  }
  // 没有画像时的引导：收起当前生成设置，打开仓库画像阅读区与运行操作。
  const openProfileGuide = () => {
    if (!guardChanges()) return
    setModalOpen(false)
    openSpecial('repositoryProfile')
  }
  const functionChain = chains.find(item => item.kind === 'function')
  const detailedStage = functionChain?.stages.find(item => item.stage === 'detailed_cases')
  const currentCases = useQuery({
    queryKey: ['candidateWorkflow', requirementId, 'function', 'detailed_cases', 'current'],
    queryFn: () => generationCandidatesApi.current(requirementId, 'function', 'detailed_cases'),
    enabled: Boolean(requirementId && functionChain?.candidateMode),
  })
  const candidateRelations = functionChain?.candidateMode && currentCases.data?.candidateId
    ? { requirementId, currentToken: currentCases.data.currentToken }
    : undefined
  const relations = candidateRelations ? { active: inspectorOpen && special === 'relations', onOpen: (origin?: HTMLElement) => openSpecial('relations', origin) } : undefined
  const profileSelectedCandidate = profileWorkspace.selectedProfileView
  const profileModel = profileWorkspace.latestRun
    ? getRunPipelineModel(profileWorkspace.latestRun)
    : undefined
  const profileLatestCandidate = profileWorkspace.latestProfileView
  const profileRunning = profileModel?.statusTone === 'processing'
  const profileCard = useMemo(
    () => ({
      statusLabel: profileRunning
        ? '运行中'
        : profileModel?.statusTone === 'error'
          ? '执行失败'
          : profileWorkspace.profileCandidateMode && profileWorkspace.currentProfile?.candidateId
            ? '已采用'
            : profileWorkspace.profileCandidateMode && profileLatestCandidate
              ? '待采用'
          : profileLatestCandidate
            ? '已生成'
            : '未运行',
      statusClass: profileRunning
        ? 'is-running'
        : profileModel?.statusTone === 'error'
          ? 'is-failed'
          : profileWorkspace.profileCandidateMode && profileLatestCandidate && !profileWorkspace.currentProfile?.candidateId
            ? 'is-muted'
          : profileLatestCandidate
            ? 'is-approved'
            : 'is-empty',
      running: Boolean(profileRunning),
      versionLabel: profileLatestCandidate?.label,
      meta: profileLatestCandidate?.profile
        ? `${profileLatestCandidate.profile.repositories.length} 个仓库`
        : '暂无画像',
    }),
    [profileLatestCandidate, profileModel?.statusTone, profileRunning, profileWorkspace.profileCandidateMode, profileWorkspace.currentProfile?.candidateId],
  )
  if (initializationError) return <div className="gc-panorama flex min-h-0 min-w-0 flex-1 flex-col gap-3.5 overflow-auto p-4"><Alert type="error" showIcon title={`初始化生成流程失败：${getErrorMessage(initializationError)}`} action={<Button onClick={() => setInitializationAttempt(value => value + 1)}>重试</Button>} /></div>
  if (overview.isPending || initializing) return <div className="gc-panorama gc-loading flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center gap-3.5 overflow-auto p-4"><Spin /></div>
  if (overview.error) return <div className="gc-panorama flex min-h-0 min-w-0 flex-1 flex-col gap-3.5 overflow-auto p-4"><Alert type="error" showIcon title={getErrorMessage(overview.error)} action={<Button onClick={refresh}>重试读取</Button>} /></div>
  const activeStage = special || sourceSelected ? undefined : stage
  const activeChain = sourceSelected ? sourceChain : special === 'relations' ? functionChain : special ? undefined : chain
  const profileMaterialLabel = profileWorkspace.profileCandidateMode && profileSelectedCandidate
    ? '已冻结，采用时核对'
    : profileSelectedCandidate ? '未记录'
      : profileWorkspace.currentMaterialAvailable ? '当前已采用' : '未选择'
  const stageRunning = activeStage?.state === 'running'
  const details = special === 'repositoryProfile'
    ? `画像 ${profileSelectedCandidate?.label ?? '未选择'} · 材料整理 ${profileMaterialLabel} · ${profileWorkspace.bindings.length} 个仓库`
    : stageRunning ? '' : activeStage?.blockedReason ?? ''
  const inspectorSelection = sourceSelected ? `${sourceSelected}-source` : special ?? `${selected?.kind}:${selected?.stage}`
  return <div className="gc-panorama gc-canvas-panorama flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-hidden p-0">
    {workspace.personalLlm.dialog}
    <div className="gc-canvas-workspace flex min-h-0 min-w-0 flex-1 gap-3 max-[900.01px]:flex-col max-[900.01px]:overflow-auto"><div ref={stageRef} className={`gc-canvas-stage relative flex min-h-0 min-w-0 flex-1 max-[900.01px]:h-[min(60vh,600px)] max-[900.01px]:min-h-[380px] max-[900.01px]:flex-none${modalOpen || relationsOpen || documentOpen || profileReadingOpen ? ' is-reading' : ''}`}><div className="gc-canvas-map flex min-h-0 min-w-0 flex-1" inert={modalOpen || relationsOpen || documentOpen || profileReadingOpen}><RequirementGenerationCanvas canWrite={canWrite} chains={visibleChains} selected={inspectorOpen && !sourceSelected ? selected : undefined} special={inspectorOpen ? special : null} profile={profileCard} relations={relations}
      sourceSelected={inspectorOpen ? sourceSelected : null} onSelectSource={kind => { if (!guardChanges()) return; setInspectorOpen(true); setSourceSelected(kind); setSpecial(null); setModalOpen(false); setDocumentOpen(false); setRelationsOpen(false) }}
      onOpenStage={openStageContent} onOpenSpecial={openSpecial} onOpenTab={tab => { if (guardChanges()) onOpenTab(tab) }} /></div>      <GenerationArtifactFrame hideHeader open={documentOpen} title="需求文档" onCancel={() => closeReading(() => setDocumentOpen(false))}
        className="generation-chain-document">{documentPreview}</GenerationArtifactFrame>
      <GenerationChainModal inspectorContainer={inspectorContainer} inspectorActionContainer={inspectorActionContainer} workspace={workspace} requirementId={requirementId} projectId={projectId} open={modalOpen}
        uiSourceOptions={uiSourceOptionsState} onOpenProfile={openProfileGuide}
        chooseGitlab={profileWorkspace.personalGitlab.choose} gitlabDialog={profileWorkspace.personalGitlab.dialog}
        onClose={closeStageReading} onOpenLegacy={onOpenTab} />
      <GenerationArtifactFrame hideHeader open={profileReadingOpen} title="仓库画像" onCancel={closeProfileReading}
        className="generation-chain-modal generation-profile-reading">
        <RequirementRepositoryProfileReading workspace={profileWorkspace} />
      </GenerationArtifactFrame>
      {candidateRelations ? <FunctionalCaseRelationsModal inspectorContainer={inspectorContainer} inspectorActionContainer={inspectorActionContainer} open={relationsOpen} onClose={() => closeReading(() => setRelationsOpen(false))}
        projectId={projectId} disabled={detailedStage?.state === 'running'}
        chooseConnection={workspace.personalLlm.choose} candidate={candidateRelations} /> : null}
    </div>{inspectorOpen ? <InspectorPortal host={inspectorHost}><div className={`gc-inspector-drawer${inspectorCollapsed ? ' is-collapsed' : ''}`}>
      <div className="gc-inspector-rail" aria-hidden="true"><FileTextOutlined /><HistoryOutlined /><EllipsisOutlined /></div>
      {readingOpen ? <button type="button" className="gc-inspector-toggle" aria-controls={inspectorId} aria-expanded={!inspectorCollapsed} aria-label={inspectorCollapsed ? '展开阶段详情' : '收起阶段详情'} title={inspectorCollapsed ? '展开阶段详情' : '收起阶段详情'} onClick={() => setInspectorCollapsed(value => !value)}>{inspectorCollapsed ? <LeftOutlined aria-hidden /> : <RightOutlined aria-hidden />}</button> : null}
      <aside id={inspectorId} ref={inspectorRef} className="gc-inspector flex h-full w-[304px] min-w-0 min-h-0 flex-col overflow-hidden rounded-[12px] border border-[var(--app-surface-border)] bg-[var(--app-surface)] max-[900.01px]:w-full max-[900.01px]:min-h-[220px]" aria-label="阶段详情" inert={inspectorCollapsed} aria-hidden={inspectorCollapsed || undefined}>
      {special || selected || sourceSelected ? <><div className="gc-inspector-header flex flex-none items-center justify-between gap-2 border-b border-[var(--app-surface-divider)] bg-[var(--app-list-toolbar-bg)] px-4 py-3" key={inspectorSelection}>
        <h2 className="min-w-0 flex-1 truncate">{sourceSelected ? sourceChain?.label : special === 'content' ? '需求文档' : special === 'codeRisk' ? '代码风险分析' : special === 'repositoryProfile' ? '仓库画像' : special === 'relations' ? '用例图谱' : activeStage?.label ?? '阶段详情'}</h2>
        {!modalOpen && !relationsOpen && !documentOpen && !profileReadingOpen ? <Button type="text" size="small" icon={<CloseOutlined />} aria-label="关闭阶段详情" onClick={() => { if (guardChanges()) { setInspectorOpen(false); workspace.clearStage() } }} /> : null}
      </div>
        <div className="gc-inspector-content min-h-0 flex-1 overflow-auto px-4 pt-4 pb-4 [&>.gc-inspector-section]:mt-4 [&>.gc-inspector-section]:flex [&>.gc-inspector-section]:flex-col [&>.gc-inspector-section]:gap-2.5 [&>.gc-inspector-section]:border-t [&>.gc-inspector-section]:border-[var(--app-surface-divider)] [&>.gc-inspector-section]:pt-4 [&>.gc-inspector-section:first-child]:border-t-0 [&>.gc-inspector-section:first-child]:pt-0 [&>.gc-inspector-section_h3]:m-0 [&>.gc-inspector-section_h3]:text-[12px] [&>.gc-inspector-section_h3]:font-semibold">
          {sourceSelected === 'ui' ? <UiGenerationSourcePanel key={requirementId} projectId={projectId}
            sourceOptions={uiSourceOptionsState} canWrite={canWrite}
            busy={Boolean(sourceChain?.busy || sourceChain?.stages.some(item => item.state === 'running'))}
            existingSource={showUiSourceSnapshot ? uiSourceSnapshot.data : undefined}
            snapshotLoading={showUiSourceSnapshot && uiSourceSnapshot.isPending}
            onOpenCandidate={() => { void (async () => {
              try {
                if (!sourceChain?.configured) {
                  await requirementDesignApi.configure(requirementId, 'ui', {
                    requestId: uiConfigurationRequestId, newConfiguration: false,
                  })
                }
                const result = await overview.refetch()
                if (result.error) throw result.error
                const uiChain = result.data?.chains.find(item => item.kind === 'ui')
                const entry = uiChain?.stages.find(item => item.stage === 'ui_surface')
                if (!uiChain?.candidateMode || !entry) throw new Error('UI 候选工作区尚未就绪，请刷新后重试')
                openStageContent('ui', entry)
              } catch (error) {
                message.error(getErrorMessage(error))
              }
            })() }}
            onOpenProfile={openProfileGuide} /> : null}
          {sourceSelected === 'api' ? <ApiGenerationSourcePanel key={sourceChain?.taskId ?? 'new-api-source'} requirementId={requirementId} projectId={projectId} taskId={sourceChain?.taskId} canWrite={canWrite}
            busy={Boolean(sourceChain?.busy || sourceChain?.stages.some(item => item.state === 'running'))}
            profileCandidate={profileLatestCandidate} profileLoading={profileWorkspace.candidateViewsLoading} onOpenProfile={openProfileGuide} onSaved={refresh} /> : null}
          {activeChain?.kind === 'api' && activeStage?.blockedReason ? <section className="gc-inspector-section">
            <Alert showIcon type="info" title={activeStage.blockedReason} />
          </section> : null}
          {workspace.detail.error && !special && !sourceSelected ? <Alert type="error" showIcon title={getErrorMessage(workspace.detail.error)} action={<Button onClick={() => void workspace.detail.refetch()}>重试</Button>} /> : null}
          {!special && !sourceSelected && workspace.detail.isPending && !activeStage ? <Spin /> : <>{special !== 'repositoryProfile' && !activeStage && !sourceSelected ? <div className="gc-inspector-summary mb-3.5 text-[12px] leading-[1.6] text-[var(--app-surface-text-muted)] [overflow-wrap:anywhere] [&_dl]:m-0 [&_dl]:mt-3 [&_dl]:border-t [&_dl]:border-[var(--app-surface-divider)] [&_dl_div]:flex [&_dl_div]:justify-between [&_dl_div]:gap-2.5 [&_dl_div]:pt-2 [&_dd]:m-0 [&_dd]:text-right [&_dd]:text-[var(--app-surface-text)] [&_dt]:text-[var(--app-surface-text-muted)]" key={inspectorSelection}><span>{special === 'content' ? '生成链读取这里的最新正文。单击卡片打开需求文档。' : special === 'codeRisk' ? '独立运行并查看分析报告' : special === 'relations' ? '由「完整用例」派生的用例关联图，不单独采用。' : details}</span>{special === 'relations' ? <dl><div><dt>所属阶段</dt><dd>{functionChain?.label ?? '功能测试'}</dd></div><div><dt>来源</dt><dd>当前采用的完整用例</dd></div></dl> : null}</div> : null}
            {special === 'repositoryProfile' ? <RequirementRepositoryProfileInspector workspace={profileWorkspace} showRun={profileReadingOpen} /> : null}
            {activeStage && activeChain?.candidateMode && !modalOpen ? <section className="gc-inspector-section">
              <h3>候选与当前内容</h3>
              <p>可比较多份候选、选择试生成来源，并采用任意基于有效冻结来源的结果。</p>
              <Button onClick={() => openStageContent(activeChain.kind, activeStage)}>打开候选工作区</Button>
            </section> : null}
            {activeStage?.state === 'failed' ? <section className="gc-inspector-section" key={`${inspectorSelection}:failure`}><h3>失败详情</h3><Alert showIcon type="error" style={{ whiteSpace: 'pre-line' }} title={activeStage.errorMessage || '阶段执行失败，Worker 未返回具体原因'} /><p className="gc-failure-meta m-0 text-[11px] leading-[1.6] text-[var(--app-surface-text-muted)] [overflow-wrap:anywhere]">{generationFailureMeta(activeStage) || '请重新执行；若持续失败，请查看 Worker 日志。'}</p></section> : null}
</>}
          <div ref={setInspectorContainer} />
        </div><div className="gc-inspector-footer max-h-[60%] flex-none overflow-auto empty:hidden" ref={setInspectorActionContainer} /></> : <Empty description="选择一个阶段查看详情" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
    </aside></div></InspectorPortal> : null}</div>
    {!chains.length ? <Empty description="暂无生成链" /> : null}

  </div>
}
