import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Spin } from 'antd'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { getErrorMessage } from '@/utils/format'
import { useRequirementGenerationChain } from '../hooks/useRequirementGenerationChain'
import type { GenerationChain, GenerationChainKind, GenerationChainStage, UiGenerationSourceInputs } from '../api/generationChain.api'
import { GenerationArtifactFrame } from './GenerationArtifactFrame'
import { GenerationChainModal } from './GenerationChainModal'
import { UiGenerationSourceTrace } from './UiGenerationSourceTrace'
import { UiGenerationSourcePanel } from './UiGenerationSourcePanel'
import { FunctionalCaseRelationsModal } from './FunctionalCaseRelationsModal'
import { RequirementGenerationCanvas } from './RequirementGenerationCanvas'
import { generationStageLabel, generationStageClass } from '../utils/generationStageDisplay'
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
      const missing = Boolean(selectedId) && !version
      return <span className={`gc-trace-chip${missing ? ' is-danger' : ''}`} key={name}>
        {upstreamStage?.label ?? name}<b>{version?.label ?? (missing ? '上游已删除' : '未选择')}</b>
      </span>
    }) : chain.kind !== 'ui' ? <span className="gc-trace-chip">需求材料<b>只读来源</b></span> : null}
    {chain.kind === 'ui' ? <UiGenerationSourceTrace source={source} loading={loading} /> : null}
  </div></section>
}
type SpecialKind = 'content' | 'codeRisk' | 'relations'
export function RequirementGenerationPanorama({ requirementId, projectId, canWrite, onOpenTab, documentPreview }: {
  canWrite: boolean
  documentPreview?: ReactNode
  requirementId: string; projectId: string
  onOpenTab: (tab: 'content' | GenerationChainKind | 'codeRisk') => void
}) {
  const workspace = useRequirementGenerationChain({ requirementId, projectId, enabled: Boolean(projectId) })
  const { overview, filter, openStage, refresh, chain, stage, selected, versionOptions, versionKey } = workspace
  const [inspectorActionContainer, setInspectorActionContainer] = useState<HTMLDivElement | null>(null)
  const [inspectorContainer, setInspectorContainer] = useState<HTMLDivElement | null>(null)
  const [documentOpen, setDocumentOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [relationsOpen, setRelationsOpen] = useState(false)
  const [special, setSpecial] = useState<SpecialKind | null>(null)
  const [uiSourceSelected, setUiSourceSelected] = useState(false)
  const chains = useMemo(() => overview.data?.chains ?? [], [overview.data?.chains])
  const visibleChains = laneOrder.map(kind => chains.find(item => item.kind === kind)).filter(Boolean) as GenerationChain[]
  useEffect(() => {
    if (selected || special || !chains.length) return
    const candidate = chains.flatMap(item => item.configured ? item.stages.map(entry => ({ kind: item.kind, stage: entry })) : []).find(item => item.stage.draft && !item.stage.draft.invalidated)
      ?? chains.flatMap(item => item.configured ? item.stages.map(entry => ({ kind: item.kind, stage: entry })) : [])[0]
    if (candidate) openStage(candidate.kind, candidate.stage.stage)
  }, [chains, selected, special, openStage])
  const selectStage = (kind: GenerationChainKind, entry: GenerationChainStage) => {
    setUiSourceSelected(false)
    setSpecial(null); setDocumentOpen(false); setRelationsOpen(false); setModalOpen(false)
    if (special || selected?.kind !== kind || selected.stage !== entry.stage) openStage(kind, entry.stage)
  }
  const openStageContent = (kind: GenerationChainKind, entry: GenerationChainStage) => { selectStage(kind, entry); setModalOpen(true) }
  const selectSpecial = (value: SpecialKind) => {
    setUiSourceSelected(false)
    setSpecial(value); setDocumentOpen(false); setModalOpen(false); setRelationsOpen(false); workspace.setRevisionOpen(false)
  }
  const openSpecial = (value: SpecialKind) => {
    selectSpecial(value)
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
  const relations = relationsRunId ? { active: special === 'relations', onSelect: () => selectSpecial('relations'), onOpen: () => openSpecial('relations') } : undefined
  if (overview.isPending) return <div className="gc-panorama gc-loading"><Spin /></div>
  if (overview.error) return <div className="gc-panorama"><Alert type="error" showIcon title={getErrorMessage(overview.error)} action={<Button onClick={refresh}>重试读取</Button>} /></div>
  const uiChain = chains.find(item => item.kind === 'ui')
  const activeStage = special || uiSourceSelected ? undefined : stage
  const activeChain = uiSourceSelected ? uiChain : special === 'relations' ? functionChain : special ? undefined : chain
  const status = activeStage ? generationStageLabel(activeStage) : special === 'content' ? '只读来源' : special === 'codeRisk' ? '独立分析' : special === 'relations' ? '派生' : ''
  const details = (versionKey === 'draft' ? activeStage?.draft?.summary : workspace.selectedVersion?.summary) ?? activeStage?.latestVersion?.summary ?? activeStage?.blockedReason ?? '暂无产物'
  return <div className="gc-panorama gc-canvas-panorama">
    {workspace.personalLlm.dialog}
    <div className="gc-canvas-workspace"><div className={`gc-canvas-stage${modalOpen || relationsOpen || documentOpen ? ' is-reading' : ''}`}><div className="gc-canvas-map" inert={modalOpen || relationsOpen || documentOpen}><RequirementGenerationCanvas chains={visibleChains} filter={filter} selected={uiSourceSelected ? undefined : selected} special={special} relations={relations}
      uiSourceSelected={uiSourceSelected} onSelectUiSource={() => { setUiSourceSelected(true); setSpecial(null); setModalOpen(false); setDocumentOpen(false); setRelationsOpen(false); workspace.setRevisionOpen(false) }}
      onSelectStage={selectStage} onOpenStage={openStageContent} onSelectSpecial={selectSpecial} onOpenSpecial={openSpecial} onOpenTab={onOpenTab} /></div>
      <GenerationArtifactFrame embedded open={documentOpen} title="需求文档" onCancel={() => setDocumentOpen(false)}
        className="generation-chain-document">{documentPreview}</GenerationArtifactFrame>
      <GenerationChainModal embedded inspectorContainer={inspectorContainer} inspectorActionContainer={inspectorActionContainer} workspace={workspace} requirementId={requirementId} projectId={projectId} open={modalOpen}
        onClose={() => { setModalOpen(false); setRelationsOpen(false); workspace.setRevisionOpen(false); refresh() }} onOpenLegacy={onOpenTab} />
      <FunctionalCaseRelationsModal embedded inspectorContainer={inspectorContainer} inspectorActionContainer={inspectorActionContainer} open={relationsOpen} onClose={() => setRelationsOpen(false)}
        taskId={functionChain?.taskId ?? ''} runId={relationsRunId} disabled={detailedStage?.state === 'running'}
        chooseConnection={workspace.personalLlm.choose} />
    </div><aside className="gc-inspector" aria-label="阶段详情">
      {special || selected || uiSourceSelected ? <><div className="gc-inspector-header">
        {modalOpen || relationsOpen ? <Button className="gc-inspector-back" type="text" size="small" icon={<ArrowLeftOutlined aria-hidden />} onClick={() => { setModalOpen(false); setRelationsOpen(false); workspace.setRevisionOpen(false); refresh() }}>返回流程</Button> : null}
        <div className="gc-inspector-heading"><h2>{uiSourceSelected ? 'UI 测试' : special === 'content' ? '需求文档' : special === 'codeRisk' ? '代码风险分析' : special === 'relations' ? '用例图谱' : activeStage?.label ?? '阶段详情'}</h2>{status ? <span className={`gc-state ${activeStage ? generationStageClass(activeStage) : 'is-muted'}`}>{status}</span> : null}</div>
        <p>{activeChain?.label ?? (special === 'content' ? '需求材料' : special === 'codeRisk' ? '代码风险' : '正在读取阶段信息')}{activeStage ? <span className="gc-inspector-stage-summary">{details}</span> : null}</p>
      </div>
        <div className="gc-inspector-content">
          {uiSourceSelected ? <UiGenerationSourcePanel key={uiChain?.taskId ?? 'new-ui-source'} requirementId={requirementId} taskId={uiChain?.taskId} canWrite={canWrite}
            busy={Boolean(uiChain?.busy || uiChain?.stages.some(item => item.state === 'running'))} onSaved={refresh} /> : null}
          {workspace.detail.error && !special && !uiSourceSelected ? <Alert type="error" showIcon title={getErrorMessage(workspace.detail.error)} action={<Button onClick={() => void workspace.detail.refetch()}>重试</Button>} /> : null}
          {!special && !uiSourceSelected && workspace.detail.isPending && !activeStage ? <Spin /> : <>{!activeStage && !uiSourceSelected ? <div className="gc-inspector-summary"><span>{special === 'content' ? '生成链读取这里的最新正文。双击卡片打开需求文档。' : special === 'codeRisk' ? '独立运行并查看分析报告' : special === 'relations' ? '由「完整用例」派生的用例关联图，不单独审核。' : details}</span>{special === 'relations' ? <dl><div><dt>所属阶段</dt><dd>{functionChain?.label ?? '功能测试'}</dd></div><div><dt>来源</dt><dd>{detailedDraft ? '待审核产物' : detailedStage?.latestVersion?.label ?? '完整用例'}</dd></div></dl> : null}</div> : null}
            {activeStage && activeChain ? <><section className="gc-inspector-section"><h3>版本选择</h3><div className="gc-inspector-versions" role="group" aria-label="侧栏选择版本">{versionOptions.length ? versionOptions.map(option => <button type="button" key={option.key} className={`gc-version-button${versionKey === option.key ? ' is-active' : ''}`} aria-pressed={versionKey === option.key} onClick={() => { workspace.setVersionKey(option.key); workspace.setDiffOpen(false) }}>{option.label}</button>) : <span>暂无版本</span>}</div></section><UpstreamTrace stage={activeStage} chain={activeChain} upstreamStages={workspace.upstreamStages} versionKey={versionKey} upstream={workspace.upstream} versionUpstreams={workspace.versionDetail.data?.upstreamVersions}
              source={versionKey === 'draft' ? activeStage.draft?.sourceInputs : workspace.selectedVersion ? workspace.versionDetail.data?.sourceInputs : activeChain.sourceInputs}
              loading={Boolean(workspace.selectedVersion && workspace.versionDetail.isFetching)} /></> : null}
</>}
          <div ref={setInspectorContainer} />
        </div><div className="gc-inspector-footer" ref={setInspectorActionContainer} /></> : <Empty description="选择一个阶段查看详情" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
    </aside></div>
    {!chains.length ? <Empty description="暂无生成链" /> : null}

  </div>
}
