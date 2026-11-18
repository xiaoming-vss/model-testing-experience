import { ReactFlow, Handle, Position, applyNodeChanges, getNodesBounds, getViewportForBounds, type ReactFlowInstance, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { buildTreeFlow, layoutTreeFlow, type TreeFlowNode } from '../utils/caseNameTreeLayout'
import { saveBlob } from '@/shared/utils/download'
import type { CaseNameTreeNode } from '@/features/ai-testing/utils/caseNameTree'
import { buildCaseNameTree, countCaseNameTree } from '@/features/ai-testing/utils/caseNameTree'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import artifactStyles from '@/shared/styles/run-view.module.css'
import { cx } from '@/shared/utils/cx'
import { message } from '@/shared/utils/feedback'
import { DeleteOutlined, LinkOutlined, PictureOutlined } from '@ant-design/icons'
import { Button, Popover, Tag } from 'antd'
import { toBlob } from 'html-to-image'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

const RelationPopoverContext = createContext<{
  openId: string | null
  setOpenId: (id: string | null) => void
}>({ openId: null, setOpenId: () => undefined })

function CaseNameTreeNodeView({ node, className, onSelect, selected, selectionTick = 0 }: {
  node: CaseNameTreeNode; className: string; onSelect?: (nodeId: string) => void; selected?: boolean; selectionTick?: number
}) {
  return <div role={onSelect ? 'button' : undefined} tabIndex={onSelect ? 0 : undefined} aria-pressed={onSelect ? Boolean(selected) : undefined} onClick={() => onSelect?.(node.id)} onKeyDown={event => { if (onSelect && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); onSelect(node.id) } }} className={`${className}${selected ? ` is-selected motion-${selectionTick % 2}` : ''}`} title={node.title}>
    <span className="ai-case-name-tree-node-label">{node.title}</span>
  </div>
}

function pruneTree(node: CaseNameTreeNode, collapsed: Set<string>): CaseNameTreeNode {
  return { ...node, children: collapsed.has(node.id) ? [] : node.children.map((child) => pruneTree(child, collapsed)) }
}

function FlowTreeNode({ data }: NodeProps<TreeFlowNode>) {
  const node = data.treeNode
  const baseClassName = node.kind === 'root' ? 'ai-case-name-tree-root' : `ai-case-name-tree-node ${node.kind === 'testModel' ? 'test-model' : node.kind}`
  const className = `${baseClassName}${data.highlighted ? ' is-related' : ''}`
  const hasRelations = Boolean(data.renderRelations)
  const { openId, setOpenId } = useContext(RelationPopoverContext)
  const relationOpen = openId === node.id
  const relationTrigger = hasRelations ? (
    <Popover
      trigger="click"
      placement={node.kind === 'point' ? 'rightTop' : 'right'}
      destroyOnHidden
      open={relationOpen}
      onOpenChange={open => {
        if (open) setOpenId(node.id)
        else if (relationOpen) setOpenId(null)
      }}
      content={() => data.renderRelations?.(node)}
      classNames={{ root: cx('ai-case-relations-popover', artifactStyles.relationsPopover) }}
    >
      <button
        type="button"
        className={`ai-case-flow-relation-trigger nodrag absolute right-[7px] top-[7px] z-[2] inline-flex cursor-pointer items-center justify-center gap-[3px] rounded-[5px] border border-[var(--app-surface-border)] bg-[var(--app-surface-hover)] p-0 text-[10px] leading-none text-[var(--app-surface-text-muted)] opacity-0 pointer-events-none transition-[opacity,color,border-color,background-color] duration-150 group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100 hover:border-[var(--app-accent)] hover:bg-[var(--app-accent-surface)] hover:text-[var(--app-accent)] focus-visible:border-[var(--app-accent)] focus-visible:bg-[var(--app-accent-surface)] focus-visible:text-[var(--app-accent)] [@media(hover:none)]:pointer-events-auto [@media(hover:none)]:opacity-100 [&_.anticon]:text-[9px] ${node.kind === 'point' ? 'is-point w-auto px-1.5 text-[var(--app-accent)]' : 'h-5 w-5'}`}
        title="查看关联"
        aria-label={`查看关联：${node.title}`}
        onClick={event => event.stopPropagation()}
      >
        <LinkOutlined aria-hidden />
        {node.kind === 'point' ? '查看关联' : null}
      </button>
    </Popover>
  ) : null
  return <>
    {node.kind !== 'root' && <Handle type="target" position={Position.Left} className="ai-case-flow-handle" />}
    <div className={`ai-case-flow-node-shell group relative inline-flex max-w-[360px]${data.onDelete ? ' has-delete' : ''}${hasRelations ? ' has-relation' : ''}`}>
      <CaseNameTreeNodeView node={node} className={className} selected={data.selected} selectionTick={data.selectionTick} onSelect={data.onSelect} />
      {relationTrigger}
      {data.onDelete ? <Button type="text" size="small" className="ai-case-name-tree-node-delete nodrag" icon={<DeleteOutlined aria-hidden />} title="删除测试点" aria-label={`删除测试点：${node.title}`} onClick={() => data.onDelete?.(node.id)} /> : null}
    </div>
    {node.kind !== 'point' && <Handle type="source" position={Position.Right} className="ai-case-flow-handle" />}
  </>
}
const treeNodeTypes = { caseTree: FlowTreeNode }

export function CaseNameTreeView({
  content,
  rootTitle,
  expanded = false,
  treeData,
  selectedNodeId,
  selectionTick = 0,
  onNodeSelect,
  onDeleteNode,
  renderRelations,
  hideStats = false,
  defaultCollapsed,
  revealNodeIds,
  highlightedNodeIds,
  showSaveImage = false,
  toolbarHint,
  fitViewOnMount = false,
}: {
  content: string
  rootTitle: string
  expanded?: boolean
  treeData?: CaseNameTreeNode
  selectedNodeId?: string
  /** 每次点选测试点递增，用于重播同一节点的选中动效。 */
  selectionTick?: number
  onNodeSelect?: (id: string) => void
  /** 仅在可编辑候选中提供；传入后每个测试点末尾显示删除操作。 */
  onDeleteNode?: (id: string) => void
  /** 传入后每个节点显示「查看关联」，内容由调用方根据节点生成。 */
  renderRelations?: (node: CaseNameTreeNode) => ReactNode
  /** 隐藏 model/test_model/test_points 统计标签，只保留图片导出。 */
  hideStats?: boolean
  /** 仅在 treeData 模式下生效：初始折叠的节点。 */
  defaultCollapsed?: Iterable<string>
  /** 仅在 treeData 模式下生效：这些节点会从折叠集合中移除。 */
  revealNodeIds?: string[]
  /** 仅在 treeData 模式下生效：高亮这些节点。 */
  highlightedNodeIds?: string[]
  /** treeData 模式下也显示保存图片按钮。 */
  showSaveImage?: boolean
  /** treeData 模式下工具栏提示文案。 */
  toolbarHint?: string
  /** 首次布局后自动缩放到完整树，适合以总览为目的的页面。 */
  fitViewOnMount?: boolean
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set(defaultCollapsed))
  const [openRelationId, setOpenRelationId] = useState<string | null>(null)
  useEffect(() => {
    if (!revealNodeIds?.length) return
    setCollapsed(current => {
      const next = new Set(current)
      let changed = false
      revealNodeIds.forEach(id => { if (next.delete(id)) changed = true })
      return changed ? next : current
    })
  }, [revealNodeIds])
  // 树构建、折叠裁剪、计数和布局都按输入 memo：每次父级重渲染都重跑一遍 dagre 会明显拖慢大树。
  const sourceTree = useMemo(() => treeData ?? buildCaseNameTree(content, rootTitle), [content, rootTitle, treeData])
  const tree = useMemo(() => treeData && sourceTree ? pruneTree(sourceTree, collapsed) : sourceTree, [collapsed, sourceTree, treeData])
  const toggle = useMemo(() => treeData ? (id: string) => setCollapsed((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  }) : undefined, [treeData])
  const counts = useMemo(() => tree ? countCaseNameTree(tree) : null, [tree])
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const flowRef = useRef<ReactFlowInstance<TreeFlowNode> | null>(null)
  const [exportingImage, setExportingImage] = useState(false)

  useEffect(() => {
    if (!revealNodeIds?.length) return
    const timer = window.setTimeout(() => {
      flowRef.current?.fitView({ padding: 0.18, maxZoom: 1, duration: 260 })
    }, 90)
    return () => window.clearTimeout(timer)
  }, [revealNodeIds])

  async function handleSaveTreeImage() {
    const canvas = canvasRef.current
    if (!canvas) return
    setExportingImage(true)
    try {
      const viewport = canvas.querySelector<HTMLElement>('.react-flow__viewport')
      const flow = flowRef.current
      if (!viewport || !flow) throw new Error('图谱尚未准备完成')
      const bounds = getNodesBounds(flow.getNodes())
      const width = Math.ceil(bounds.width + 48)
      const height = Math.ceil(bounds.height + 48)
      const transform = getViewportForBounds(bounds, width, height, 1, 1, 0)
      const canvasStyle = getComputedStyle(canvas)
      const blob = await toBlob(viewport, {
        pixelRatio: 2, skipFonts: true, width, height,
        style: { width: `${width}px`, height: `${height}px`, transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.zoom})`, background: canvasStyle.getPropertyValue('--graph-export-background').trim() },
      })
      if (!blob) throw new Error('导出内容为空')
      saveBlob(blob, `${rootTitle}-测试点树图.png`)
      message.success('图片已保存')
    } catch {
      message.error('图片导出失败，请重试')
    } finally {
      setExportingImage(false)
    }
  }

  if (!tree) {
    return <JsonEditor value={content} showCopy={false} readOnly foldable minHeight={expanded ? 560 : 260} />
  }

  return (
    <div className={`${treeData ? 'ai-case-tree-shell' : 'ai-case-tree-passthrough'} contents`}>

      <div title={treeData ? '滚轮上下浏览，Ctrl + 滚轮缩放图谱，点击节点查看用例' : '滚轮上下浏览，Ctrl + 滚轮缩放图谱'} className={`ai-case-name-tree flex flex-col overflow-hidden rounded-[14px] border border-[var(--app-frame-divider-soft)] bg-[radial-gradient(circle_at_24px_24px,var(--app-graph-canvas-glow),transparent_26px),var(--app-graph-canvas-bg)] p-3 ${expanded ? 'expanded min-h-[min(58vh,560px)]' : 'min-h-[260px]'}`}>
      {treeData
        ? (showSaveImage || toolbarHint ? <div className="ai-case-name-tree-stats is-minimal relative z-[2] mb-3.5 flex flex-none items-center gap-2 [&_.ant-tag]:m-0 [&_.ant-tag]:rounded-full">
          {toolbarHint ? <span className="ai-case-name-tree-hint text-[11px] leading-[1.5] text-[var(--app-surface-text-muted)]">{toolbarHint}</span> : null}
          {showSaveImage ? <ProjectActionButton action="write" className="ai-case-name-tree-export ml-auto flex-none" size="small" icon={<PictureOutlined />} loading={exportingImage} onClick={handleSaveTreeImage}>保存图片</ProjectActionButton> : null}
        </div> : null)
        : <div className={`ai-case-name-tree-stats relative z-[2] mb-3.5 flex flex-none items-center [&_.ant-tag]:m-0 [&_.ant-tag]:rounded-full${hideStats ? ' is-minimal gap-2' : ' gap-1.5'}`}>
          {hideStats ? <span className="ai-case-name-tree-hint text-[11px] leading-[1.5] text-[var(--app-surface-text-muted)]">点击节点上的「查看关联」查看依据</span> : <>
            <Tag color="green">model {counts?.models ?? 0}</Tag><Tag color="cyan">test_model {counts?.testModels ?? 0}</Tag><Tag color="blue">test_points {counts?.testPoints ?? 0}</Tag>
          </>}
          <ProjectActionButton action="write" className="ai-case-name-tree-export ml-auto flex-none" size="small" icon={<PictureOutlined />} loading={exportingImage} onClick={handleSaveTreeImage}>保存图片</ProjectActionButton>
        </div>}
      <RelationPopoverContext.Provider value={{ openId: openRelationId, setOpenId: setOpenRelationId }}>
        <CaseTreeFlow tree={tree} selectedNodeId={selectedNodeId} selectionTick={selectionTick} onSelect={onNodeSelect} onToggle={toggle} onDelete={onDeleteNode} renderRelations={renderRelations} highlightedNodeIds={highlightedNodeIds} fitViewOnMount={fitViewOnMount} canvasRef={canvasRef} flowRef={flowRef} />
      </RelationPopoverContext.Provider>
      </div>

    </div>
  )
}

function CaseTreeFlow({ tree, selectedNodeId, selectionTick, onSelect, onToggle, onDelete, renderRelations, highlightedNodeIds, fitViewOnMount = false, canvasRef, flowRef }: {
  tree: CaseNameTreeNode; selectedNodeId?: string; selectionTick?: number; onSelect?: (id: string) => void; onToggle?: (id: string) => void
  onDelete?: (id: string) => void; renderRelations?: (node: CaseNameTreeNode) => ReactNode; highlightedNodeIds?: string[]; fitViewOnMount?: boolean
  canvasRef: React.RefObject<HTMLDivElement | null>; flowRef: React.RefObject<ReactFlowInstance<TreeFlowNode> | null>
}) {
  const highlightedIds = useMemo(() => new Set(highlightedNodeIds), [highlightedNodeIds])
  const graph = useMemo(() => buildTreeFlow(tree, selectedNodeId, onSelect, onToggle, onDelete, selectionTick, renderRelations, highlightedIds), [tree, selectedNodeId, selectionTick, onSelect, onToggle, onDelete, renderRelations, highlightedIds])
  const [nodes, setNodes] = useState(() => layoutTreeFlow(graph.nodes, graph.edges))
  useEffect(() => {
    setNodes(current => {
      const previous = new Map(current.map(node => [node.id, node]))
      return layoutTreeFlow(graph.nodes.map(node => ({ ...node, measured: previous.get(node.id)?.measured })), graph.edges)
    })
  }, [graph])
  const onNodesChange = useCallback<NonNullable<React.ComponentProps<typeof ReactFlow<TreeFlowNode>>['onNodesChange']>>(changes => {
    setNodes(current => {
      const updated = applyNodeChanges(changes, current)
      return changes.some(change => change.type === 'dimensions' && change.dimensions) ? layoutTreeFlow(updated, graph.edges) : updated
    })
  }, [graph.edges])
  const positioned = useRef(false)
  const positionRoot = useCallback((currentNodes: TreeFlowNode[], flow: ReactFlowInstance<TreeFlowNode> | null) => {
    const root = currentNodes.find(node => node.data.treeNode.kind === 'root')
    const canvas = canvasRef.current
    if (positioned.current || !root || !canvas || !flow || !currentNodes.every(node => node.measured?.width && node.measured?.height)) return
    positioned.current = true
    if (fitViewOnMount) {
      void flow.fitView({ padding: 0.16, maxZoom: 1, duration: 0 })
      return
    }
    void flow.setViewport({ x: 24 - root.position.x, y: canvas.clientHeight / 2 - root.position.y - (root.measured?.height ?? 0) / 2, zoom: 1 })
  }, [canvasRef, fitViewOnMount])
  useEffect(() => { positionRoot(nodes, flowRef.current) }, [nodes, flowRef, positionRoot])
  return <div ref={canvasRef} className="ai-case-flow-canvas">
    <ReactFlow nodes={nodes} edges={graph.edges} nodeTypes={treeNodeTypes} onNodesChange={onNodesChange} onInit={instance => {
      flowRef.current = instance
      positionRoot(instance.getNodes(), instance)
    }}
      nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} deleteKeyCode={null} minZoom={0.5} maxZoom={1.5}
      panOnScroll zoomOnScroll={false} zoomActivationKeyCode="Control" proOptions={{ hideAttribution: true }} />
  </div>
}
