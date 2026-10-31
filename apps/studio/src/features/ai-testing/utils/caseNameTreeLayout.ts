import dagre from '@dagrejs/dagre'
import type { Edge, Node } from '@xyflow/react'
import type { CaseNameTreeNode } from './caseNameTree'

export type TreeFlowData = { treeNode: CaseNameTreeNode; selected: boolean; editable: boolean; onSelect?: (id: string) => void; onRename: (id: string, title: string) => void; onDelete: (id: string) => void }
export type TreeFlowNode = Node<TreeFlowData, 'caseTree'>

export function buildTreeFlow(tree: CaseNameTreeNode, selectedId: string | undefined, editable: boolean, onSelect: ((id: string) => void) | undefined, onRename: (id: string, title: string) => void, onDelete: (id: string) => void, onToggle?: (id: string) => void) {
  const nodes: TreeFlowNode[] = []
  const edges: Edge[] = []
  function visit(node: CaseNameTreeNode, parent?: CaseNameTreeNode) {
    nodes.push({ id: node.id, type: 'caseTree', position: { x: 0, y: 0 }, data: { treeNode: node, selected: node.id === selectedId, editable, onSelect: node.kind === 'point' ? onSelect : node.kind === 'root' ? undefined : onToggle, onRename, onDelete } })
    if (parent) edges.push({ id: `${parent.id}->${node.id}`, source: parent.id, target: node.id, type: 'default', style: { stroke: parent.kind === 'root' ? 'var(--app-graph-edge-primary)' : parent.kind === 'model' ? 'var(--app-graph-edge-reference)' : 'var(--app-graph-edge-muted)', strokeWidth: parent.kind === 'testModel' ? 1.8 : 2 } })
    node.children.forEach(child => visit(child, node))
  }
  visit(tree)
  return { nodes, edges }
}

export function layoutTreeFlow(nodes: TreeFlowNode[], edges: Edge[]): TreeFlowNode[] {
  const graph = new dagre.graphlib.Graph()
  graph.setGraph({ rankdir: 'LR', ranksep: 86, nodesep: 10, marginx: 16, marginy: 16 })
  graph.setDefaultEdgeLabel(() => ({}))
  nodes.forEach(node => graph.setNode(node.id, { width: node.measured?.width || (node.data.treeNode.kind === 'point' ? 360 : 160), height: node.measured?.height || 38 }))
  edges.forEach(edge => graph.setEdge(edge.source, edge.target))
  dagre.layout(graph)
  // Preserve artifact order and center each parent on its children. Dagre supplies
  // the horizontal ranks; measured heights make wrapped labels safe vertically.
  const children = new Map<string, string[]>()
  edges.forEach(edge => children.set(edge.source, [...(children.get(edge.source) ?? []), edge.target]))
  const subtreeHeight = new Map<string, number>()
  const measure = (id: string): number => {
    const descendants = children.get(id) ?? []
    const childHeight = descendants.reduce((sum, child) => sum + measure(child), 0) + Math.max(0, descendants.length - 1) * 10
    const height = Math.max(graph.node(id).height, childHeight)
    subtreeHeight.set(id, height)
    return height
  }
  const yPositions = new Map<string, number>()
  const place = (id: string, top: number) => {
    const descendants = children.get(id) ?? []
    const height = subtreeHeight.get(id)!
    yPositions.set(id, top + (height - graph.node(id).height) / 2)
    const childHeight = descendants.reduce((sum, child) => sum + subtreeHeight.get(child)!, 0) + Math.max(0, descendants.length - 1) * 10
    let cursor = top + (height - childHeight) / 2
    descendants.forEach(child => { place(child, cursor); cursor += subtreeHeight.get(child)! + 10 })
  }
  if (nodes[0]) { measure(nodes[0].id); place(nodes[0].id, 16) }
  const rankLeft = new Map<number, number>()
  nodes.forEach(node => {
    const { rank, x, width } = graph.node(node.id)
    rankLeft.set(rank, Math.min(rankLeft.get(rank) ?? Infinity, x - width / 2))
  })
  return nodes.map(node => {
    const { rank } = graph.node(node.id)
    return { ...node, position: { x: rankLeft.get(rank) ?? 16, y: yPositions.get(node.id) ?? 16 } }
  })
}
