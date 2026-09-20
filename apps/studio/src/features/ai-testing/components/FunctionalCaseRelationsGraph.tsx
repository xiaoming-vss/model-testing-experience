import { Background, BackgroundVariant, BaseEdge, Handle, MarkerType, MiniMap, Position, ReactFlow, ReactFlowProvider, applyNodeChanges, getStraightPath, useReactFlow, useStore, type Edge, type EdgeProps, type Node, type NodeChange, type NodeProps } from '@xyflow/react'
import { ExpandOutlined, MinusOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Empty, Tag } from 'antd'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type ReactNode, type Ref } from 'react'
import {
  RELATIONS_NODE_HEIGHT,
  RELATIONS_NODE_WIDTH,
  buildRelationsGraphModel,
  clampRelationsScale,
  layoutRelationsFishbone,
  parseCaseRelationsContent,
  parseDetailedCaseMeta,
  type RelationsLaidOutNode,
  type RelationsOrientation,
} from '../utils/caseRelationsGraph'
import { useThemeStore } from '@/shared/store/theme.store'
import '@xyflow/react/dist/style.css'
import './FunctionalCaseRelationsGraph.css'

// 选中详情面板浮在画布右侧，全图/定位需要把这块宽度让出来，避免节点被压住。
const PANEL_WIDTH = 296
const PANEL_GAP = 24
const PANEL_RESERVE = PANEL_WIDTH + PANEL_GAP
const FIT_PADDING = 48
const MINIMAP_WIDTH = 168
const MINIMAP_HEIGHT = 96

export type FunctionalCaseRelationsGraphHandle = {
  fitView: () => void
  locateSelected: () => void
}

function padCaseNumber(number: number) {
  return String(number).padStart(2, '0')
}

type CaseNodeData = {
  meta: RelationsLaidOutNode
  dimmed: boolean
}

type CaseFlowNode = Node<CaseNodeData, 'case'>

const HANDLE_STYLE = {
  left: '50%',
  top: '50%',
  width: 1,
  height: 1,
  background: 'transparent',
  border: 'none',
} as const

// 节点卡片：位置由 React Flow 的 wrapper 控制，卡片本身只负责展示。
function CaseFlowNode({ data }: NodeProps<CaseFlowNode>) {
  const { meta, dimmed } = data
  return (
    <div
      className={`ai-relations-node${meta.onMainPath ? ' main' : ''}${dimmed ? ' dimmed' : ''}`}
      title={meta.title}
    >
      <Handle type="source" position={Position.Top} style={HANDLE_STYLE} isConnectable={false} />
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} isConnectable={false} />
      <span className="node-head">
        <span className="node-no">{padCaseNumber(meta.number)}</span>
        <span className="node-kind">{meta.onMainPath ? '主线用例' : meta.isolated ? '独立用例' : '分支用例'}</span>
        {meta.module ? <span className="node-module">{meta.module}</span> : null}
      </span>
      <span className="node-title">{meta.title}</span>
    </div>
  )
}

const NODE_TYPES = { case: CaseFlowNode }

// 鱼骨肋线是任意方向的直线，起点终点都取卡片中心，终点收拢到卡片边缘露出箭头。
function FishboneEdge({ id, sourceX, sourceY, targetX, targetY, markerEnd, style }: EdgeProps) {
  const dx = targetX - sourceX
  const dy = targetY - sourceY
  const trim = Math.abs(dx) < 1 && Math.abs(dy) < 1
    ? 0
    : Math.min(RELATIONS_NODE_WIDTH / 2 / Math.abs(dx || 1e-6), RELATIONS_NODE_HEIGHT / 2 / Math.abs(dy || 1e-6))
  const ratio = Math.min(trim, 1)
  const [path] = getStraightPath({ sourceX, sourceY, targetX: targetX - dx * ratio, targetY: targetY - dy * ratio })
  return <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />
}

const EDGE_TYPES = { fishbone: FishboneEdge }

const EDGE_COLORS = {
  next: { normal: 'rgba(96, 165, 250, 0.6)', dim: 'rgba(96, 165, 250, 0.12)' },
  branch: { normal: 'rgba(100, 116, 139, 0.6)', dim: 'rgba(100, 116, 139, 0.15)' },
} as const

function ZoomReadout() {
  const zoom = useStore((state) => state.transform[2])
  return <span className="ai-relations-zoom-value">{Math.round(zoom * 100)}%</span>
}

function PanelSection({ label, items }: { label: string; items?: string[] }) {
  return (
    <div className="panel-section">
      <strong>{label}</strong>
      {!items || items.length === 0 ? (
        <p className="panel-empty">无</p>
      ) : (
        <ol className="panel-list">
          {items.map((item, index) => <li key={index}>{item}</li>)}
        </ol>
      )}
    </div>
  )
}

function RelationsGraphInner({
  content,
  casesContent,
  orientation,
  onSelectionChange,
  handleRef,
}: {
  content: string
  casesContent?: string
  orientation: RelationsOrientation
  onSelectionChange?: (caseId: string | null) => void
  handleRef: Ref<FunctionalCaseRelationsGraphHandle>
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [nodes, setNodes] = useState<CaseFlowNode[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const themeMode = useThemeStore((state) => state.mode)
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const selectedIdRef = useRef<string | null>(null)
  const flow = useReactFlow()
  // useReactFlow 返回的函数标识在首帧后才稳定，统一走 ref，避免回调/effect 依赖抖动引发渲染循环。
  const flowRef = useRef(flow)
  const selectionCallbackRef = useRef(onSelectionChange)

  useEffect(() => {
    flowRef.current = flow
  }, [flow])

  useEffect(() => {
    selectionCallbackRef.current = onSelectionChange
  }, [onSelectionChange])

  const data = useMemo(() => parseCaseRelationsContent(content), [content])
  const caseMetaById = useMemo(() => parseDetailedCaseMeta(casesContent), [casesContent])
  const model = useMemo(() => (data ? buildRelationsGraphModel(data, caseMetaById) : null), [data, caseMetaById])
  const layout = useMemo(() => (model ? layoutRelationsFishbone(model, orientation) : null), [model, orientation])

  const selectedMeta = selectedId ? layout?.nodes.get(selectedId) ?? null : null
  const activeEdgeIds = useMemo(
    () => (selectedMeta && model ? model.edgeIdsByCase.get(selectedMeta.caseId) ?? new Set<string>() : null),
    [selectedMeta, model],
  )
  const activeNodeIds = useMemo(
    () => (selectedMeta && model ? model.neighborIdsByCase.get(selectedMeta.caseId) ?? new Set<string>() : null),
    [selectedMeta, model],
  )

  // 自适应铺满：扣除选中面板占用的宽度后居中，保证整图可见且不被面板压住。
  const fitView = useCallback((animate = true) => {
    const wrapper = wrapperRef.current
    const { getNodes, getNodesBounds: measureNodes, setViewport } = flowRef.current
    const all = getNodes()
    if (!wrapper || all.length === 0) return
    const bounds = measureNodes(all)
    if (bounds.width <= 0 || bounds.height <= 0) return
    const reserve = selectedIdRef.current ? PANEL_RESERVE : 0
    const width = wrapper.clientWidth - reserve
    const height = wrapper.clientHeight
    if (width <= FIT_PADDING || height <= FIT_PADDING) return
    const zoom = clampRelationsScale(Math.min(
      (width - FIT_PADDING) / bounds.width,
      (height - FIT_PADDING) / bounds.height,
      1,
    ))
    setViewport({
      x: (width - bounds.width * zoom) / 2 - bounds.x * zoom,
      y: (height - bounds.height * zoom) / 2 - bounds.y * zoom,
      zoom,
    }, { duration: animate ? 180 : 0 })
  }, [])

  const locateSelected = useCallback(() => {
    const caseId = selectedIdRef.current
    const wrapper = wrapperRef.current
    if (!caseId || !wrapper) return
    const { getNode, getViewport, getZoom, setCenter, setViewport } = flowRef.current
    const node = getNode(caseId)
    if (!node) return
    const zoom = getZoom()
    setCenter(
      node.position.x + RELATIONS_NODE_WIDTH / 2,
      node.position.y + RELATIONS_NODE_HEIGHT / 2,
      { zoom, duration: 200 },
    )
    // setCenter 居中整个画布，这里再左移半个面板宽度，让节点落在可见区域中心。
    const viewport = getViewport()
    setViewport({ ...viewport, x: viewport.x - PANEL_RESERVE / 2 }, { duration: 200 })
  }, [])

  useImperativeHandle(handleRef, () => ({ fitView: () => fitView(), locateSelected }), [fitView, locateSelected])

  // 布局变化（内容/方向切换）时整体重置节点位置；此后拖拽产生的位移由 applyNodeChanges 保留。
  useEffect(() => {
    setSelectedId(null)
    if (!model || !layout) {
      setNodes([])
      setEdges([])
      return
    }
    setNodes([...layout.nodes.values()].map((meta) => ({
      id: meta.caseId,
      type: 'case' as const,
      position: { x: meta.x, y: meta.y },
      initialWidth: RELATIONS_NODE_WIDTH,
      initialHeight: RELATIONS_NODE_HEIGHT,
      selected: false,
      data: { meta, dimmed: false },
    })))
  }, [model, layout])

  useEffect(() => {
    selectedIdRef.current = selectedId
    selectionCallbackRef.current?.(selectedId)
  }, [selectedId])

  // 选中高亮：只更新 data/selected 标记，不重置用户拖拽后的位置。
  useEffect(() => {
    setNodes((current) => current.map((node) => ({
      ...node,
      selected: node.id === selectedId,
      data: {
        ...node.data,
        dimmed: Boolean(selectedMeta) && node.id !== selectedId && !(activeNodeIds?.has(node.id)),
      },
    })))
  }, [selectedId, selectedMeta, activeNodeIds])

  useEffect(() => {
    if (!model) {
      setEdges([])
      return
    }
    setEdges(model.edges.map((edge) => {
      const color = EDGE_COLORS[edge.relationType][!activeEdgeIds || activeEdgeIds.has(edge.edgeId) ? 'normal' : 'dim']
      return {
        id: edge.edgeId,
        source: edge.fromCaseId,
        target: edge.toCaseId,
        type: 'fishbone' as const,
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
        style: {
          stroke: color,
          strokeWidth: 1.6,
          ...(edge.relationType === 'branch' ? { strokeDasharray: '6 5' } : {}),
        },
      }
    }))
  }, [model, activeEdgeIds])

  // 内容/方向切换后重新铺满（等节点完成首帧布局再计算包围盒）。
  useEffect(() => {
    if (!layout) return
    const timer = window.setTimeout(() => fitView(false), 50)
    return () => window.clearTimeout(timer)
  }, [layout, fitView])

  // 面板会盖住画布右侧：选中的节点若落在面板下方，平移视口把它让出来。
  useEffect(() => {
    if (!selectedId) return
    const wrapper = wrapperRef.current
    if (!wrapper) return
    const { getNode, getViewport, getZoom, setViewport } = flowRef.current
    const node = getNode(selectedId)
    if (!node) return
    const zoom = getZoom()
    const viewport = getViewport()
    const nodeRight = (node.position.x + RELATIONS_NODE_WIDTH) * zoom + viewport.x
    const overflow = nodeRight - (wrapper.clientWidth - PANEL_RESERVE)
    if (overflow <= 0) return
    setViewport({ ...viewport, x: viewport.x - overflow - 16 }, { duration: 180 })
  }, [selectedId])

  const onNodesChange = (changes: NodeChange<CaseFlowNode>[]) => {
    setNodes((current) => applyNodeChanges(changes, current))
  }

  if (!data || !model || !layout || model.nodes.length === 0) {
    return (
      <div className="ai-relations-graph" ref={wrapperRef}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={data ? '图谱暂无用例节点' : '图谱数据暂不可解析，请在 json 页签查看原始数据'}
        />
      </div>
    )
  }

  const selectedCaseMeta = selectedId ? caseMetaById.get(selectedId) ?? null : null

  return (
    <div className="ai-relations-graph" ref={wrapperRef}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodesChange={onNodesChange}
        onNodeClick={(_, node) => setSelectedId(node.id)}
        onPaneClick={() => setSelectedId(null)}
        nodesConnectable={false}
        deleteKeyCode={null}
        minZoom={0.2}
        maxZoom={2.5}
        colorMode={themeMode}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={22}
          size={1.4}
          color={themeMode === 'dark' ? 'rgba(148, 163, 184, 0.3)' : 'rgba(100, 116, 139, 0.35)'}
        />
        <MiniMap
          pannable
          zoomable
          position="bottom-right"
          // React Flow 用 style 上的 width/height 作为小地图 SVG 尺寸，缺失就会按默认 200×150 拉伸失真
          style={{
            width: MINIMAP_WIDTH,
            height: MINIMAP_HEIGHT,
            right: selectedId ? PANEL_WIDTH + PANEL_GAP + 14 : 14,
            bottom: 14,
            margin: 0,
          }}
          bgColor={themeMode === 'dark' ? '#161b26' : '#ffffff'}
          maskColor={themeMode === 'dark' ? 'rgba(2, 6, 23, 0.55)' : 'rgba(15, 23, 42, 0.08)'}
          nodeColor={(node) => {
            const meta = (node as CaseFlowNode).data.meta
            if (meta.onMainPath) return themeMode === 'dark' ? '#60a5fa' : '#3b82f6'
            if (meta.isolated) return themeMode === 'dark' ? '#64748b' : '#94a3b8'
            return themeMode === 'dark' ? '#475569' : '#cbd5e1'
          }}
        />
      </ReactFlow>
      <div className="ai-relations-hint" aria-hidden>拖拽空白平移 · 滚轮缩放 · 拖动用例调整位置 · 点击用例查看详情</div>
      <div className="ai-relations-zoom">
        <Button type="text" size="small" aria-label="缩小" icon={<MinusOutlined />} onClick={() => flow.zoomOut({ duration: 120 })} />
        <ZoomReadout />
        <Button type="text" size="small" aria-label="放大" icon={<PlusOutlined />} onClick={() => flow.zoomIn({ duration: 120 })} />
        <Button type="text" size="small" aria-label="适应画布" icon={<ExpandOutlined />} onClick={() => fitView()} />
      </div>
      {selectedMeta ? (
        <aside className="ai-relations-panel">
          <header className="panel-head">
            <span>选中用例 / {padCaseNumber(selectedMeta.number)}</span>
            <Button size="small" type="text" aria-label="关闭选中用例面板" onClick={() => setSelectedId(null)}>×</Button>
          </header>
          <div className="panel-tags">
            <Tag color={selectedMeta.onMainPath ? 'blue' : 'default'}>{selectedMeta.onMainPath ? '主线用例' : selectedMeta.isolated ? '独立用例' : '分支用例'}</Tag>
            {selectedCaseMeta?.priority ? <Tag color="orange">P{selectedCaseMeta.priority}</Tag> : null}
            {selectedCaseMeta?.caseType ? <Tag color="cyan">{selectedCaseMeta.caseType}</Tag> : null}
          </div>
          <h3 className="panel-title">{selectedMeta.title}</h3>
          <p className="panel-uuid">{selectedMeta.caseId}</p>
          {selectedMeta.module ? <p className="panel-meta">模块：{selectedMeta.module}</p> : null}
          {model.paths.length > 1 ? <p className="panel-meta">业务主线：主线 {selectedMeta.pathIndex + 1}</p> : null}
          <PanelSection label="前置条件" items={selectedCaseMeta?.precondition} />
          <PanelSection label="测试步骤" items={selectedCaseMeta?.testSteps} />
          <PanelSection label="预期结果" items={selectedCaseMeta?.expectedResults} />
        </aside>
      ) : null}
    </div>
  )
}

export const FunctionalCaseRelationsGraph = forwardRef<FunctionalCaseRelationsGraphHandle, {
  content: string
  casesContent?: string
  orientation: RelationsOrientation
  onSelectionChange?: (caseId: string | null) => void
  children?: ReactNode
}>(function FunctionalCaseRelationsGraph({ content, casesContent, orientation, onSelectionChange }, ref) {
  return (
    <ReactFlowProvider>
      <RelationsGraphInner
        content={content}
        casesContent={casesContent}
        orientation={orientation}
        onSelectionChange={onSelectionChange}
        handleRef={ref}
      />
    </ReactFlowProvider>
  )
})
