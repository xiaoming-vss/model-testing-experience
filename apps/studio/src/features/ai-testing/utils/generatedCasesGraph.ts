import type { Edge, Node } from '@xyflow/react'
import type { GeneratedCaseEntry, GeneratedCasesModel } from './generatedCasesModel'

export type GeneratedCasesSelection =
  | { kind: 'overview' }
  | { kind: 'module'; id: string }
  | { kind: 'scene'; id: string }
  | { kind: 'case'; key: string }

export type GeneratedCasesNodeData =
  | { kind: 'root'; title: string; count: number; selected: boolean }
  | { kind: 'module'; id: string; title: string; count: number; selected: boolean }
  | { kind: 'scene'; id: string; title: string; count: number; expanded: boolean; selected: boolean }
  | { kind: 'case'; entry: GeneratedCaseEntry }
  | { kind: 'detail'; entry: GeneratedCaseEntry }

export type GeneratedCasesFlowNode = Node<GeneratedCasesNodeData>
export type GeneratedCasesFlowEdge = Edge

export type GeneratedCasesGraphInput = {
  model: GeneratedCasesModel
  rootTitle: string
  expandedSceneIds: ReadonlySet<string>
  selection: GeneratedCasesSelection
}

const ROOT_WIDTH = 220
const MODULE_WIDTH = 180
const SCENE_WIDTH = 170
const CASE_COLUMN_WIDTH = 430
export const GENERATED_CASE_DETAIL_HEIGHT = 560
export const GENERATED_CASE_CANVAS_MARGIN = 16
const RANK_GAP = 96
const SIBLING_GAP = 12
const CASE_GAP = 10
const ROOT_X = GENERATED_CASE_CANVAS_MARGIN
const MODULE_X = ROOT_X + ROOT_WIDTH + RANK_GAP
const SCENE_X = MODULE_X + MODULE_WIDTH + RANK_GAP
const CASE_X = SCENE_X + SCENE_WIDTH + RANK_GAP
export const GENERATED_CASES_STAGE_WIDTH = CASE_X + CASE_COLUMN_WIDTH + GENERATED_CASE_CANVAS_MARGIN

export function generatedCaseNodeId(entry: GeneratedCaseEntry) {
  return `case-${entry.testCase.sourceIndex}`
}

function nodeHeight(data: GeneratedCasesNodeData) {
  if (data.kind === 'detail') return GENERATED_CASE_DETAIL_HEIGHT
  if (data.kind === 'case') return 46
  return 40
}

export function buildGeneratedCasesGraph(input: GeneratedCasesGraphInput): {
  nodes: GeneratedCasesFlowNode[]
  edges: GeneratedCasesFlowEdge[]
  stageHeight: number
} {
  const { model, expandedSceneIds, selection } = input
  const nodes: GeneratedCasesFlowNode[] = []
  const edges: GeneratedCasesFlowEdge[] = []

  const root: GeneratedCasesFlowNode = {
    id: 'graph-root',
    type: 'generated-case',
    position: { x: 0, y: 0 },
    data: { kind: 'root', title: input.rootTitle || '完整用例', count: model.entries.length, selected: selection.kind === 'overview' },
  }
  nodes.push(root)

  model.modules.forEach((module) => {
    nodes.push({
      id: module.id,
      type: 'generated-case',
      position: { x: 0, y: 0 },
      data: { kind: 'module', id: module.id, title: module.title, count: module.entries.length, selected: selection.kind === 'module' && selection.id === module.id },
    })
    edges.push({ id: `${root.id}->${module.id}`, source: root.id, target: module.id, style: { stroke: 'var(--app-graph-edge-primary)', strokeWidth: 2 } })

    module.scenes.forEach((scene) => {
      const expanded = expandedSceneIds.has(scene.id)
      nodes.push({
        id: scene.id,
        type: 'generated-case',
        position: { x: 0, y: 0 },
        data: { kind: 'scene', id: scene.id, title: scene.title, count: scene.cases.length, expanded, selected: selection.kind === 'scene' && selection.id === scene.id },
      })
      edges.push({ id: `${module.id}->${scene.id}`, source: module.id, target: scene.id, style: { stroke: 'var(--app-graph-edge-reference)', strokeWidth: 2 } })
      if (!expanded) return
      scene.cases.forEach((entry) => {
        const id = generatedCaseNodeId(entry)
        const selected = selection.kind === 'case' && selection.key === entry.key
        nodes.push({
          id,
          type: 'generated-case',
          position: { x: 0, y: 0 },
          data: selected ? { kind: 'detail', entry } : { kind: 'case', entry },
        })
        edges.push({
          id: `${scene.id}->${id}`,
          source: scene.id,
          target: id,
          style: { stroke: 'var(--app-graph-edge-muted)', strokeWidth: 1.8 },
        })
      })
    })
  })

  return layoutGraph(nodes, edges)
}

type TreeNode = { id: string; children: TreeNode[] }

function layoutGraph(nodes: GeneratedCasesFlowNode[], edges: GeneratedCasesFlowEdge[]) {
  const nodeById = new Map(nodes.map(node => [node.id, node]))
  const childIds = new Map<string, string[]>()
  edges.forEach((edge) => {
    if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) return
    childIds.set(edge.source, [...(childIds.get(edge.source) ?? []), edge.target])
  })

  const buildTree = (id: string, path = new Set<string>()): TreeNode | undefined => {
    if (path.has(id)) return undefined
    const node = nodeById.get(id)
    if (!node) return undefined
    const nextPath = new Set(path).add(id)
    return { id, children: (childIds.get(id) ?? []).map(child => buildTree(child, nextPath)).filter((child): child is TreeNode => Boolean(child)) }
  }
  const tree = buildTree('graph-root')
  if (!tree) return { nodes, edges, stageHeight: 0 }

  const heightById = new Map(nodes.map(node => [node.id, nodeHeight(node.data)]))
  const subtreeHeight = new Map<string, number>()
  const measure = (treeNode: TreeNode): number => {
    const own = heightById.get(treeNode.id) ?? 40
    const childHeights = treeNode.children.map(measure)
    const gap = treeNode.children.length > 1
      ? Math.max(...treeNode.children.map(child => nodeById.get(child.id)?.data.kind === 'case' || nodeById.get(child.id)?.data.kind === 'detail' ? CASE_GAP : SIBLING_GAP))
      : 0
    const childBlock = childHeights.reduce((sum, height) => sum + height, 0) + Math.max(0, treeNode.children.length - 1) * gap
    const height = Math.max(own, childBlock)
    subtreeHeight.set(treeNode.id, height)
    return height
  }
  measure(tree)

  const positions = new Map<string, { x: number; y: number }>()
  const place = (treeNode: TreeNode, top: number, x: number) => {
    const own = heightById.get(treeNode.id) ?? 40
    const height = subtreeHeight.get(treeNode.id) ?? own
    positions.set(treeNode.id, { x, y: top + (height - own) / 2 })
    if (!treeNode.children.length) return
    const gap = Math.max(...treeNode.children.map(child => nodeById.get(child.id)?.data.kind === 'case' || nodeById.get(child.id)?.data.kind === 'detail' ? CASE_GAP : SIBLING_GAP))
    const childHeights = treeNode.children.map(child => subtreeHeight.get(child.id) ?? 0)
    const childBlock = childHeights.reduce((sum, childHeight) => sum + childHeight, 0) + Math.max(0, treeNode.children.length - 1) * gap
    let cursor = top + (height - childBlock) / 2
    treeNode.children.forEach((child, index) => {
      const childNode = nodeById.get(child.id)
      const childX = childNode?.data.kind === 'module'
        ? MODULE_X
        : childNode?.data.kind === 'scene'
          ? SCENE_X
          : CASE_X
      place(child, cursor, childX)
      cursor += (childHeights[index] ?? 0) + gap
    })
  }
  place(tree, GENERATED_CASE_CANVAS_MARGIN, ROOT_X)

  const maxBottom = Math.max(
    GENERATED_CASE_CANVAS_MARGIN + (subtreeHeight.get('graph-root') ?? 40),
    ...nodes.map((node) => {
      const position = positions.get(node.id)
      return position ? position.y + (heightById.get(node.id) ?? 40) : 0
    }),
  )

  return {
    nodes: nodes.map((node) => {
      const position = positions.get(node.id) ?? { x: GENERATED_CASE_CANVAS_MARGIN, y: GENERATED_CASE_CANVAS_MARGIN }
      return {
        ...node,
        position,
        // 不设置 node.width：连线的锚点是 React Flow 节点盒，树节点内部卡片
        // 使用 max-content。让 React Flow 测量实际宽度，连线才会贴到可见卡片边缘。
        height: heightById.get(node.id) ?? 40,
        style: { ...node.style, maxWidth: '430px', pointerEvents: 'all' as const },
      }
    }),
    edges,
    stageHeight: maxBottom + GENERATED_CASE_CANVAS_MARGIN,
  }
}

