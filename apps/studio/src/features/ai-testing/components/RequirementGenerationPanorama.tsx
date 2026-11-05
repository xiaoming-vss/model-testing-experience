import { ArrowLeftOutlined, CloseOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Spin, Typography } from 'antd'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { getErrorMessage } from '@/utils/format'
import { requirementDesignApi } from '../api/requirementDesign.api'
import { useRequirementGenerationChain } from '../hooks/useRequirementGenerationChain'
import type { GenerationChain, GenerationChainKind, GenerationChainStage, UiGenerationSourceInputs } from '../api/generationChain.api'
import { GenerationArtifactFrame } from './GenerationArtifactFrame'
import { GenerationChainModal } from './GenerationChainModal'
import { UiGenerationSourceTrace } from './UiGenerationSourceTrace'
import { UiGenerationSourcePanel } from './UiGenerationSourcePanel'
import { ApiGenerationSourcePanel } from './ApiGenerationSourcePanel'
import { FunctionalCaseRelationsModal } from './FunctionalCaseRelationsModal'
import { RequirementGenerationCanvas } from './RequirementGenerationCanvas'
import { animateInspectorContents, animateReadingExit, setReadingOrigin } from './readingTransition'
import { generationStageLabel, generationStageClass, generationFailureMeta } from '../utils/generationStageDisplay'
import '../styles/requirement-generation-chain.css'
import '../styles/requirement-generation-canvas.css'

const laneOrder: GenerationChainKind[] = ['requirement_analysis', 'function', 'api', 'ui']
/** 侧栏追溯：显示当前待审核产物或所选版本实际引用的上游版本。 */
function UpstreamTrace({ stage, chain, upstreamStages, versionKey, upstream, versionUpstreams, source, loading }: {
  stage: GenerationChainStage
  upstreamStages: GenerationChainStage[]
  chain: GenerationChain
  versionKey: string
  upstream: Record<string, string>
  versionUpstreams?: Record<string, string>
  source?: UiGenerationSourceInputs | null
  loading?: boolean
}) {
  return <section className="gc-inspector-section"><h3>上游追溯</h3><div className="gc-inspector-trace">
    {stage.upstreamStages.length ? stage.upstreamStages.map(name => {
      const upstreamStage = upstreamStages.find(item => item.stage === name)
      const selectedId = versionKey === 'draft' || !versionKey ? upstream[name] : versionUpstreams?.[name]
      const version = upstreamStage?.versions.find(item => item.versionId === selectedId)
      if (versionKey && versionKey !== 'draft' && !version) return null
      const missing = Boolean(selectedId) && !version
      return <span className={`gc-trace-chip${missing ? ' is-danger' : ''}`} key={name}>
        {upstreamStage?.label ?? name}<b>{version?.label ?? (missing ? '上游已删除' : '未选择')}</b>
      </span>
    }) : chain.kind !== 'ui' ? <span className="gc-trace-chip">{chain.kind === 'api' ? 'OpenAPI 文档' : '需求材料'}<b>只读来源</b></span> : null}
    {chain.kind === 'ui' ? <UiGenerationSourceTrace source={source} loading={loading} /> : null}
  </div></section>
}
type SpecialKind = 'content' | 'codeRisk' | 'relations'
/** 阅读态交给页面标题栏的面包屑末项；leave 用于点上级需求名时退回生成流程。 */
export type RequirementReadingNode = { label: string; status?: string; tone?: string; leave?: () => void }
export function RequirementGenerationPanorama({ requirementId, projectId, canWrite, onOpenTab, documentPreview, onReadingNodeChange }: {
  canWrite: boolean
  documentPreview?: ReactNode
  requirementId: string; projectId: string
  onOpenTab: (tab: 'content' | GenerationChainKind | 'codeRisk') => void
  onReadingNodeChange?: (node: RequirementReadingNode | null) => void
}) {
  const stageRef = useRef<HTMLDivElement>(null)
  const inspectorRef = useRef<HTMLElement>(null)
  const wasReading = useRef(false)
  const originRef = useRef<HTMLElement | undefined>(undefined)
  const exitAnimation = useRef<Animation | null>(null)
  useEffect(() => () => { exitAnimation.current?.cancel() }, [])
  const workspace = useRequirementGenerationChain({ requirementId, projectId, enabled: Boolean(projectId) })
  const { overview, filter, openStage, refresh, chain, stage, selected, versionOptions, versionKey } = workspace
  const [inspectorActionContainer, setInspectorActionContainer] = useState<HTMLDivElement | null>(null)
  const [inspectorContainer, setInspectorContainer] = useState<HTMLDivElement | null>(null)
  const [documentOpen, setDocumentOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [relationsOpen, setRelationsOpen] = useState(false)
  const [special, setSpecial] = useState<SpecialKind | null>(null)
  const [sourceSelected, setSourceSelected] = useState<'ui' | 'api' | null>(null)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  useLayoutEffect(() => {
    const isReading = modalOpen || relationsOpen || documentOpen
    if (isReading) setReadingOrigin(stageRef.current, originRef.current)
    if (wasReading.current !== isReading) animateInspectorContents(inspectorRef.current)
    wasReading.current = isReading
  }, [modalOpen, relationsOpen, documentOpen])
  const chains = useMemo(() => overview.data?.chains ?? [], [overview.data?.chains])
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
    if (!workspace.guardUnsaved()) return false
    setInspectorOpen(true)
    setSourceSelected(null)
    setSpecial(null); setDocumentOpen(false); setRelationsOpen(false); setModalOpen(false)
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
    })
  }
  const closeStageReading = () => { if (workspace.guardUnsaved()) closeReading(() => {
    setModalOpen(false); setRelationsOpen(false); workspace.setRevisionOpen(false); refresh()
  }) }
  // 面包屑点「需求名」一级：退出阅读态，回到生成流程。
  const leaveReading = () => { if (workspace.guardUnsaved()) closeReading(() => {
    setModalOpen(false); setRelationsOpen(false); setDocumentOpen(false); workspace.setRevisionOpen(false); refresh()
  }) }
  const leaveReadingRef = useRef<() => void>(() => {})
  useEffect(() => { leaveReadingRef.current = leaveReading })
  const leaveReadingAction = useCallback(() => leaveReadingRef.current(), [])
  // 进入阅读态时把当前产物交给页面标题栏，作为面包屑的最后一级。
  useEffect(() => {
    if (!onReadingNodeChange) return
    if (documentOpen) { onReadingNodeChange({ label: '需求文档', status: '只读来源', tone: 'is-muted', leave: leaveReadingAction }); return }
    if (relationsOpen) { onReadingNodeChange({ label: '用例图谱', status: '派生', tone: 'is-muted', leave: leaveReadingAction }); return }
    if (modalOpen && stage) { onReadingNodeChange({ label: stage.label, status: generationStageLabel(stage), tone: generationStageClass(stage), leave: leaveReadingAction }); return }
    onReadingNodeChange(null)
  }, [onReadingNodeChange, documentOpen, relationsOpen, modalOpen, stage, leaveReadingAction])
  const selectSpecial = (value: SpecialKind) => {
    if (!workspace.guardUnsaved()) return false
    setInspectorOpen(true)
    setSourceSelected(null)
    setSpecial(value); setDocumentOpen(false); setModalOpen(false); setRelationsOpen(false); workspace.setRevisionOpen(false)
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
  }
  const functionChain = chains.find(item => item.kind === 'function')
  const detailedStage = functionChain?.stages.find(item => item.stage === 'detailed_cases')
  const detailedDraft = detailedStage?.draft && !detailedStage.draft.invalidated ? detailedStage.draft : undefined
  // 用例图谱挂在「完整用例」的运行上：有待审核产物时跟随该次运行，否则跟随最新已通过版本。
  const relationsRunId = functionChain?.configured
    ? detailedDraft?.runId ?? detailedStage?.latestVersion?.sourceRunId
    : undefined
  const relations = relationsRunId ? { active: inspectorOpen && special === 'relations', onSelect: () => selectSpecial('relations'), onOpen: (origin?: HTMLElement) => openSpecial('relations', origin) } : undefined
  if (initializationError) return <div className="gc-panorama"><Alert type="error" showIcon title={`初始化生成流程失败：${getErrorMessage(initializationError)}`} action={<Button onClick={() => setInitializationAttempt(value => value + 1)}>重试</Button>} /></div>
  if (overview.isPending || initializing) return <div className="gc-panorama gc-loading"><Spin /></div>
  if (overview.error) return <div className="gc-panorama"><Alert type="error" showIcon title={getErrorMessage(overview.error)} action={<Button onClick={refresh}>重试读取</Button>} /></div>
  const sourceChain = chains.find(item => item.kind === sourceSelected)
  const activeStage = special || sourceSelected ? undefined : stage
  const activeChain = sourceSelected ? sourceChain : special === 'relations' ? functionChain : special ? undefined : chain
  const status = activeStage ? generationStageLabel(activeStage) : special === 'content' ? '只读来源' : special === 'codeRisk' ? '独立分析' : special === 'relations' ? '派生' : ''
  const details = (versionKey === 'draft' ? activeStage?.draft?.summary : workspace.selectedVersion?.summary) ?? activeStage?.latestVersion?.summary ?? activeStage?.blockedReason ?? '暂无产物'
  const runId = special === 'relations' ? relationsRunId : !activeStage ? undefined : versionKey === 'draft' ? activeStage.draft?.runId : workspace.selectedVersion?.sourceRunId ?? (!versionKey ? activeStage.activeRunId : undefined)
  const inspectorSelection = sourceSelected ? `${sourceSelected}-source` : special ?? `${selected?.kind}:${selected?.stage}`
  return <div className="gc-panorama gc-canvas-panorama">
    {workspace.personalLlm.dialog}
    <div className="gc-canvas-workspace"><div ref={stageRef} className={`gc-canvas-stage${modalOpen || relationsOpen || documentOpen ? ' is-reading' : ''}`}><div className="gc-canvas-map" inert={modalOpen || relationsOpen || documentOpen}><RequirementGenerationCanvas canWrite={canWrite} chains={visibleChains} filter={filter} selected={inspectorOpen && !sourceSelected ? selected : undefined} special={inspectorOpen ? special : null} relations={relations}
      sourceSelected={inspectorOpen ? sourceSelected : null} onSelectSource={kind => { if (!workspace.guardUnsaved()) return; setInspectorOpen(true); setSourceSelected(kind); setSpecial(null); setModalOpen(false); setDocumentOpen(false); setRelationsOpen(false); workspace.setRevisionOpen(false) }}
      onSelectStage={selectStage} onOpenStage={openStageContent} onSelectSpecial={selectSpecial} onOpenSpecial={openSpecial} onOpenTab={tab => { if (workspace.guardUnsaved()) onOpenTab(tab) }} /></div>
      <GenerationArtifactFrame embedded open={documentOpen} title="需求文档" onCancel={() => closeReading(() => setDocumentOpen(false))}
        className="generation-chain-document">{documentPreview}</GenerationArtifactFrame>
      <GenerationChainModal embedded showApiRunInInspector={inspectorOpen && !sourceSelected && !special && !documentOpen && !relationsOpen} inspectorContainer={inspectorContainer} inspectorActionContainer={inspectorActionContainer} workspace={workspace} requirementId={requirementId} projectId={projectId} open={modalOpen}
        onClose={closeStageReading} onOpenLegacy={onOpenTab} />
      <FunctionalCaseRelationsModal embedded inspectorContainer={inspectorContainer} inspectorActionContainer={inspectorActionContainer} open={relationsOpen} onClose={() => closeReading(() => setRelationsOpen(false))}
        taskId={functionChain?.taskId ?? ''} runId={relationsRunId} disabled={detailedStage?.state === 'running'}
        chooseConnection={workspace.personalLlm.choose} />
    </div>{inspectorOpen ? <aside ref={inspectorRef} className="gc-inspector" aria-label="阶段详情">
      {special || selected || sourceSelected ? <><div className="gc-inspector-header" key={inspectorSelection}>
        {modalOpen || relationsOpen ? <Button className="gc-inspector-back" type="text" size="small" icon={<ArrowLeftOutlined aria-hidden />} onClick={closeStageReading}>返回流程</Button> : null}
        <div className="gc-inspector-heading"><h2>{sourceSelected ? sourceChain?.label : special === 'content' ? '需求文档' : special === 'codeRisk' ? '代码风险分析' : special === 'relations' ? '用例图谱' : activeStage?.label ?? '阶段详情'}</h2>{status ? <span className={`gc-state ${activeStage ? generationStageClass(activeStage) : 'is-muted'}`}>{status}</span> : null}{!modalOpen && !relationsOpen && !documentOpen ? <Button type="text" size="small" icon={<CloseOutlined />} aria-label="关闭阶段详情" onClick={() => { if (workspace.guardUnsaved()) { setInspectorOpen(false); workspace.clearStage() } }} /> : null}</div>
        <p>{activeChain?.label ?? (special === 'content' ? '需求材料' : special === 'codeRisk' ? '代码风险' : '正在读取阶段信息')}{activeStage && !(activeChain?.kind === 'api' && details === activeStage.blockedReason) ? <span className="gc-inspector-stage-summary">{details}</span> : null}</p>
        {runId ? <div className="gc-inspector-run-meta"><span>运行 ID</span><Typography.Text className="gc-inspector-run-id" title={runId} copyable={{ text: runId, tooltips: ['复制运行 ID', '已复制'] }}>{runId.length > 20 ? `${runId.slice(0, 8)}…${runId.slice(-4)}` : runId}</Typography.Text></div> : null}
      </div>
        <div className="gc-inspector-content">
          {sourceSelected === 'ui' ? <UiGenerationSourcePanel key={sourceChain?.taskId ?? 'new-ui-source'} requirementId={requirementId} taskId={sourceChain?.taskId} canWrite={canWrite}
            busy={Boolean(sourceChain?.busy || sourceChain?.stages.some(item => item.state === 'running'))} onSaved={refresh} /> : null}
          {sourceSelected === 'api' ? <ApiGenerationSourcePanel key={sourceChain?.taskId ?? 'new-api-source'} requirementId={requirementId} taskId={sourceChain?.taskId} canWrite={canWrite}
            busy={Boolean(sourceChain?.busy || sourceChain?.stages.some(item => item.state === 'running'))} onSaved={refresh} /> : null}
          {activeChain?.kind === 'api' && activeStage ? <section className="gc-inspector-section">
            <h3>生成流程</h3><p>{activeStage.stage === 'openapi_extract' ? '提取 OpenAPI 接口配置，审核通过后可用于生成 API 用例。' : '使用已审核的接口配置生成 API 用例 YAML。'}</p>
            {activeStage.blockedReason ? <Alert showIcon type="info" title={activeStage.blockedReason} /> : null}
          </section> : null}
          {workspace.detail.error && !special && !sourceSelected ? <Alert type="error" showIcon title={getErrorMessage(workspace.detail.error)} action={<Button onClick={() => void workspace.detail.refetch()}>重试</Button>} /> : null}
          {!special && !sourceSelected && workspace.detail.isPending && !activeStage ? <Spin /> : <>{!activeStage && !sourceSelected ? <div className="gc-inspector-summary" key={inspectorSelection}><span>{special === 'content' ? '生成链读取这里的最新正文。双击卡片打开需求文档。' : special === 'codeRisk' ? '独立运行并查看分析报告' : special === 'relations' ? '由「完整用例」派生的用例关联图，不单独审核。' : details}</span>{special === 'relations' ? <dl><div><dt>所属阶段</dt><dd>{functionChain?.label ?? '功能测试'}</dd></div><div><dt>来源</dt><dd>{detailedDraft ? '待审核产物' : detailedStage?.latestVersion?.label ?? '完整用例'}</dd></div></dl> : null}</div> : null}
            {activeStage && activeChain ? <><section className="gc-inspector-section" key={`${inspectorSelection}:versions`}><h3>版本选择</h3><div className="gc-inspector-versions" role="group" aria-label="侧栏选择版本">{versionOptions.length ? versionOptions.map(option => <button type="button" key={option.key} className={`gc-version-button${versionKey === option.key ? ' is-active' : ''}`} aria-pressed={versionKey === option.key} onClick={() => { workspace.setVersionKey(option.key); workspace.setDiffOpen(false) }}>{option.label}</button>) : <span>暂无版本</span>}</div></section><UpstreamTrace key={`${inspectorSelection}:trace`} stage={activeStage} chain={activeChain} upstreamStages={workspace.upstreamStages} versionKey={versionKey} upstream={workspace.upstream} versionUpstreams={workspace.versionDetail.data?.upstreamVersions}
              source={versionKey === 'draft' ? activeStage.draft?.sourceInputs : workspace.selectedVersion ? workspace.versionDetail.data?.sourceInputs : activeChain.sourceInputs}
              loading={Boolean(workspace.selectedVersion && workspace.versionDetail.isFetching)} />
              {activeStage.state === 'failed' ? <section className="gc-inspector-section" key={`${inspectorSelection}:failure`}><h3>失败详情</h3><Alert showIcon type="error" title={activeStage.errorMessage || '阶段执行失败，Worker 未返回具体原因'} /><p className="gc-failure-meta">{generationFailureMeta(activeStage) || '请重新执行；若持续失败，请查看 Worker 日志。'}</p></section> : null}
            </> : null}
</>}
          <div ref={setInspectorContainer} />
        </div><div className="gc-inspector-footer" ref={setInspectorActionContainer} /></> : <Empty description="选择一个阶段查看详情" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
    </aside> : null}</div>
    {!chains.length ? <Empty description="暂无生成链" /> : null}

  </div>
}
