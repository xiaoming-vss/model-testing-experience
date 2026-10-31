import { ReactFlow, Handle, Position, applyNodeChanges, getNodesBounds, getViewportForBounds, type ReactFlowInstance, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { buildTreeFlow, layoutTreeFlow, type TreeFlowNode } from '../utils/caseNameTreeLayout'
import { saveBlob } from '@/shared/utils/download'
import '@/features/ai-testing/styles/functional-import-confirm.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/case-name-tree.css'
import type { CaseNameTreeNode } from '@/features/ai-testing/utils/caseNameTree'
import { buildCaseNameTree, countCaseNameTree, deleteCaseNameTreeNode, renameCaseNameTreeNode, serializeCaseNameTree, updateCategoryCaseNamesContent } from '@/features/ai-testing/utils/caseNameTree'
import { isJsonText } from '@/features/ai-testing/utils/functionalOutput'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { message } from '@/shared/utils/feedback'
import { PictureOutlined } from '@ant-design/icons'
import { ArtifactViewTabs } from './ArtifactViewTabs'
import { Input, Popconfirm, Tag } from 'antd'
import { toBlob } from 'html-to-image'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

export type CaseNamesViewMode = 'json' | 'tree'

function CaseNameTreeNodeView({
  node,
  className,
  editable,
  onRename,
  onDelete,
  onSelect,
  selected,
}: {
  node: CaseNameTreeNode
  className: string
  editable?: boolean
  onRename?: (nodeId: string, title: string) => void
  onDelete?: (nodeId: string) => void
  onSelect?: (nodeId: string) => void
  selected?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState(node.title)
  const canEdit = Boolean(editable && node.kind !== 'root')

  useEffect(() => {
    setDraftTitle(node.title)
  }, [node.title])

  function commitEdit() {
    const nextTitle = draftTitle.trim()
    if (!nextTitle) {
      message.warning('节点名称不能为空')
      setDraftTitle(node.title)
      setEditing(false)
      return
    }

    if (nextTitle !== node.title) {
      onRename?.(node.id, nextTitle)
    }
    setEditing(false)
  }

  return (
    <div role={onSelect ? 'button' : undefined} tabIndex={onSelect ? 0 : undefined} aria-pressed={onSelect ? Boolean(selected) : undefined} onClick={() => onSelect?.(node.id)} onKeyDown={(event) => { if (onSelect && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); onSelect(node.id) } }} className={`${className}${selected ? ' is-selected' : ''}${canEdit ? ' editable' : ''}`} title={node.title}>
      {editing ? (
        <Input
          className="ai-case-name-tree-node-input"
          size="small"
          value={draftTitle}
          autoFocus
          onChange={(event) => setDraftTitle(event.target.value)}
          onBlur={commitEdit}
          onPressEnter={commitEdit}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setDraftTitle(node.title)
              setEditing(false)
            }
          }}
        />
      ) : (
        <span className="ai-case-name-tree-node-label">{node.title}</span>
      )}
      {canEdit && !editing ? (
        <span className="ai-case-name-tree-node-actions">
          <ProjectActionButton action="write"
            type="text"
            size="small"
            operation="edit" iconOnly
            aria-label="编辑节点"
            onClick={(event) => {
              event.stopPropagation()
              setEditing(true)
            }}
          />
          <Popconfirm
            title="确认删除该节点？"
            onConfirm={() => onDelete?.(node.id)}
          >
            <ProjectActionButton action="write"
              danger
              type="text"
              size="small"
              operation="delete" iconOnly
              aria-label="删除节点"
              onClick={(event) => event.stopPropagation()}
            />
          </Popconfirm>
        </span>
      ) : null}
    </div>
  )
}

function FlowTreeNode({ data }: NodeProps<TreeFlowNode>) {
  const node = data.treeNode
  const className = node.kind === 'root' ? 'ai-case-name-tree-root' : `ai-case-name-tree-node ${node.kind === 'testModel' ? 'test-model' : node.kind}`
  return <>
    {node.kind !== 'root' && <Handle type="target" position={Position.Left} className="ai-case-flow-handle" />}
    <CaseNameTreeNodeView node={node} className={className} editable={data.editable} selected={data.selected} onSelect={data.onSelect} onRename={data.onRename} onDelete={data.onDelete} />
    {node.kind !== 'point' && <Handle type="source" position={Position.Right} className="ai-case-flow-handle" />}
  </>
}
const treeNodeTypes = { caseTree: FlowTreeNode }

export function CaseNameTreeView({
  content,
  rootTitle,
  expanded = false,
  editable = false,
  onTreeChange,
  treeData,
  selectedNodeId,
  onNodeSelect,
}: {
  content: string
  rootTitle: string
  expanded?: boolean
  editable?: boolean
  onTreeChange?: (content: string) => void
  treeData?: CaseNameTreeNode
  selectedNodeId?: string
  onNodeSelect?: (id: string) => void
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const sourceTree = treeData ?? buildCaseNameTree(content, rootTitle)
  const prune = (node: CaseNameTreeNode): CaseNameTreeNode => ({ ...node, children: collapsed.has(node.id) ? [] : node.children.map(prune) })
  const tree = treeData && sourceTree ? prune(sourceTree) : sourceTree
  const toggle = treeData ? (id: string) => setCollapsed((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  }) : undefined
  const counts = countCaseNameTree(tree)
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const flowRef = useRef<ReactFlowInstance<TreeFlowNode> | null>(null)
  const [exportingImage, setExportingImage] = useState(false)

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

  const handleRename = (nodeId: string, title: string) => {
    onTreeChange?.(updateCategoryCaseNamesContent(content, nodeId, 'rename', title) ?? serializeCaseNameTree(renameCaseNameTreeNode(tree, nodeId, title)))
  }
  const handleDelete = (nodeId: string) => {
    onTreeChange?.(updateCategoryCaseNamesContent(content, nodeId, 'delete') ?? serializeCaseNameTree(deleteCaseNameTreeNode(tree, nodeId)))
  }

  return (
    <div className={treeData ? 'ai-case-tree-shell' : 'ai-case-tree-passthrough'}>

      <div title={treeData ? '滚轮上下浏览，Ctrl + 滚轮缩放图谱，点击节点查看用例' : '滚轮上下浏览，Ctrl + 滚轮缩放图谱'} className={`ai-case-name-tree${expanded ? ' expanded' : ''}${editable ? ' editable' : ''}`}>
      {treeData ? null : <div className="ai-case-name-tree-stats">
        <Tag color="green">model {counts.models}</Tag><Tag color="cyan">test_model {counts.testModels}</Tag><Tag color="blue">test_points {counts.testPoints}</Tag>
        <ProjectActionButton action="write" className="ai-case-name-tree-export" size="small" icon={<PictureOutlined />} loading={exportingImage} onClick={handleSaveTreeImage}>保存图片</ProjectActionButton>
      </div>}
      <CaseTreeFlow tree={tree} selectedNodeId={selectedNodeId} editable={editable} onSelect={onNodeSelect} onToggle={toggle} onRename={handleRename} onDelete={handleDelete} canvasRef={canvasRef} flowRef={flowRef} />
      </div>

    </div>
  )
}

function CaseTreeFlow({ tree, selectedNodeId, editable, onSelect, onToggle, onRename, onDelete, canvasRef, flowRef }: {
  tree: CaseNameTreeNode; selectedNodeId?: string; editable: boolean; onSelect?: (id: string) => void; onToggle?: (id: string) => void
  onRename: (id: string, title: string) => void; onDelete: (id: string) => void
  canvasRef: React.RefObject<HTMLDivElement | null>; flowRef: React.RefObject<ReactFlowInstance<TreeFlowNode> | null>
}) {
  const graph = useMemo(() => buildTreeFlow(tree, selectedNodeId, editable, onSelect, onRename, onDelete, onToggle), [tree, selectedNodeId, editable, onSelect, onRename, onDelete, onToggle])
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
  return <div ref={canvasRef} className="ai-case-flow-canvas">
    <ReactFlow nodes={nodes} edges={graph.edges} nodeTypes={treeNodeTypes} onNodesChange={onNodesChange} onInit={instance => {
      flowRef.current = instance
      const firstPoint = instance.getNodes().find(node => node.data.treeNode.kind === 'point')
      if (firstPoint && canvasRef.current) {
        const x = Math.min(0, canvasRef.current.clientWidth - firstPoint.position.x - (firstPoint.measured?.width ?? 360) - 24)
        void instance.setViewport({ x, y: 0, zoom: 1 })
      }
    }}
      nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} deleteKeyCode={null} minZoom={0.5} maxZoom={1.5}
      panOnScroll zoomOnScroll={false} zoomActivationKeyCode="Control" proOptions={{ hideAttribution: true }} />
  </div>
}

export function CaseNamesResultView({
  content,
  rootTitle,
  expanded = false,
  activeView,
  onViewChange,
}: {
  content: string
  rootTitle: string
  expanded?: boolean
  activeView?: CaseNamesViewMode
  onViewChange?: (view: CaseNamesViewMode) => void
}) {
  return (
    <ArtifactViewTabs jsonCopyText={content}
      className={`ai-case-names-inner-tabs${expanded ? ' expanded' : ''}`}
      size="small"
      activeKey={activeView}
      onChange={(key) => onViewChange?.(key as CaseNamesViewMode)}
      items={[
        {
          key: 'tree',
          label: '可视化',
          children: <CaseNameTreeView content={content} rootTitle={rootTitle} expanded={expanded} />,
        },
        {
          key: 'json',
          label: 'json',
          children: isJsonText(content) ? (
            <JsonEditor value={content} showCopy={false} readOnly foldable minHeight={expanded ? 520 : 240} />
          ) : (
            <pre className="ai-task-code-block">{content}</pre>
          ),
        },
      ]}
    />
  )
}
