import { ApartmentOutlined, AppstoreOutlined, BranchesOutlined, FileTextOutlined, LoadingOutlined, ProfileOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { Background, BackgroundVariant, BaseEdge, getBezierPath, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState, type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react'
import { useEffect, useMemo, useRef, type CSSProperties } from 'react'
import { useThemeStore } from '@/shared/theme/theme.store'
import type { GenerationChain, GenerationChainKind, GenerationChainStage } from '../api/generationChain.api'
import '@xyflow/react/dist/style.css'

import { generationStageClass, generationStageLabel } from '../utils/generationStageDisplay'

type GroupData = { kind: GenerationChainKind; label: string; status: string; active?: boolean; unconfigured?: boolean; readOnlyUnconfigured?: boolean; onConfigure?: () => void; onSelect?: () => void }
type CardActions = { onOpen: (origin?: HTMLElement) => void }
type StageData = { stage: GenerationChainStage; active: boolean } & CardActions
type SpecialData = { kind: 'content' | 'codeRisk'; active: boolean } & CardActions
type ProfileCardData = { index: string; statusLabel: string; statusClass: string; running: boolean; versionLabel?: string; meta: string }
type ProfileData = ProfileCardData & { active: boolean } & CardActions
type RelationsData = { index: string; active: boolean } & CardActions
type GroupNode = Node<GroupData, 'chainGroup'>
type StageNode = Node<StageData, 'stage'>
type SpecialNode = Node<SpecialData, 'special'>
type ProfileNode = Node<ProfileData, 'profile'>
type RelationsNode = Node<RelationsData, 'relations'>
type CanvasNode = GroupNode | StageNode | SpecialNode | ProfileNode | RelationsNode

type CanvasProps = {
  canWrite: boolean
  sourceSelected: 'ui' | 'api' | null
  onSelectSource: (kind: 'ui' | 'api') => void
  chains: GenerationChain[]; selected?: { kind: GenerationChainKind; stage: string }; special: 'content' | 'codeRisk' | 'repositoryProfile' | 'relations' | null
  /** 仓库画像位于需求分析分组第二行，复用阶段卡片尺寸与状态动画。 */
  profile?: Omit<ProfileCardData, 'index'>
  /** 功能测试「完整用例」派生出的用例图谱入口；没有可用运行记录时不渲染。 */
  relations?: { active: boolean } & CardActions
  onOpenStage: (kind: GenerationChainKind, stage: GenerationChainStage, origin?: HTMLElement) => void
  onOpenSpecial: (kind: 'content' | 'codeRisk' | 'repositoryProfile' | 'relations', origin?: HTMLElement) => void
  onOpenTab: (kind: 'content' | GenerationChainKind) => void
}
const ports = <><Handle type="target" position={Position.Left} className="gc-flow-handle" /><Handle type="target" position={Position.Top} id="top" className="gc-flow-handle" /><Handle type="source" position={Position.Right} className="gc-flow-handle" /><Handle type="source" position={Position.Bottom} id="bottom" className="gc-flow-handle" /></>
const historyInputHandle = 'history-input'
const NODE_CLASS = 'gc-node relative flex flex-col gap-[5px] rounded-[10px] border border-[var(--gc-line)] p-[10px_11px] text-left [font:inherit] text-[var(--gc-text)] cursor-pointer transition-[border-color,box-shadow,transform] duration-[160ms]'
const NODE_TOP_CLASS = 'gc-node-top flex items-center justify-between gap-1.5'
const NODE_INDEX_CLASS = 'gc-node-index font-mono text-[10px] tracking-[0.06em] text-[var(--gc-muted)]'
const NODE_STATE_CLASS = 'gc-node-state text-[10px] text-[var(--gc-muted)]'
const NODE_MAIN_CLASS = 'gc-node-main flex min-w-0 items-center gap-1.5 [&_.anticon]:flex-none [&_.anticon]:text-[15px] [&_.anticon]:text-[var(--app-accent)]'
const NODE_TITLE_CLASS = 'overflow-hidden text-[12px] text-ellipsis whitespace-nowrap'
const NODE_META_CLASS = 'gc-node-meta flex min-w-0 items-center gap-[5px] text-[11px] text-[var(--gc-muted)]'
const NODE_META_TEXT_CLASS = 'overflow-hidden text-ellipsis whitespace-nowrap'
const NODE_VERSION_CLASS = 'gc-node-version flex-[0_0_auto] rounded-[5px] bg-[var(--app-surface-chip)] px-[5px] font-mono text-[10px] text-[var(--gc-muted)]'
const DOC_NODE_CLASS = 'gc-document-node flex min-h-[76px] flex-col items-start gap-1 rounded-[10px] border border-solid border-[var(--gc-line)] bg-[var(--gc-surface)] p-[10px_12px] text-left [font:inherit] text-[var(--gc-text)] cursor-pointer'
const LANE_EMPTY_CLASS = 'gc-lane-empty flex min-h-[76px] flex-col items-start gap-1 rounded-[10px] border border-dashed border-[var(--gc-line)] bg-[var(--gc-surface)] p-[10px_12px] text-left [font:inherit] text-[var(--gc-text)] cursor-pointer'
const NODE_CAPTION_CLASS = 'font-mono text-[10px] tracking-[0.06em] text-[var(--gc-blue)]'
const GROUP_CLASS = 'gc-flow-group relative box-border h-full w-full rounded-[10px] border border-transparent bg-[var(--gc-surface)] p-3.5'
const SPECIAL_CLASS = 'gc-flow-special box-border h-full w-full rounded-[10px] border border-transparent bg-transparent p-3.5'
const GROUP_HEADER_CLASS = 'gc-flow-group-header flex items-center gap-2 [&_small]:ml-auto [&_small]:text-[11px] [&_small]:text-[var(--app-surface-text-muted)] [&_strong]:text-[13px]'
const GROUP_SELECT_CLASS = 'gc-flow-group-select cursor-pointer border-0 bg-transparent p-0 text-left [font:inherit]'
function cardActions(data: CardActions) {
  return {
    onClick: (event: React.MouseEvent<HTMLButtonElement>) => data.onOpen(event.currentTarget),
    title: '打开',
  }
}
function ChainGroup({ data }: NodeProps<GroupNode>) {
  return <section className={`${GROUP_CLASS}${data.active ? ' is-selected' : ''}`} aria-label={data.label}
    onClick={event => { if (!(event.target as HTMLElement).closest('button')) data.onSelect?.() }}>
    <svg className="gc-flow-group-outline" aria-hidden="true"><rect x="0" y="0" rx="10" /></svg>
    <div className={GROUP_HEADER_CLASS}>{data.onSelect ? <button type="button" className={`${GROUP_SELECT_CLASS} nodrag`} aria-label={`选择${data.label}分组`} aria-pressed={Boolean(data.active)} onClick={data.onSelect}><strong>{data.label}</strong></button> : <strong>{data.label}</strong>}<small>{data.status}</small></div>
    {data.unconfigured ? <div className="gc-flow-empty-card relative mt-2.5">{ports}<button type="button" className={`${LANE_EMPTY_CLASS} nodrag w-full min-h-[84px]`} disabled={data.readOnlyUnconfigured} onClick={data.onConfigure}><span className={NODE_CAPTION_CLASS}>未开始</span><strong className="text-[12px]">开始{data.label}</strong><small className="text-[11px] text-[var(--gc-muted)]">{data.readOnlyUnconfigured ? '等待有编辑权限的成员初始化生成流程' : '先完成生成设置，再运行首阶段'}</small></button></div> : null}
  </section>
}
function StageCard({ data }: NodeProps<StageNode>) {
  const { stage } = data
  const Icon = stage.stage === 'ui_surface' ? AppstoreOutlined : stage.stage === 'ui_design' ? ProfileOutlined : stage.stage === 'api_design' ? BranchesOutlined : stage.stage === 'case_names' ? UnorderedListOutlined : FileTextOutlined
  const running = stage.state === 'running'
  const summary = running && stage.moduleGeneration
    ? stage.moduleGeneration.status === 'reviewing' ? '正在独立复核测试点'
      : stage.moduleGeneration.status === 'revising' ? '正在修订测试点'
        : `已完成 ${stage.moduleGeneration.modules.filter(module => module.status === 'completed').length}/${stage.moduleGeneration.modules.length} ${stage.moduleGeneration.stage === 'case_names' ? '个分组' : '个模块'}`
    : running ? '等待本次结果' : stage.blockedReason
      || (stage.state === 'approved' ? '已有当前采用内容' : stage.state === 'draft' ? '已有候选内容' : stage.state === 'invalid' ? '当前内容需重新确认' : stage.state === 'failed' ? stage.errorMessage || '本次生成失败' : '暂无产物')
  return <div className="gc-flow-stage relative w-full">{ports}
    {stage.stage === 'detailed_cases' ? <Handle type="target" position={Position.Bottom} id={historyInputHandle} className="gc-flow-handle" /> : null}
    <button type="button" className={`${NODE_CLASS} ${generationStageClass(stage)}${data.active ? ' is-selected' : ''}`} {...cardActions(data)} aria-label={`${stage.label} · ${generationStageLabel(stage)}`} aria-pressed={data.active} aria-busy={stage.state === 'running'}>
    <span className={NODE_TOP_CLASS}><span className={NODE_INDEX_CLASS}>{String(stage.order + 1).padStart(2, '0')}</span><span className={NODE_STATE_CLASS}>{stage.state === 'running' ? <LoadingOutlined className="gc-running-indicator" aria-hidden /> : null}{generationStageLabel(stage)}</span></span>
    <span className={NODE_MAIN_CLASS}><Icon aria-hidden /><strong className={NODE_TITLE_CLASS}>{stage.label}</strong></span><span className={NODE_META_CLASS}><span className={NODE_META_TEXT_CLASS}>{summary}</span></span>
  </button></div>
}
function SpecialCard({ data }: NodeProps<SpecialNode>) {
  const doc = data.kind === 'content'
  return <section className={`${SPECIAL_CLASS}${doc ? ' is-document relative border-0 p-0' : ''}`} aria-label={doc ? '需求文档' : '代码风险'}>{doc ? ports : null}
    {!doc ? <div className={GROUP_HEADER_CLASS}><strong>代码风险</strong><small>独立分析链</small></div> : null}
    <button type="button" className={`${doc ? DOC_NODE_CLASS : LANE_EMPTY_CLASS}${data.active ? ' is-selected' : ''} ${doc ? 'mt-0' : 'mt-2.5'} w-full min-h-[72px]`} aria-pressed={data.active} {...cardActions(data)}>
      <span className={NODE_CAPTION_CLASS}>{doc ? '需求材料' : '独立'}</span><strong className="text-[12px]">{doc ? <><FileTextOutlined aria-hidden /> 查看需求文档</> : '代码风险分析'}</strong><small className="text-[11px] text-[var(--gc-muted)]">{doc ? '生成链读取这里的最新正文' : '查看代码风险运行报告'}</small>
    </button>
  </section>
}
function RelationsCard({ data }: NodeProps<RelationsNode>) {
  return <div className="gc-flow-stage relative w-full">{ports}
    <button type="button" className={`${NODE_CLASS} is-derived${data.active ? ' is-selected' : ''}`} {...cardActions(data)}
      aria-label="用例图谱 · 派生" aria-pressed={data.active}>
      <span className={NODE_TOP_CLASS}><span className={NODE_INDEX_CLASS}>{data.index}</span><span className={NODE_STATE_CLASS}>派生</span></span>
      <span className={NODE_MAIN_CLASS}><ApartmentOutlined aria-hidden /><strong className={NODE_TITLE_CLASS}>用例图谱</strong></span>
      <span className={NODE_META_CLASS}><span className={NODE_META_TEXT_CLASS}>完整用例的关联图</span></span>
    </button>
  </div>
}
/** 仓库画像不是生成链阶段，但在需求分析分组内复用阶段卡片的尺寸、状态和运行动画。 */
function ProfileCard({ data }: NodeProps<ProfileNode>) {
  return <div className="gc-flow-stage relative w-full">
    <Handle type="target" position={Position.Left} className="gc-flow-handle" />
    <Handle type="target" position={Position.Top} id="top" className="gc-flow-handle" />
    <Handle type="source" position={Position.Right} id="right" className="gc-flow-handle" />
    <button type="button" className={`${NODE_CLASS} ${data.statusClass}${data.active ? ' is-selected' : ''}`} {...cardActions(data)}
      aria-label={`仓库画像 · ${data.statusLabel}`} aria-pressed={data.active} aria-busy={data.running}>
      <span className={NODE_TOP_CLASS}><span className={NODE_INDEX_CLASS}>{data.index}</span><span className={NODE_STATE_CLASS}>{data.running ? <LoadingOutlined className="gc-running-indicator" aria-hidden /> : null}{data.statusLabel}</span></span>
      <span className={NODE_MAIN_CLASS}><ApartmentOutlined aria-hidden /><strong className={NODE_TITLE_CLASS}>仓库画像</strong></span>
      <span className={NODE_META_CLASS}>{data.versionLabel ? <span className={NODE_VERSION_CLASS}>{data.versionLabel}</span> : null}<span className={NODE_META_TEXT_CLASS}>{data.meta}</span></span>
    </button>
  </div>
}
const nodeTypes = { chainGroup: ChainGroup, stage: StageCard, special: SpecialCard, profile: ProfileCard, relations: RelationsCard }
type EdgeRoute = { route?: 'profile' | 'document-material'; optional?: boolean }
type GenerationFlowEdge = Edge<EdgeRoute & { running: boolean }, 'generationFlow'>
// 320 单位/秒，每秒一束；12 段透明度渐变组成 87 单位的拖尾，沿实际曲线行进。
const beamSegments = Array.from({ length: 12 }, (_, index) => ({
  '--gc-beam-offset': `${(11 - index) * 7.25}px`,
  opacity: (index / 11) ** 2.2,
} as CSSProperties))
// 画像入线从材料整理右侧出弯，沿材料整理与画像之间的空隙下行，再接入画像左侧。
function getProfilePath({ sourceX, sourceY, targetX, targetY }: EdgeProps) {
  const corridorX = Math.min(sourceX + 36, targetX - 20)
  const top = sourceY + 46
  const bottom = Math.max(top + 20, targetY - 42)
  return `M ${sourceX} ${sourceY} C ${sourceX + 26} ${sourceY} ${corridorX} ${sourceY + 24} ${corridorX} ${top} L ${corridorX} ${bottom} C ${corridorX} ${targetY - 16} ${corridorX + 8} ${targetY} ${targetX} ${targetY}`
}
// 正文到材料整理的连线从出口上抬，不再下绕与评审连线交叉。
function getDocumentMaterialPath({ sourceX, sourceY, targetX, targetY }: EdgeProps) {
  return `M ${sourceX} ${sourceY} H ${sourceX + 30} C ${sourceX + 80} ${sourceY} ${sourceX + 80} ${targetY} ${targetX} ${targetY}`
}
const flowRoutes = { profile: getProfilePath, 'document-material': getDocumentMaterialPath }
function FlowEdge(props: EdgeProps<GenerationFlowEdge>) {
  const route = props.data?.route
  const path = route ? flowRoutes[route](props) : getBezierPath(props)[0]
  return <>
    {props.data?.optional ? <title>可选输入 · 历史用例核验结果</title> : null}
    <BaseEdge id={props.id} path={path} markerEnd={props.markerEnd} style={props.style} className="gc-flow-edge-track" />
    {props.data?.optional ? null : props.data?.running ? <g className="gc-flow-edge-output" aria-hidden="true">
      <path d={path} className="gc-flow-beam gc-flow-beam-halo" />
      {beamSegments.map((style, index) => <path key={index} d={path} className="gc-flow-beam" style={style} />)}
    </g> : <path d={path} className="gc-flow-edge-stream" fill="none" aria-hidden="true" />}
  </>
}
const edgeTypes = { generationFlow: FlowEdge }
const positions: Record<GenerationChainKind, { x: number; y: number; width: number }> = {
  requirement_analysis: { x: 375, y: 211, width: 560 }, function: { x: 1050, y: -228, width: 600 },
  api: { x: 1100, y: 286, width: 504 }, ui: { x: 1095, y: 652, width: 504 },
}
const stageInset = 20
const stageGap = 40
const functionStageInset = 40
const functionStageGap = 60
const stageTop = 44
const stageBottom = 176
const itemWidth = 126
// 需求分析使用两行：材料整理、历史需求关联在上，需求评审、仓库画像在下。
const analysisGroupSize = { width: 560, height: 320 }
const analysisStagePositions: Record<string, { x: number; y: number }> = {
  extracting_text: { x: 40, y: 48 },
  historical_requirement_relations: { x: 370, y: 48 },
  requirement_review: { x: 40, y: 176 },
}
const profilePosition = { x: 250, y: 196 }
// API / UI 三阶段链路外框向右加宽、向下加高，阶段卡片交错排布。
const staggeredKinds = new Set<GenerationChainKind>(['api', 'ui'])
const staggeredExtraWidth = 96
const staggeredGroupHeight = 280
const compactGroupHeight = 144
const functionGroupHeight = 280
const isStaggered = (kind: GenerationChainKind) => staggeredKinds.has(kind)
const isStaggeredGroup = (node: CanvasNode) => node.type === 'chainGroup' && isStaggered(node.data.kind)
function buildCanvas({ chains, selected, special, profile, relations, canWrite, sourceSelected, onSelectSource, onOpenStage, onOpenSpecial, onOpenTab }: CanvasProps) {
  const nodes: CanvasNode[] = [
    { id: 'document', type: 'special', position: { x: 35, y: 327 }, style: { width: 184 }, data: { kind: 'content', active: special === 'content', onOpen: (origin) => onOpenSpecial('content', origin) } },
    { id: 'risk', type: 'special', position: { x: 300, y: 600 }, style: { width: 300 }, data: { kind: 'codeRisk', active: special === 'codeRisk', onOpen: (origin) => onOpenSpecial('codeRisk', origin) } },
  ]
  const edges: Edge<EdgeRoute>[] = []
  const materialNodeId = 'requirement_analysis:extracting_text'
  const analysis = chains.find(item => item.kind === 'requirement_analysis' && item.configured)
  const verification = analysis?.stages.find(stage => stage.stage === 'historical_test_case_verification')
  for (const chain of chains) {
    const layout = positions[chain.kind]
    const groupId = `group:${chain.kind}`
    const status = !chain.configured ? '未开始' : chain.pendingCandidateCount ? `${chain.pendingCandidateCount} 个候选待处理` : chain.stages.length > 0 && chain.stages.every(stage => ['approved', 'imported'].includes(stage.state)) ? '已全部采用' : '已配置'
    const profileCard = chain.kind === 'requirement_analysis' && chain.configured ? profile : undefined
    const stages = chain.stages.filter(stage => stage !== verification)
    const count = stages.length
    const staggered = isStaggered(chain.kind)
    const groupWidth = chain.kind === 'requirement_analysis'
      ? analysisGroupSize.width
      : Math.max(layout.width, (chain.kind === 'function' ? functionStageInset : stageInset) * 2 + count * itemWidth + Math.max(0, count - 1) * (chain.kind === 'function' ? functionStageGap : stageGap))
        + (staggered ? staggeredExtraWidth : 0)
    const groupHeight = chain.kind === 'requirement_analysis'
      ? analysisGroupSize.height
      : chain.kind === 'function' ? functionGroupHeight : staggered ? staggeredGroupHeight : compactGroupHeight
    nodes.push({ id: groupId, type: 'chainGroup', position: { x: layout.x, y: layout.y }, style: { width: groupWidth, height: groupHeight }, data: { kind: chain.kind, label: chain.label, status, active: chain.kind === sourceSelected, onSelect: chain.kind === 'ui' || chain.kind === 'api' ? () => onSelectSource(chain.kind as 'ui' | 'api') : undefined, unconfigured: !chain.configured, readOnlyUnconfigured: !canWrite && (chain.kind === 'requirement_analysis' || chain.kind === 'function'), onConfigure: () => chain.kind === 'ui' || chain.kind === 'api' ? onSelectSource(chain.kind) : onOpenTab(chain.kind) } })
    if (!chain.configured) continue
    stages.forEach((entry, index) => {
      const id = `${chain.kind}:${entry.stage}`
      const position = chain.kind === 'requirement_analysis'
        ? analysisStagePositions[entry.stage] ?? { x: stageInset + index * (itemWidth + stageGap), y: stageTop }
        : staggered ? {
          x: stageInset + index * (groupWidth - stageInset * 2 - itemWidth) / Math.max(1, count - 1),
          y: index % 2 === 1 ? stageBottom : stageTop,
        } : { x: functionStageInset + index * (itemWidth + functionStageGap), y: stageTop }
      nodes.push({ id, type: 'stage', parentId: groupId, extent: 'parent', position, style: { width: itemWidth }, data: { stage: entry, active: !special && selected?.kind === chain.kind && selected.stage === entry.stage, onOpen: (origin) => onOpenStage(chain.kind, entry, origin) } })
      if (chain.kind === 'requirement_analysis') {
        if (entry.upstreamStages.length === 0) {
          edges.push({
            id: `document-to-${entry.stage}`, source: 'document', target: id,
            data: id === materialNodeId ? { route: 'document-material' } : undefined,
          })
        }
        for (const upstream of entry.upstreamStages) {
          if (stages.some(stage => stage.stage === upstream)) {
            edges.push({ id: `${chain.kind}:${upstream}:${entry.stage}`, source: `${chain.kind}:${upstream}`, target: id })
          }
        }
      } else if (index > 0) {
        edges.push({ id: `${chain.kind}:${index}`, source: `${chain.kind}:${stages[index - 1].stage}`, target: id })
      }
    })
    if (profileCard && stages.length) {
      const profileIndex = stages.length
      nodes.push({
        id: 'profile', type: 'profile', parentId: groupId, extent: 'parent',
        // 第二行居中偏右，与需求评审并列。
        position: profilePosition,
        style: { width: itemWidth },
        data: {
          ...profileCard, index: String(profileIndex + 1).padStart(2, '0'),
          active: special === 'repositoryProfile',
          onOpen: (origin) => onOpenSpecial('repositoryProfile', origin),
        },
      })
      if (stages.some(stage => stage.stage === 'extracting_text')) {
        edges.push({ id: 'analysis-to-profile', source: materialNodeId, target: 'profile', data: { route: 'profile' } })
      }
    }
  }
  const functional = chains.find(item => item.kind === 'function' && item.configured)
  if (verification && nodes.some(node => node.id === 'group:function')) {
    const id = `requirement_analysis:${verification.stage}`
    const upstream = 'requirement_analysis:historical_requirement_relations'
    nodes.push({
      id, type: 'stage', parentId: 'group:function', extent: 'parent',
      position: { x: functionStageInset, y: stageBottom }, style: { width: itemWidth },
      data: {
        stage: verification,
        active: !special && selected?.kind === 'requirement_analysis' && selected.stage === verification.stage,
        onOpen: (origin) => onOpenStage('requirement_analysis', verification, origin),
      },
    })
    if (nodes.some(node => node.id === upstream)) edges.push({ id: 'history-to-verification', source: upstream, target: id })
    if (functional?.stages.some(stage => stage.stage === 'detailed_cases')) {
      edges.push({
        id: 'verification-to-detailed-cases', source: id, target: 'function:detailed_cases',
        targetHandle: historyInputHandle, ariaLabel: '历史用例核验到完整用例的可选输入',
        data: { optional: true }, style: { strokeDasharray: '6 4', opacity: 0.8 },
      })
    }
  }
  if (relations && functional) {
    const count = functional.stages.length
    const groupWidth = Math.max(positions.function.width, functionStageInset * 2 + count * itemWidth + Math.max(0, count - 1) * functionStageGap)
    // 作为泳道子节点固定在分组右侧，随分组一起缩放和平移。
    nodes.push({
      id: 'case-relations', type: 'relations', parentId: `group:function`, position: { x: groupWidth + stageGap, y: stageTop }, style: { width: itemWidth },
      data: { index: String(count + 1).padStart(2, '0'), active: relations.active, onOpen: relations.onOpen },
    })
    const lastStage = functional.stages.at(-1)
    if (lastStage) edges.push({ id: 'function-to-relations', source: `function:${lastStage.stage}`, target: 'case-relations' })
  }
  const hasMaterialNode = nodes.some(node => node.id === materialNodeId)
  if (hasMaterialNode && functional?.stages.some(stage => stage.stage === 'requirement_analysis')) {
    edges.push({ id: 'analysis-to-function', source: materialNodeId, target: 'function:requirement_analysis' })
  }
  const profileNode = nodes.some(node => node.id === 'profile')
  if (profileNode || hasMaterialNode) {
    for (const kind of ['api', 'ui'] as const) {
      const targetChain = chains.find(item => item.kind === kind)
      if (!targetChain) continue
      const target = targetChain.configured && targetChain.stages[0] ? `${kind}:${targetChain.stages[0].stage}` : `group:${kind}`
      // API 与 UI 共用仓库画像提供的软件仓库上下文，两条下游都从画像卡片出线。
      if (profileNode) {
        edges.push({ id: `profile-to-${kind}`, source: 'profile', sourceHandle: 'right', target })
        continue
      }
      edges.push({ id: `analysis-to-${kind}`, source: materialNodeId, target })
    }
  }
  const runningStages = new Set(chains.filter(item => item.configured).flatMap(item => item.stages
    .filter(entry => entry.state === 'running').map(entry => `${item.kind}:${entry.stage}`)))
  return { nodes, edges: edges.map((edge): GenerationFlowEdge => ({ ...edge, type: 'generationFlow', data: { ...edge.data, running: runningStages.has(edge.source) }, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: 'var(--app-accent)', strokeWidth: 1.5, ...edge.style } })) }
}
function CanvasInner(props: CanvasProps) {
  const { chains, selected, special, profile, relations, canWrite, sourceSelected, onSelectSource, onOpenStage, onOpenSpecial, onOpenTab } = props
  const graph = useMemo(() => buildCanvas({ chains, selected, special, profile, relations, canWrite, sourceSelected, onSelectSource, onOpenStage, onOpenSpecial, onOpenTab }), [chains, selected, special, profile, relations, canWrite, sourceSelected, onSelectSource, onOpenStage, onOpenSpecial, onOpenTab])
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(graph.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges)
  const frameRef = useRef<HTMLDivElement>(null)
  const resolvedTheme = useThemeStore(state => state.resolvedTheme)
  useEffect(() => {
    const frame = frameRef.current
    if (!frame) return
    let visible = true
    const update = () => { frame.dataset.flowVisible = String(visible && !document.hidden) }
    const observer = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      update()
    })
    observer?.observe(frame)
    document.addEventListener('visibilitychange', update)
    update()
    return () => {
      observer?.disconnect()
      document.removeEventListener('visibilitychange', update)
    }
  }, [])
  useEffect(() => {
    setNodes(current => {
      const previous = new Map(current.map(node => [node.id, node]))
      // 刷新产物数据时保留节点尺寸；丢失 measured 会让 React Flow 隐藏节点，
      // 而阅读期间延迟的 ResizeObserver 通知不一定会在返回后重新触发。
      return graph.nodes.map(node => {
        const prior = previous.get(node.id)
        return { ...node, measured: prior?.measured, position: prior?.parentId === node.parentId ? prior?.position ?? node.position : node.position }
      })
    })
    setEdges(graph.edges)
  }, [graph, setNodes, setEdges])
  return <div ref={frameRef} className="gc-canvas-frame relative flex min-h-0 min-w-0 flex-1 overflow-hidden rounded-[12px] border border-[var(--app-surface-border)] bg-[var(--app-bg)] max-[900.01px]:h-[min(60vh,600px)] max-[900.01px]:min-h-[380px] max-[900.01px]:flex-none" aria-label="需求生成流程"><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
    nodesConnectable={false} elementsSelectable={false} deleteKeyCode={null} minZoom={0.5} maxZoom={1.5} onInit={flow => {
      const width = frameRef.current?.clientWidth ?? 1650
      const height = frameRef.current?.clientHeight ?? 1000
      const roots = flow.getNodes().filter(node => !node.parentId)
      // 功能测试分组的图谱节点位于分组右侧，缩放时把它的宽度一并计入。
      const nodeWidth = (node: CanvasNode) => (typeof node.style?.width === 'number' ? node.style.width : node.measured?.width ?? 0)
        + (relations && node.id === 'group:function' ? stageGap + itemWidth : 0)
      // 交错排布的分组只扩展外框，初始横向位置仍按扩展前的宽度计算。
      const spacing = Math.max(0.62, Math.min(1, ...roots.filter(node => node.position.x > 35)
        .map(node => (width - 95 - nodeWidth(node) + (isStaggeredGroup(node) ? staggeredExtraWidth : 0)) / (node.position.x - 35))))
      setNodes(current => current.map(node => node.parentId ? node : { ...node, position: { ...node.position, x: 35 + (node.position.x - 35) * spacing } }))
      const right = Math.max(35, ...roots.map(node => 35 + (node.position.x - 35) * spacing + nodeWidth(node)))
      // 图谱节点让功能测试分组更宽：超出画布时缩小初始缩放，避免节点被右侧裁掉。
      const top = Math.min(...roots.map(node => node.position.y))
      const bottom = Math.max(...roots.map(node => node.position.y + (typeof node.style?.height === 'number' ? node.style.height : node.measured?.height ?? 144)))
      const zoom = Math.max(0.5, Math.min(1, width / Math.max(right - 35 + 60, 1), height / (bottom - top + 60)))
      // 高度不足时一起收进视口，避免右上功能测试被裁掉；大画布保留原来的视觉中心。
      const halfHeight = height / (2 * zoom) - 30
      const centerY = bottom - top <= halfHeight * 2 ? Math.min(top + halfHeight, Math.max(bottom - halfHeight, 390)) : (top + bottom) / 2
      void flow.setCenter((35 + right) / 2, centerY, { zoom })
    }}
    zoomOnDoubleClick={false} zoomOnScroll={false} zoomOnPinch panOnScroll={false} zoomActivationKeyCode="Control" colorMode={resolvedTheme} proOptions={{ hideAttribution: true }}>
    <Background variant={BackgroundVariant.Dots} gap={24} size={2.3} color="var(--graph-grid)" />
  </ReactFlow></div>
}
export function RequirementGenerationCanvas(props: CanvasProps) {
  return <ReactFlowProvider><CanvasInner {...props} /></ReactFlowProvider>
}
