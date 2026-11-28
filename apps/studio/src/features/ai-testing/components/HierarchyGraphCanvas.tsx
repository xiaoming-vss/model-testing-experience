import { Background, BaseEdge, MiniMap, ReactFlow, useReactFlow, useStore, type EdgeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { ExpandOutlined, MinusOutlined, PlusOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import type { ReactNode, RefObject } from 'react'
import { HIERARCHY_MIN_ZOOM } from '../utils/relationsHierarchyLayout'
import { useThemeStore } from '@/shared/theme/theme.store'
import { HierarchyNode, type HierarchyCaseNode } from './HierarchyGraphNodes'
import type { useHierarchyFlow, HierarchyFlowEdge } from '../hooks/useHierarchyFlow'

function HierarchyEdge({ id, data, markerEnd, style }: EdgeProps<HierarchyFlowEdge>) {
  return <BaseEdge id={id} path={data?.path ?? ''} markerEnd={markerEnd} style={style} label={data?.label?.id} labelX={data?.label?.x} labelY={data?.label?.y}
    labelStyle={{ fill: 'var(--ant-color-text-secondary)', fontSize: 12 }} labelBgStyle={{ fill: 'var(--ant-color-bg-container)' }} />
}
const EDGE_TYPES = { hierarchy: HierarchyEdge }
const NODE_TYPES = { hierarchyCase: HierarchyNode }

function ZoomReadout() {
  const zoom = useStore((state) => state.transform[2])
  return <span className="ai-relations-zoom-value min-w-[42px] text-center text-[12px] tabular-nums text-[var(--ant-color-text-secondary)]">{Math.round(zoom * 100)}%</span>
}

export function HierarchyGraphCanvas({ graph, canvasRef, onSelect, onFit, controls }: {
  graph: ReturnType<typeof useHierarchyFlow>
  canvasRef: RefObject<HTMLDivElement | null>
  onSelect: (id: string | null) => void
  controls?: ReactNode
  onFit: () => void
}) {
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)
  const flow = useReactFlow()
  const { routing } = graph
  return <div className="ai-relations-graph ai-hierarchy-canvas relative flex h-full min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--ant-color-bg-container)] max-[768.01px]:[&_.react-flow__minimap]:hidden" ref={canvasRef}>
    <ReactFlow nodes={graph.nodes} edges={graph.edges} nodeTypes={NODE_TYPES} edgeTypes={EDGE_TYPES}
      onNodeClick={(_, node) => { if (node.type === 'hierarchyCase') onSelect(node.id) }} onPaneClick={() => onSelect(null)}
      nodesConnectable={false} nodesDraggable={false} edgesFocusable={false} deleteKeyCode={null} minZoom={HIERARCHY_MIN_ZOOM} maxZoom={2.5} colorMode={resolvedTheme} proOptions={{ hideAttribution: true }}>
      <Background gap={22} size={1} color="var(--graph-grid)" />
      <MiniMap pannable zoomable position="bottom-right" style={{ width: 168, height: 96, margin: 12 }} bgColor="var(--graph-minimap-bg)" maskColor="var(--graph-minimap-mask)"
        nodeColor={(node) => node.type === 'hierarchyCase' && (node as HierarchyCaseNode).data.placed.main ? 'var(--graph-minimap-main)' : 'var(--graph-minimap-branch)'} />
    </ReactFlow>
    {controls}
    {routing.error || routing.blockedEdgeIds.length ? <div className="ai-relations-hint ai-hierarchy-routing pointer-events-auto absolute left-3.5 top-3 z-[5] max-w-[calc(100%-28px)] whitespace-normal rounded-full border border-[var(--ant-color-border-secondary)] bg-[var(--ant-color-bg-container)] px-3 py-[5px] text-[11.5px] text-[var(--ant-color-text-secondary)] shadow-[0_1px_3px_var(--app-glass-request-shadow-selected)]" role="status">
      {routing.error ? '部分关联连线尚未完成，已绘制连线会保留' : `${routing.blockedEdgeIds.length} 条关联尚未找到避障路径；可在用例详情查看并跳转关联`}
      <Button size="small" type="link" onClick={routing.retry}>重试</Button>
    </div> : null}
    <div className="ai-relations-zoom absolute bottom-3.5 left-3.5 z-[5] flex items-center gap-px rounded-full border border-[var(--ant-color-border-secondary)] bg-[var(--ant-color-bg-container)] px-[5px] py-[3px] shadow-[0_1px_3px_var(--app-glass-request-shadow-selected)]">
      <Button size="small" type="text" aria-label="缩小" icon={<MinusOutlined />} onClick={() => void flow.zoomOut({ duration: 120 })} /><ZoomReadout />
      <Button size="small" type="text" aria-label="放大" icon={<PlusOutlined />} onClick={() => void flow.zoomIn({ duration: 120 })} />
      <Button size="small" type="text" aria-label="适应画布" icon={<ExpandOutlined />} onClick={onFit} />
    </div>
  </div>
}
