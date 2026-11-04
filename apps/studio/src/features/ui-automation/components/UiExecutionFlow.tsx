import { forwardRef, useCallback, useImperativeHandle, useMemo, useState, type ReactNode, type CSSProperties } from 'react'
import { Alert, Button, Dropdown, Space } from 'antd'
import { MoreOutlined } from '@ant-design/icons'
import { Background, BaseEdge, Controls, EdgeLabelRenderer, getBezierPath, Handle, MarkerType, Position, ReactFlow, addEdge, reconnectEdge, useEdgesState, useNodesState, type Connection, type Edge, type EdgeProps, type Node, type NodeProps, type OnReconnect, type XYPosition } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { UiTestCaseRunStepResult } from '@/services/api'
import { getFlowOrder } from '../utils/flowOrder'
import { computeFlowLayout, oppositeFlowSide, FLOW_NODE_WIDTH, FLOW_NODE_HEIGHT, FLOW_COLUMN_PITCH, FLOW_ROW_PITCH, LEGACY_COLUMN_PITCH, LEGACY_ROW_OFFSETS, type FlowHandleSide } from '../utils/flowLayout'
import { UiStepResultBadge } from './UiStepResultBadge'
import '../styles/execution-flow.css'

export type FlowItemAction = { key: string; label: string; danger?: boolean; onSelect: () => void }
export type FlowItem = { id: string; title: string; caption: string; serial: string; enabled: boolean; result?: UiTestCaseRunStepResult; actions?: FlowItemAction[] }
type FlowNodeData = FlowItem & { sourceSide: FlowHandleSide; targetSide: FlowHandleSide }
type AddFlowNodeData = { label: string; targetSide: FlowHandleSide }
type FlowNode = Node<FlowNodeData, 'execution'>
type AddFlowNode = Node<AddFlowNodeData, 'add'>
type StoredFlowPosition = XYPosition & Partial<Pick<FlowNodeData, 'sourceSide' | 'targetSide'>>
export type UiExecutionFlowHandle = { prepareSave: () => boolean }
type Props = { inlineSave?: boolean; header?: ReactNode; toolbarExtra?: ReactNode; items: FlowItem[]; storageKey: string; editable: boolean; applying?: boolean; remapPositionsOnApply?: boolean; selectedId?: string; runningIds?: string[]; onSelect?: (id: string) => void; onOpen?: (id: string) => void; onApply: (order: string[]) => void; onAdd?: () => void; addLabel?: string; hint?: string }

const ADD_NODE_ID = '__ui-flow-add__'
const HANDLE_POSITION: Record<FlowHandleSide, Position> = { left: Position.Left, right: Position.Right, top: Position.Top, bottom: Position.Bottom }
const ADD_TARGET_SIDES: FlowHandleSide[] = ['left', 'right', 'top', 'bottom']
const HIDDEN_HANDLE_STYLE: CSSProperties = { opacity: 0, pointerEvents: 'none' }

function ExecutionNode({ data }: NodeProps<FlowNode>) {
  const actions = data.actions ?? []
  return <div className={`ui-flow-node${actions.length ? ' has-actions' : ''}`}>
    <Handle type="target" position={HANDLE_POSITION[data.targetSide]} />
    <div className="ui-flow-node-head"><span className="ui-flow-node-serial">{data.serial}</span><span className={`ui-flow-node-status${data.enabled ? ' tone-green' : ''}`}>{data.enabled ? '● 已启用' : '已禁用'}</span></div>
    <strong title={data.title}>{data.title}</strong><span className="ui-flow-node-caption">{data.caption}</span>{data.result ? <UiStepResultBadge stepResult={data.result} /> : null}
    {actions.length ? <div className="ui-flow-node-actions nodrag nopan" onClick={(event) => event.stopPropagation()} onDoubleClick={(event) => event.stopPropagation()} onPointerDown={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
      <Dropdown
        trigger={['click']}
        placement="bottomRight"
        menu={{
          items: actions.map((action) => ({ key: action.key, label: action.label, danger: action.danger })),
          onClick: ({ key }) => actions.find((action) => action.key === key)?.onSelect(),
        }}
      >
        <button type="button" className="ui-flow-node-action-trigger" aria-label={`${data.title} 更多操作`}>
          <MoreOutlined />
        </button>
      </Dropdown>
    </div> : null}
    <Handle type="source" position={HANDLE_POSITION[data.sourceSide]} />
  </div>
}

function AddNode({ data }: NodeProps<AddFlowNode>) {
  return <div className="ui-flow-node ui-flow-node-add">
    {/* 三个方向的入线口常驻，按终点方向选择其中一个，避免连接点位置变化后需要重新测量。 */}
    {ADD_TARGET_SIDES.map((side) => <Handle key={side} id={`add-${side}`} type="target" position={HANDLE_POSITION[side]} style={side === data.targetSide ? undefined : HIDDEN_HANDLE_STYLE} />)}
    <span className="ui-flow-node-add-icon" aria-hidden="true">+</span>
    <strong>{data.label}</strong>
  </div>
}
const nodeTypes = { execution: ExecutionNode, add: AddNode }
const beamSegments = Array.from({ length: 12 }, (_, index) => ({
  '--ui-flow-beam-offset': `${(11 - index) * 7.25}px`,
  opacity: (index / 11) ** 2.2,
} as CSSProperties))

function RemovableEdge(props: EdgeProps) {
  const [path, x, y] = getBezierPath(props)
  const remove = props.data?.remove as ((id: string) => void) | undefined
  return <>
    <BaseEdge id={props.id} path={path} markerEnd={props.markerEnd} interactionWidth={24} className="ui-flow-edge-track" />
    {props.data?.running ? <g className="ui-flow-edge-output" aria-hidden="true">
      <path d={path} className="ui-flow-beam ui-flow-beam-halo" />
      {beamSegments.map((style, index) => <path key={index} d={path} className="ui-flow-beam" style={style} />)}
    </g> : <path d={path} className="ui-flow-edge-stream" fill="none" aria-hidden="true" />}
    {props.selected && remove ? <EdgeLabelRenderer>
      <button type="button" className="ui-flow-edge-delete nodrag nopan" aria-label="删除选中连线" style={{ transform: `translate(-50%, -50%) translate(${x}px, ${y}px)` }} onClick={(event) => { event.stopPropagation(); remove(props.id) }}>×</button>
    </EdgeLabelRenderer> : null}
  </>
}
const edgeTypes = { removable: RemovableEdge }
const edgeStyle = { type: 'removable', markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--app-accent)' }, interactionWidth: 24 }
function isHandleSide(value: unknown): value is FlowHandleSide {
  return value === 'left' || value === 'right' || value === 'top' || value === 'bottom'
}

function toStoredPosition(node: Node): StoredFlowPosition {
  const data = node.data as Partial<FlowNodeData>
  return {
    x: node.position.x,
    y: node.position.y,
    ...(isHandleSide(data.sourceSide) ? { sourceSide: data.sourceSide } : {}),
    ...(isHandleSide(data.targetSide) ? { targetSide: data.targetSide } : {}),
  }
}

function readPositions(key: string): Record<string, StoredFlowPosition> {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? '{}')
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
    const positions: Record<string, StoredFlowPosition> = {}
    for (const [id, position] of Object.entries(value)) {
      if (!position || typeof position !== 'object') continue
      const point = position as Partial<XYPosition> & { sourceSide?: unknown; targetSide?: unknown }
      if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) continue
      positions[id] = { x: point.x as number, y: point.y as number }
      if (isHandleSide(point.sourceSide)) positions[id].sourceSide = point.sourceSide
      if (isHandleSide(point.targetSide)) positions[id].targetSide = point.targetSide
    }
    return positions
  } catch { return {} }
}

/** 旧版单行排布只作为默认值保存过；用户拖动过的位置不会被这套规则命中。 */
function isLegacyAutoLayout(positions: Record<string, StoredFlowPosition>, ids: string[]): boolean {
  if (ids.length === 0) return false
  const slots = new Set(ids.map((_, index) => `${index * LEGACY_COLUMN_PITCH}:${LEGACY_ROW_OFFSETS[index % 2]}`))
  return ids.every((id) => {
    const position = positions[id]
    return position !== undefined && slots.has(`${position.x}:${position.y}`)
  })
}

export const UiExecutionFlow = forwardRef<UiExecutionFlowHandle, Props>(function UiExecutionFlow({ inlineSave, header, toolbarExtra, items, storageKey, editable, applying, remapPositionsOnApply, selectedId, runningIds, onSelect, onOpen, onApply, onAdd, addLabel = '添加', hint }, ref) {
  const ids = items.map((item) => item.id)
  const savedPositions = readPositions(storageKey)
  const legacyLayout = isLegacyAutoLayout(savedPositions, ids)
  const initialLayout = computeFlowLayout(items.length, { withAddSlot: Boolean(onAdd) })
  const [nodes, , onNodesChange] = useNodesState<Node>(items.map((item, index) => {
    const placement = initialLayout.nodes[index]
    const saved = legacyLayout ? undefined : savedPositions[item.id]
    return {
      id: item.id,
      type: 'execution',
      position: saved ? { x: saved.x, y: saved.y } : placement.position,
      // 后台标签页里 ResizeObserver 不会派发测量结果；给出初始尺寸避免卡片一直 visibility:hidden。
      initialWidth: FLOW_NODE_WIDTH,
      initialHeight: FLOW_NODE_HEIGHT,
      // 旧版保存的位置没有连接点方向，按原来的左右连线兜底。
      data: { ...item, sourceSide: saved?.sourceSide ?? (saved ? 'right' : placement.sourceSide), targetSide: saved?.targetSide ?? (saved ? 'left' : placement.targetSide) },
    }
  }))
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(items.slice(1).map((item, index) => ({ id: `${items[index].id}-${item.id}`, source: items[index].id, target: item.id, ...edgeStyle })))
  const [selectedEdge, setSelectedEdge] = useState('')
  const order = getFlowOrder(ids, edges)
  const dirty = !order || order.some((id, index) => id !== ids[index])
  // 虚线入口挂在流程实际的终点；连线不完整时退回最后一张卡片。
  const terminalId = order?.length ? order[order.length - 1] : ids[ids.length - 1]
  // 末尾的“+”卡片只是入口，不进入 items/连线状态，因此不影响执行顺序与保存。
  const addNode = useMemo<AddFlowNode | null>(() => {
    if (!onAdd) return null
    const lastNode = (terminalId ? nodes.find((node) => node.id === terminalId) : undefined) ?? nodes[nodes.length - 1]
    const sourceSide = (lastNode?.data as FlowNodeData | undefined)?.sourceSide ?? 'right'
    // 沿终点卡片的出线方向接一张添加卡片，折行时自然落到下一格或下一行首格。
    const offset = sourceSide === 'left' ? { x: -FLOW_COLUMN_PITCH, y: 0 }
      : sourceSide === 'bottom' ? { x: 0, y: FLOW_ROW_PITCH }
        : sourceSide === 'top' ? { x: 0, y: -FLOW_ROW_PITCH }
          : { x: FLOW_COLUMN_PITCH, y: 0 }
    return {
      id: ADD_NODE_ID, type: 'add',
      position: lastNode ? { x: lastNode.position.x + offset.x, y: lastNode.position.y + offset.y } : { x: 0, y: 0 },
      data: { label: addLabel, targetSide: oppositeFlowSide(sourceSide) },
      draggable: false, selectable: false, deletable: false, connectable: false, initialWidth: FLOW_NODE_WIDTH, initialHeight: FLOW_NODE_HEIGHT,
    }
  }, [addLabel, nodes, onAdd, terminalId])
  const displayedNodes = useMemo(() => {
    const list = nodes.map((node) => {
      const item = items.find((entry) => entry.id === node.id)
      return { ...node, selected: selectedId === undefined ? node.selected : node.id === selectedId, data: item ? { ...node.data, ...item } : node.data }
    })
    return addNode ? [...list, addNode] : list
  }, [addNode, nodes, items, selectedId])
  const onConnect = useCallback((connection: Connection) => {
    if (connection.source !== connection.target) setEdges((current) => addEdge({ ...connection, ...edgeStyle }, current))
  }, [setEdges])
  const onReconnect: OnReconnect = useCallback((oldEdge, connection) => {
    if (connection.source !== connection.target) setEdges((current) => reconnectEdge(oldEdge, connection, current))
  }, [setEdges])
  const savePositions = useCallback((next: Node[]) => {
    try {
      const positions: Record<string, StoredFlowPosition> = {}
      for (const node of next) {
        if (node.id === ADD_NODE_ID) continue
        positions[node.id] = toStoredPosition(node)
      }
      localStorage.setItem(storageKey, JSON.stringify(positions))
    } catch { /* Layout remains usable for this session. */ }
  }, [storageKey])
  const applyOrder = useCallback((nextOrder: string[]) => {
    if (remapPositionsOnApply) {
      try {
        const positions = new Map(nodes.map((node) => [node.id, toStoredPosition(node)]))
        localStorage.setItem(storageKey, JSON.stringify(Object.fromEntries(nextOrder.map((id, index) => [String(index), positions.get(id)]))))
      } catch { /* The order can still be saved without a local layout. */ }
    }
    onApply(nextOrder)
  }, [nodes, onApply, remapPositionsOnApply, storageKey])
  useImperativeHandle(ref, () => ({ prepareSave: () => {
    if (!order) return false
    if (dirty) applyOrder(order)
    return true
  } }), [applyOrder, dirty, order])
  const displayedEdges = useMemo(() => {
    const list = edges.map((edge) => ({ ...edge, type: 'removable', data: { ...edge.data, running: runningIds?.includes(edge.source) ?? false, ...(inlineSave && editable ? { remove: (id: string) => { setEdges((current) => current.filter((item) => item.id !== id)); setSelectedEdge('') } } : {}) } }))
    if (!onAdd || !terminalId || !addNode) return list
    return [...list, { id: `${terminalId}-add`, source: terminalId, target: ADD_NODE_ID, targetHandle: `add-${addNode.data.targetSide}`, className: 'ui-flow-edge-add', selectable: false, deletable: false, focusable: false }]
  }, [edges, runningIds, inlineSave, editable, setEdges, setSelectedEdge, terminalId, onAdd, addNode])
  return <section className="ui-flow" aria-label="执行流程图">
    {header ? <div className="ui-flow-case-toolbar">{header}</div> : null}
    {!inlineSave || toolbarExtra ? <div className="ui-flow-toolbar"><div className="ui-flow-toolbar-title"><strong>执行流程</strong><span className="ui-flow-count">{items.length} 个节点</span>{toolbarExtra}</div>
      {!inlineSave ? <Space wrap>
        <Button size="small" disabled={!editable || !selectedEdge} onClick={() => { setEdges((current) => current.filter((edge) => edge.id !== selectedEdge)); setSelectedEdge('') }}>删除连线</Button>
        <Button size="small" disabled={!editable || !dirty} onClick={() => { setEdges(items.slice(1).map((item, index) => ({ id: `${items[index].id}-${item.id}`, source: items[index].id, target: item.id, ...edgeStyle }))); setSelectedEdge('') }}>还原连线</Button>
        <Button size="small" type="primary" loading={applying} disabled={!editable || !dirty || !order} onClick={() => { if (order) applyOrder(order) }}>应用顺序</Button>
      </Space> : null}
    </div> : null}
    <div className="ui-flow-canvas" onKeyDown={(event) => {
      if (event.key !== 'Enter' || (!onOpen && !onSelect)) return
      const nodeId = (event.target as HTMLElement).closest<HTMLElement>('.react-flow__node')?.dataset.id
      if (nodeId) {
        if (nodeId === ADD_NODE_ID) { onAdd?.(); return }
        (onSelect ?? onOpen)?.(nodeId)
      }
    }}>
      <div className="ui-flow-hint">{hint ?? (onSelect ? '点击步骤编辑 · ' : '')}拖动卡片摆放 · 拖动连接点连线 · 选中连线后可删除或拖动端点</div>
      <ReactFlow nodes={displayedNodes} edges={displayedEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onNodesChange={onNodesChange} onEdgesChange={editable ? onEdgesChange : undefined}
        onConnect={editable ? onConnect : undefined} onReconnect={editable ? onReconnect : undefined} edgesReconnectable={editable} nodesConnectable={editable}
        onNodeDragStop={(_, __, allNodes) => savePositions(allNodes)} onEdgeClick={(_, edge) => setSelectedEdge(edge.id)} onPaneClick={() => setSelectedEdge('')}
        onNodeClick={(event, node) => {
          if (node.id === ADD_NODE_ID) {
            // 双击的第二下 detail > 1，避免一次双击追加两张卡片。
            if (event.detail <= 1) onAdd?.()
            return
          }
          onSelect?.(node.id)
        }}
        onNodeDoubleClick={(_, node) => { if (node.id !== ADD_NODE_ID) onOpen?.(node.id) }} deleteKeyCode={editable ? ['Backspace', 'Delete'] : null}
        onBeforeDelete={async ({ edges: deleting }) => ({ nodes: [], edges: deleting })} onEdgesDelete={() => setSelectedEdge('')}
        fitView fitViewOptions={{ padding: 0.06, maxZoom: 1 }} minZoom={0.2} maxZoom={1.5} proOptions={{ hideAttribution: true }}>
        <Background gap={20} size={1} /><Controls showInteractive={false} />
      </ReactFlow>
    </div>
    <div className="ui-flow-footer">{order ? <span>{dirty ? (inlineSave ? '保存后更新执行顺序；离开画布将丢弃未保存的连线。' : '应用后更新执行顺序；离开画布将丢弃未应用的连线。') : '卡片位置仅保存在此浏览器。'}</span> : <Alert type="warning" showIcon message="连线尚未形成完整顺序，请检查断开、分叉或循环。当前执行顺序未改变，离开画布将丢弃未保存的连线。" />}</div>
  </section>
})
