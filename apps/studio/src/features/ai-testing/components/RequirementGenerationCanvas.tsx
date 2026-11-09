import { ApartmentOutlined, AppstoreOutlined, FileTextOutlined, LoadingOutlined, ProfileOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { Background, BackgroundVariant, BaseEdge, getBezierPath, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState, type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react'
import { useEffect, useMemo, useRef, type CSSProperties } from 'react'
import { useThemeStore } from '@/shared/theme/theme.store'
import type { GenerationChain, GenerationChainKind, GenerationChainStage } from '../api/generationChain.api'
import type { ChainFilter } from '../hooks/useRequirementGenerationChain'
import '@xyflow/react/dist/style.css'

import { generationStageClass, generationStageLabel } from '../utils/generationStageDisplay'

type GroupData = { kind: GenerationChainKind; label: string; status: string; dim: boolean; active?: boolean; unconfigured?: boolean; readOnlyUnconfigured?: boolean; onConfigure?: () => void; onSelect?: () => void }
type CardActions = { onSelect: () => void; onOpen: (origin?: HTMLElement) => void }
type StageData = { stage: GenerationChainStage; active: boolean; dim: boolean } & CardActions
type SpecialData = { kind: 'content' | 'codeRisk'; active: boolean } & CardActions
type ProfileCardData = { index: string; statusLabel: string; statusClass: string; running: boolean; versionLabel?: string; meta: string }
type ProfileData = ProfileCardData & { active: boolean } & CardActions
type RelationsData = { index: string; active: boolean; dim: boolean } & CardActions
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
  chains: GenerationChain[]; filter: ChainFilter; selected?: { kind: GenerationChainKind; stage: string }; special: 'content' | 'codeRisk' | 'repositoryProfile' | 'relations' | null
  /** 仓库画像作为需求分析分组内第二行右对齐的卡片渲染，复用阶段卡片尺寸与状态动画。 */
  profile?: Omit<ProfileCardData, 'index'>
  /** 功能测试「完整用例」派生出的用例图谱入口；没有可用运行记录时不渲染。 */
  relations?: { active: boolean } & CardActions
  onSelectStage: (kind: GenerationChainKind, stage: GenerationChainStage) => void
  onOpenStage: (kind: GenerationChainKind, stage: GenerationChainStage, origin?: HTMLElement) => void
  onSelectSpecial: (kind: 'content' | 'codeRisk' | 'repositoryProfile' | 'relations') => void
  onOpenSpecial: (kind: 'content' | 'codeRisk' | 'repositoryProfile' | 'relations', origin?: HTMLElement) => void
  onOpenTab: (kind: 'content' | GenerationChainKind) => void
}
const ports = <><Handle type="target" position={Position.Left} className="gc-flow-handle" /><Handle type="target" position={Position.Top} id="top" className="gc-flow-handle" /><Handle type="source" position={Position.Right} className="gc-flow-handle" /><Handle type="source" position={Position.Bottom} id="bottom" className="gc-flow-handle" /></>
function cardActions(data: CardActions) {
  return {
    onClick: (event: React.MouseEvent<HTMLButtonElement>) => { data.onSelect(); if (event.detail === 0) data.onOpen(event.currentTarget) },
    onDoubleClick: (event: React.MouseEvent<HTMLButtonElement>) => data.onOpen(event.currentTarget),
    title: '单击选中，双击打开；键盘按 Enter 或空格打开',
  }
}
function ChainGroup({ data }: NodeProps<GroupNode>) {
  return <section className={`gc-flow-group${data.dim ? ' is-dim' : ''}${data.active ? ' is-selected' : ''}`} aria-label={data.label}
    onClick={event => { if (!(event.target as HTMLElement).closest('button')) data.onSelect?.() }}>
    <svg className="gc-flow-group-outline" aria-hidden="true"><rect x="0" y="0" rx="10" /></svg>
    <div className="gc-flow-group-header">{data.onSelect ? <button type="button" className="gc-flow-group-select nodrag" aria-label={`选择${data.label}分组`} aria-pressed={Boolean(data.active)} onClick={data.onSelect}><strong>{data.label}</strong></button> : <strong>{data.label}</strong>}<small>{data.status}</small></div>
    {data.unconfigured ? <div className="gc-flow-empty-card">{ports}<button type="button" className="gc-lane-empty nodrag" disabled={data.readOnlyUnconfigured} onClick={data.onConfigure}><span>未开始</span><strong>开始{data.label}</strong><small>{data.readOnlyUnconfigured ? '等待有编辑权限的成员初始化生成流程' : '先完成生成设置，再运行首阶段'}</small></button></div> : null}
  </section>
}
function StageCard({ data }: NodeProps<StageNode>) {
  const { stage } = data
  const Icon = stage.stage === 'ui_surface' ? AppstoreOutlined : stage.stage === 'ui_design' ? ProfileOutlined : stage.stage === 'case_names' ? UnorderedListOutlined : FileTextOutlined
  const summary = stage.draft?.summary ?? stage.latestVersion?.summary ?? stage.blockedReason ?? '暂无产物'
  return <div className={`gc-flow-stage${data.dim ? ' is-dim' : ''}`}>{ports}<button type="button" className={`gc-node ${generationStageClass(stage)}${data.active ? ' is-selected' : ''}`} {...cardActions(data)} aria-label={`${stage.label} · ${generationStageLabel(stage)}`} aria-pressed={data.active} aria-busy={stage.state === 'running'}>
    <span className="gc-node-top"><span className="gc-node-index">{String(stage.order + 1).padStart(2, '0')}</span><span className="gc-node-state">{stage.state === 'running' ? <LoadingOutlined className="gc-running-indicator" aria-hidden /> : null}{generationStageLabel(stage)}</span></span>
    <span className="gc-node-main"><Icon aria-hidden /><strong>{stage.label}</strong></span><span className="gc-node-meta">{!stage.draft && stage.latestVersion ? <span className="gc-node-version">{stage.latestVersion.label}</span> : null}<span>{summary}</span></span>
  </button></div>
}
function SpecialCard({ data }: NodeProps<SpecialNode>) {
  const doc = data.kind === 'content'
  return <section className={`gc-flow-special${doc ? ' is-document' : ''}`} aria-label={doc ? '需求文档' : '代码风险'}>{doc ? ports : null}
    {!doc ? <div className="gc-flow-group-header"><strong>代码风险</strong><small>独立分析链</small></div> : null}
    <button type="button" className={`${doc ? 'gc-document-node' : 'gc-lane-empty'}${data.active ? ' is-selected' : ''}`} aria-pressed={data.active} {...cardActions(data)}>
      <span>{doc ? '需求材料' : '独立'}</span><strong>{doc ? <><FileTextOutlined aria-hidden /> 查看需求文档</> : '代码风险分析'}</strong><small>{doc ? '生成链读取这里的最新正文' : '查看代码风险运行报告'}</small>
    </button>
  </section>
}
function RelationsCard({ data }: NodeProps<RelationsNode>) {
  return <div className="gc-flow-stage">{ports}
    <button type="button" className={`gc-node is-derived${data.active ? ' is-selected' : ''}`} {...cardActions(data)}
      aria-label="用例图谱 · 派生" aria-pressed={data.active}>
      <span className="gc-node-top"><span className="gc-node-index">{data.index}</span><span className="gc-node-state">派生</span></span>
      <span className="gc-node-main"><ApartmentOutlined aria-hidden /><strong>用例图谱</strong></span>
      <span className="gc-node-meta"><span>完整用例的关联图</span></span>
    </button>
  </div>
}
/** 仓库画像不是生成链阶段，但在需求分析分组内复用阶段卡片的尺寸、状态和运行动画。 */
function ProfileCard({ data }: NodeProps<ProfileNode>) {
  return <div className="gc-flow-stage">
    <Handle type="target" position={Position.Left} className="gc-flow-handle" />
    <Handle type="target" position={Position.Top} id="top" className="gc-flow-handle" />
    <button type="button" className={`gc-node ${data.statusClass}${data.active ? ' is-selected' : ''}`} {...cardActions(data)}
      aria-label={`仓库画像 · ${data.statusLabel}`} aria-pressed={data.active} aria-busy={data.running}>
      <span className="gc-node-top"><span className="gc-node-index">{data.index}</span><span className="gc-node-state">{data.running ? <LoadingOutlined className="gc-running-indicator" aria-hidden /> : null}{data.statusLabel}</span></span>
      <span className="gc-node-main"><ApartmentOutlined aria-hidden /><strong>仓库画像</strong></span>
      <span className="gc-node-meta">{data.versionLabel ? <span className="gc-node-version">{data.versionLabel}</span> : null}<span>{data.meta}</span></span>
    </button>
  </div>
}
const nodeTypes = { chainGroup: ChainGroup, stage: StageCard, special: SpecialCard, profile: ProfileCard, relations: RelationsCard }
type GenerationFlowEdge = Edge<{ running: boolean }, 'generationFlow'>
// 320 单位/秒，每秒一束；12 段透明度渐变组成 87 单位的拖尾，沿实际曲线行进。
const beamSegments = Array.from({ length: 12 }, (_, index) => ({
  '--gc-beam-offset': `${(11 - index) * 7.25}px`,
  opacity: (index / 11) ** 2.2,
} as CSSProperties))
function FlowEdge(props: EdgeProps<GenerationFlowEdge>) {
  const [path] = getBezierPath(props)
  return <>
    <BaseEdge id={props.id} path={path} markerEnd={props.markerEnd} style={props.style} className="gc-flow-edge-track" />
    {props.data?.running ? <g className="gc-flow-edge-output" aria-hidden="true">
      <path d={path} className="gc-flow-beam gc-flow-beam-halo" />
      {beamSegments.map((style, index) => <path key={index} d={path} className="gc-flow-beam" style={style} />)}
    </g> : <path d={path} className="gc-flow-edge-stream" fill="none" aria-hidden="true" />}
  </>
}
const edgeTypes = { generationFlow: FlowEdge }
const positions: Record<GenerationChainKind, { x: number; y: number; width: number }> = {
  requirement_analysis: { x: 434, y: 273, width: 292 }, function: { x: 1024, y: -172, width: 455 },
  api: { x: 1027, y: 286, width: 455 }, ui: { x: 1044, y: 630, width: 455 },
}
const stageInset = 20
const stageGap = 40
const stageTop = 44
const stageBottom = 176
const itemWidth = 126
// 三阶段链路（功能测试、UI 测试）外框向右加宽、向下加高，阶段卡片交错排布。
const staggeredKinds = new Set<GenerationChainKind>(['function', 'ui'])
const staggeredExtraWidth = 96
const staggeredGroupHeight = 280
const compactGroupHeight = 144
const isStaggered = (kind: GenerationChainKind) => staggeredKinds.has(kind)
const isStaggeredGroup = (node: CanvasNode) => node.type === 'chainGroup' && isStaggered(node.data.kind)
function buildCanvas({ chains, filter, selected, special, profile, relations, canWrite, sourceSelected, onSelectSource, onSelectStage, onOpenStage, onSelectSpecial, onOpenSpecial, onOpenTab }: CanvasProps) {
  const nodes: CanvasNode[] = [
    { id: 'document', type: 'special', position: { x: 35, y: 275 }, style: { width: 184 }, data: { kind: 'content', active: special === 'content', onSelect: () => onSelectSpecial('content'), onOpen: (origin) => onOpenSpecial('content', origin) } },
    { id: 'risk', type: 'special', position: { x: 198, y: 643 }, style: { width: 300 }, data: { kind: 'codeRisk', active: special === 'codeRisk', onSelect: () => onSelectSpecial('codeRisk'), onOpen: (origin) => onOpenSpecial('codeRisk', origin) } },
  ]
  const edges: Edge[] = []
  for (const chain of chains) {
    const layout = positions[chain.kind]
    const dim = (filter === 'draft' && !chain.draftCount) || (filter === 'empty' && chain.configured)
    const groupId = `group:${chain.kind}`
    const status = !chain.configured ? '未开始' : chain.draftCount ? `${chain.draftCount} 个待审核` : chain.stages.length > 0 && chain.stages.every(stage => ['approved', 'imported'].includes(stage.state)) ? '已通过' : '已配置'
    const profileCard = chain.kind === 'requirement_analysis' && chain.configured ? profile : undefined
    const hasProfileRow = Boolean(profileCard && chain.stages.length)
    const count = chain.stages.length
    const staggered = isStaggered(chain.kind)
    const groupWidth = Math.max(layout.width, stageInset * 2 + count * itemWidth + Math.max(0, count - 1) * stageGap)
      + (staggered ? staggeredExtraWidth : 0)
    const groupHeight = staggered || hasProfileRow ? staggeredGroupHeight : compactGroupHeight
    nodes.push({ id: groupId, type: 'chainGroup', position: { x: layout.x, y: layout.y }, style: { width: groupWidth, height: groupHeight }, data: { kind: chain.kind, label: chain.label, status, dim, active: chain.kind === sourceSelected, onSelect: chain.kind === 'ui' || chain.kind === 'api' ? () => onSelectSource(chain.kind as 'ui' | 'api') : undefined, unconfigured: !chain.configured, readOnlyUnconfigured: !canWrite && (chain.kind === 'requirement_analysis' || chain.kind === 'function'), onConfigure: () => chain.kind === 'ui' || chain.kind === 'api' ? onSelectSource(chain.kind) : onOpenTab(chain.kind) } })
    if (!chain.configured) continue
    chain.stages.forEach((entry, index) => {
      const id = `${chain.kind}:${entry.stage}`
      const position = staggered ? {
        x: stageInset + index * (groupWidth - stageInset * 2 - itemWidth) / Math.max(1, count - 1),
        y: index % 2 === 1 ? stageBottom : stageTop,
      } : { x: stageInset + index * (itemWidth + stageGap), y: stageTop }
      nodes.push({ id, type: 'stage', parentId: groupId, extent: 'parent', position, style: { width: itemWidth }, data: { stage: entry, active: !special && selected?.kind === chain.kind && selected.stage === entry.stage, dim, onSelect: () => onSelectStage(chain.kind, entry), onOpen: (origin) => onOpenStage(chain.kind, entry, origin) } })
      if (index > 0) edges.push({ id: `${chain.kind}:${index}`, source: `${chain.kind}:${chain.stages[index - 1].stage}`, target: id })
    })
    if (profileCard && chain.stages.length) {
      const profileIndex = chain.stages.length
      nodes.push({
        id: 'profile', type: 'profile', parentId: groupId, extent: 'parent',
        // 仓库画像在分组第二行右对齐，避免看起来像需求理解之后的第三个链上阶段。
        position: { x: groupWidth - stageInset - itemWidth, y: stageBottom },
        style: { width: itemWidth },
        data: {
          ...profileCard, index: String(profileIndex + 1).padStart(2, '0'),
          active: special === 'repositoryProfile',
          onSelect: () => onSelectSpecial('repositoryProfile'),
          onOpen: (origin) => onOpenSpecial('repositoryProfile', origin),
        },
      })
      edges.push({ id: 'analysis-to-profile', source: `requirement_analysis:${chain.stages[profileIndex - 1].stage}`, target: 'profile', sourceHandle: 'bottom', targetHandle: 'top' })
    }
  }
  const analysis = chains.find(item => item.kind === 'requirement_analysis' && item.configured)
  const functional = chains.find(item => item.kind === 'function' && item.configured)
  if (relations && functional) {
    const count = functional.stages.length
    const groupWidth = Math.max(positions.function.width, stageInset * 2 + count * itemWidth + Math.max(0, count - 1) * stageGap) + staggeredExtraWidth
    // 作为泳道子节点固定在分组右侧，随分组一起缩放和平移。
    nodes.push({
      id: 'case-relations', type: 'relations', parentId: `group:function`, position: { x: groupWidth + stageGap, y: stageTop }, style: { width: itemWidth },
      data: { index: String(count + 1).padStart(2, '0'), active: relations.active, dim: (filter === 'draft' && !functional.draftCount) || (filter === 'empty' && functional.configured), onSelect: relations.onSelect, onOpen: relations.onOpen },
    })
    const lastStage = functional.stages.at(-1)
    if (lastStage) edges.push({ id: 'function-to-relations', source: `function:${lastStage.stage}`, target: 'case-relations' })
  }
  if (analysis?.stages[0]) edges.push({ id: 'document-to-analysis', source: 'document', target: `requirement_analysis:${analysis.stages[0].stage}` })
  if (analysis?.stages.length && functional?.stages[0]) edges.push({ id: 'analysis-to-function', source: `requirement_analysis:${analysis.stages.at(-1)!.stage}`, target: `function:${functional.stages[0].stage}` })
  if (analysis?.stages.length) {
    for (const kind of ['api', 'ui'] as const) {
      const targetChain = chains.find(item => item.kind === kind)
      if (!targetChain) continue
      const target = targetChain.configured && targetChain.stages[0] ? `${kind}:${targetChain.stages[0].stage}` : `group:${kind}`
      edges.push({ id: `analysis-to-${kind}`, source: `requirement_analysis:${analysis.stages.at(-1)!.stage}`, target })
    }
  }
  const runningStages = new Set(chains.filter(item => item.configured).flatMap(item => item.stages
    .filter(entry => entry.state === 'running').map(entry => `${item.kind}:${entry.stage}`)))
  return { nodes, edges: edges.map((edge): GenerationFlowEdge => ({ ...edge, type: 'generationFlow', data: { running: runningStages.has(edge.source) }, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: 'var(--app-accent)', strokeWidth: 1.5 } })) }
}
function CanvasInner(props: CanvasProps) {
  const { chains, filter, selected, special, profile, relations, canWrite, sourceSelected, onSelectSource, onSelectStage, onOpenStage, onSelectSpecial, onOpenSpecial, onOpenTab } = props
  const graph = useMemo(() => buildCanvas({ chains, filter, selected, special, profile, relations, canWrite, sourceSelected, onSelectSource, onSelectStage, onOpenStage, onSelectSpecial, onOpenSpecial, onOpenTab }), [chains, filter, selected, special, profile, relations, canWrite, sourceSelected, onSelectSource, onSelectStage, onOpenStage, onSelectSpecial, onOpenSpecial, onOpenTab])
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
      return graph.nodes.map(node => ({ ...node, measured: previous.get(node.id)?.measured, position: previous.get(node.id)?.position ?? node.position }))
    })
    setEdges(graph.edges)
  }, [graph, setNodes, setEdges])
  return <div ref={frameRef} className="gc-canvas-frame" aria-label="需求生成流程"><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
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
