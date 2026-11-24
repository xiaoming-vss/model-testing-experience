import type { Edge, Node } from '@xyflow/react'
import type { TraceableGap, TraceableIssue, TraceableModule, TraceablePoint } from './traceablePointsModel'

export type TraceableMode = 'points' | 'issues' | 'gaps'

export type TraceableSelection =
  | { kind: 'overview' }
  | { kind: 'module'; id: string }
  | { kind: 'scene'; id: string }
  | { kind: 'point'; id: string }
  | { kind: 'gap'; id: string }
  | { kind: 'issue'; index: number }

export type TraceableNodeData =
  | { kind: 'root'; title: string; pointCount: number; selected: boolean }
  | { kind: 'module'; id: string; title: string; pointCount: number; sceneCount: number; selected: boolean }
  | { kind: 'scene'; id: string; title: string; pointCount: number; selected: boolean; highlighted: boolean; expanded: boolean }
  | { kind: 'point'; point: TraceablePoint; selected: boolean; highlighted: boolean }
  | { kind: 'detail'; point: TraceablePoint }
  | { kind: 'gap'; gap: TraceableGap }
  | { kind: 'review'; reviewStatus: string; reviewLabel: string; pointCount: number; gapCount: number; moduleCount: number }
  | { kind: 'issue'; issue: TraceableIssue; targetLabel: string; targetKind: 'point' | 'gap' | 'missing' }

export type TraceableFlowNode = Node<TraceableNodeData>
export type TraceableFlowEdge = Edge

export type TraceableGraphInput = {
  modules: TraceableModule[]
  rootTitle: string
  mode: TraceableMode
  expandedSceneIds: ReadonlySet<string>
  selection: TraceableSelection
  activeGap?: TraceableGap
  activeIssue?: TraceableIssue
  issueCount: number
  totalPoints: number
  totalGaps: number
  reviewStatus: string
  reviewLabel: string
}

const RANK_GAP = 96
const MARGIN = 16
const SIBLING_GAP = 12
const POINT_GAP = 10

function widthForText(title: string, min: number, max: number) {
  return Math.min(max, Math.max(min, title.length * 12 + 24))
}

function pointKey(id: string) {
  return `point-${id}`
}

function gapKey(id: string) {
  return `gap-${id}`
}

function issueKey(index: number) {
  return `issue-${index}`
}

function issueTargetLabel(issue: TraceableIssue | undefined, point?: TraceablePoint, gap?: TraceableGap): string {
  if (point) return point.name
  if (gap) return gap.id
  if (!issue || issue.targetType === 'missing' || !issue.targetId) return '遗漏项'
  if (issue.targetType === 'coverageGap') return '未定位的覆盖缺口'
  return '未定位的测试点'
}

function nodeWidth(node: TraceableFlowNode) {
  switch (node.data.kind) {
    case 'root': return 220
    case 'module':
    case 'scene': return widthForText(node.data.title, 140, 260)
    case 'gap':
    case 'issue': return 360
    case 'review': return 340
    default: return 340
  }
}

function nodeHeight(node: TraceableFlowNode) {
  switch (node.data.kind) {
    case 'point': return 46
    case 'detail': return 300
    case 'gap': return 430
    case 'review': return 300
    case 'issue': return 300
    case 'root':
    case 'module':
    case 'scene': {
      const charactersPerLine = Math.max(6, Math.floor((nodeWidth(node) - 24) / 12))
      return node.data.title.length > charactersPerLine ? 50 : 38
    }
    default: return 38
  }
}

export function buildTraceablePointsGraph(input: TraceableGraphInput): {
  nodes: TraceableFlowNode[]
  edges: TraceableFlowEdge[]
  stageWidth: number
  stageHeight: number
  pointColumnX: number
} {
  const showPointBranches = input.mode === 'points'
  const targetPoint = input.mode === 'issues' && input.activeIssue?.pointId
    ? input.modules.flatMap(module => module.points).find(point => point.id === input.activeIssue?.pointId)
    : undefined
  const targetGap = input.mode === 'issues' && input.activeIssue?.gapId
    ? input.activeGap
    : undefined
  const highlightedSceneIds = new Set(input.activeGap?.relatedSceneIds ?? [])
  const highlightedPointIds = new Set(input.activeGap?.relatedPointIds ?? [])
  if (targetPoint) {
    highlightedSceneIds.add(targetPoint.sceneId)
    highlightedPointIds.add(targetPoint.id)
  }

  const selectedPointId = input.selection.kind === 'point' ? input.selection.id : undefined
  const nodes: TraceableFlowNode[] = []
  const edges: TraceableFlowEdge[] = []

  const root: TraceableFlowNode = {
    id: 'graph-root',
    type: 'traceable',
    position: { x: MARGIN, y: MARGIN },
    data: { kind: 'root', title: input.rootTitle || '测试点', pointCount: input.totalPoints, selected: input.selection.kind === 'overview' },
  }
  nodes.push(root)

  input.modules.forEach((module) => {
    const moduleNode: TraceableFlowNode = {
      id: module.id,
      type: 'traceable',
      position: { x: 0, y: 0 },
      data: {
        kind: 'module',
        id: module.id,
        title: module.title,
        pointCount: module.points.length,
        sceneCount: module.scenes.length,
        selected: input.selection.kind === 'module' && input.selection.id === module.id,
      },
    }
    nodes.push(moduleNode)
    edges.push({
      id: `${root.id}->${module.id}`,
      source: root.id,
      target: module.id,
      style: { stroke: 'var(--app-graph-edge-primary)', strokeWidth: 2 },
    })

    module.scenes.forEach((scene) => {
      const expanded = showPointBranches
        ? input.expandedSceneIds.has(scene.id)
        : targetPoint?.sceneId === scene.id
      const sceneNode: TraceableFlowNode = {
        id: scene.id,
        type: 'traceable',
        position: { x: 0, y: 0 },
        data: {
          kind: 'scene',
          id: scene.id,
          title: scene.title,
          pointCount: scene.points.length,
          selected: input.selection.kind === 'scene' && input.selection.id === scene.id,
          highlighted: highlightedSceneIds.has(scene.id),
          expanded,
        },
      }
      nodes.push(sceneNode)
      edges.push({
        id: `${module.id}->${scene.id}`,
        source: module.id,
        target: scene.id,
        style: { stroke: 'var(--app-graph-edge-reference)', strokeWidth: 2 },
      })

      if (!expanded) return
      const pointNodes = targetPoint
        ? scene.points.filter(point => point.id === targetPoint.id)
        : scene.points
      pointNodes.forEach((point) => {
        const selected = showPointBranches && selectedPointId === point.id
        const pointNode: TraceableFlowNode = {
          id: pointKey(point.id),
          type: 'traceable',
          position: { x: 0, y: 0 },
          data: selected
            ? { kind: 'detail', point }
            : { kind: 'point', point, selected, highlighted: highlightedPointIds.has(point.id) },
        }
        nodes.push(pointNode)
        edges.push({
          id: `${scene.id}->${pointNode.id}`,
          source: scene.id,
          target: pointNode.id,
          style: { stroke: 'var(--app-graph-edge-muted)', strokeWidth: 1.8 },
        })
      })
    })
  })

  const gapNode = input.mode === 'gaps' && input.activeGap
    ? input.activeGap
    : input.mode === 'issues' && targetGap
      ? targetGap
      : undefined
  if (gapNode) {
    const node: TraceableFlowNode = {
      id: gapKey(gapNode.id),
      type: 'traceable',
      position: { x: 0, y: 0 },
      data: { kind: 'gap', gap: gapNode },
    }
    nodes.push(node)
    gapNode.relatedSceneIds.forEach((sceneId) => {
      if (!nodes.some(item => item.id === sceneId)) return
      edges.push({
        id: `${sceneId}->${node.id}`,
        source: sceneId,
        target: node.id,
        style: {
          stroke: 'var(--app-status-warning-text)',
          strokeWidth: 1.6,
          strokeDasharray: '4 4',
          opacity: 0.82,
        },
      })
    })
  }

  if (input.mode === 'issues' && input.issueCount === 0) {
    nodes.push({
      id: 'review-summary',
      type: 'traceable',
      position: { x: 0, y: 0 },
      data: {
        kind: 'review',
        reviewStatus: input.reviewStatus,
        reviewLabel: input.reviewLabel,
        pointCount: input.totalPoints,
        gapCount: input.totalGaps,
        moduleCount: input.modules.length,
      },
    })
  }

  if (input.mode === 'issues' && input.activeIssue) {
    const issue = input.activeIssue
    const point = issue.pointId
      ? input.modules.flatMap(module => module.points).find(entry => entry.id === issue.pointId)
      : undefined
    const gap = issue.gapId ? input.activeGap : undefined
    const targetKind = point ? 'point' : gap ? 'gap' : 'missing'
    nodes.push({
      id: issueKey(issue.index),
      type: 'traceable',
      position: { x: 0, y: 0 },
      data: { kind: 'issue', issue, targetLabel: issueTargetLabel(issue, point, gap), targetKind },
    })
    if (point) {
      edges.push({
        id: `${pointKey(point.id)}->${issueKey(issue.index)}`,
        source: pointKey(point.id),
        target: issueKey(issue.index),
        style: { stroke: 'var(--app-request-error-text)', strokeWidth: 1.6, strokeDasharray: '4 4', opacity: 0.82 },
      })
    } else if (gap) {
      edges.push({
        id: `${gapKey(gap.id)}->${issueKey(issue.index)}`,
        source: gapKey(gap.id),
        target: issueKey(issue.index),
        style: { stroke: 'var(--app-request-error-text)', strokeWidth: 1.6, strokeDasharray: '4 4', opacity: 0.82 },
      })
    }
  }

  return layoutGraph(nodes, edges)
}

type TreeNode = { id: string; children: TreeNode[] }

function layoutGraph(nodes: TraceableFlowNode[], edges: TraceableFlowEdge[]) {
  const nodeById = new Map(nodes.map(node => [node.id, node]))
  const children = new Map<string, string[]>()
  edges.forEach((edge) => {
    if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) return
    if (edge.id.includes('->issue-') || edge.id.includes('->gap-')) return
    const source = nodeById.get(edge.source)!
    const target = nodeById.get(edge.target)!
    if (source.data.kind === 'root' || source.data.kind === 'module' || source.data.kind === 'scene') {
      children.set(edge.source, [...(children.get(edge.source) ?? []), edge.target])
    }
    if (target.data.kind === 'issue') return
  })

  const tree: TreeNode = { id: 'graph-root', children: [] }
  const buildTree = (id: string, path = new Set<string>()): TreeNode | undefined => {
    if (path.has(id)) return undefined
    const node = nodeById.get(id)
    if (!node) return undefined
    const nextPath = new Set(path).add(id)
    return { id, children: (children.get(id) ?? []).map(child => buildTree(child, nextPath)).filter((child): child is TreeNode => Boolean(child)) }
  }
  const rootTree = buildTree('graph-root') ?? tree

  const widthById = new Map(nodes.map(node => [node.id, nodeWidth(node)]))
  const heightById = new Map(nodes.map(node => [node.id, nodeHeight(node)]))
  const rootWidth = widthById.get('graph-root') ?? 200
  const moduleWidth = Math.max(140, ...nodes.filter(node => node.data.kind === 'module').map(node => widthById.get(node.id) ?? 140))
  const sceneWidth = Math.max(140, ...nodes.filter(node => node.data.kind === 'scene').map(node => widthById.get(node.id) ?? 140))
  const pointColumnWidth = 360
  const rootX = MARGIN
  const moduleX = rootX + rootWidth + RANK_GAP
  const sceneX = moduleX + moduleWidth + RANK_GAP
  const pointX = sceneX + sceneWidth + RANK_GAP
  const issueX = pointX + pointColumnWidth + RANK_GAP

  const subtreeHeight = new Map<string, number>()
  const measure = (treeNode: TreeNode): number => {
    const ownHeight = heightById.get(treeNode.id) ?? 38
    const childHeights = treeNode.children.map(measure)
    const gap = treeNode.children.length > 1
      ? Math.max(...treeNode.children.map(child => nodeById.get(child.id)?.data.kind === 'point' ? POINT_GAP : SIBLING_GAP))
      : 0
    const childBlock = childHeights.reduce((sum, height) => sum + height, 0) + Math.max(0, treeNode.children.length - 1) * gap
    const height = Math.max(ownHeight, childBlock)
    subtreeHeight.set(treeNode.id, height)
    return height
  }
  const rootHeight = measure(rootTree)
  const positions = new Map<string, { x: number; y: number }>()
  const place = (treeNode: TreeNode, top: number, x: number) => {
    const ownHeight = heightById.get(treeNode.id) ?? 38
    const height = subtreeHeight.get(treeNode.id) ?? ownHeight
    positions.set(treeNode.id, { x, y: top + (height - ownHeight) / 2 })
    if (!treeNode.children.length) return
    const gap = Math.max(...treeNode.children.map(child => nodeById.get(child.id)?.data.kind === 'point' ? POINT_GAP : SIBLING_GAP))
    const childHeights = treeNode.children.map(child => subtreeHeight.get(child.id) ?? 0)
    const childBlock = childHeights.reduce((sum, childHeight) => sum + childHeight, 0) + Math.max(0, treeNode.children.length - 1) * gap
    let cursor = top + (height - childBlock) / 2
    treeNode.children.forEach((child, index) => {
      const childNode = nodeById.get(child.id)
      const childX = childNode?.data.kind === 'module'
        ? moduleX
        : childNode?.data.kind === 'scene'
          ? sceneX
          : pointX
      place(child, cursor, childX)
      cursor += (childHeights[index] ?? 0) + gap
    })
  }
  place(rootTree, MARGIN, rootX)

  const rootPosition = positions.get('graph-root') ?? { x: rootX, y: MARGIN }
  const rootCenter = rootPosition.y + (heightById.get('graph-root') ?? 38) / 2
  const sceneCenters = nodes
    .filter(node => node.data.kind === 'scene')
    .map((node) => {
      const position = positions.get(node.id)
      return position ? { id: node.id, center: position.y + (heightById.get(node.id) ?? 38) / 2 } : undefined
    })
    .filter((entry): entry is { id: string; center: number } => Boolean(entry))

  const extras = nodes.filter(node => node.data.kind === 'gap' || node.data.kind === 'review' || node.data.kind === 'issue')
  extras.forEach((node) => {
    const height = heightById.get(node.id) ?? 300
    if (node.data.kind === 'gap') {
      const related = node.data.gap.relatedSceneIds
        .map(sceneId => sceneCenters.find(entry => entry.id === sceneId)?.center)
        .filter((center): center is number => typeof center === 'number')
      const center = related.length ? related.reduce((sum, value) => sum + value, 0) / related.length : rootCenter
      positions.set(node.id, { x: pointX, y: Math.max(MARGIN, center - height / 2) })
      return
    }
    if (node.data.kind === 'review') {
      positions.set(node.id, { x: pointX, y: Math.max(MARGIN, rootCenter - height / 2) })
      return
    }
    if (node.data.kind !== 'issue') return
    const issue = node.data.issue
    const targetId = issue.pointId ? pointKey(issue.pointId) : issue.gapId ? gapKey(issue.gapId) : undefined
    const targetPosition = targetId ? positions.get(targetId) : undefined
    const targetHeight = targetId ? heightById.get(targetId) ?? 0 : 0
    if (targetPosition) {
      positions.set(node.id, { x: issueX, y: Math.max(MARGIN, targetPosition.y + targetHeight / 2 - height / 2) })
    } else {
      positions.set(node.id, { x: pointX, y: Math.max(MARGIN, rootCenter - height / 2) })
    }
  })

  const maxBottom = Math.max(
    MARGIN + rootHeight,
    ...nodes.map((node) => {
      const position = positions.get(node.id)
      return position ? position.y + (heightById.get(node.id) ?? 38) : 0
    }),
  )
  const stageWidth = (nodes.some(node => node.data.kind === 'issue' && positions.get(node.id)?.x === issueX) ? issueX + 360 : pointX + pointColumnWidth) + MARGIN
  const stageHeight = maxBottom + MARGIN

  return {
    nodes: nodes.map(node => {
      const position = positions.get(node.id) ?? { x: MARGIN, y: MARGIN }
      return {
        ...node,
        position,
        // 不写 node.width：连线锚定的是 React Flow 节点盒，而树节点样式是
        // max-content。固定宽度会让节点盒宽于可见卡片，连线停在卡片右侧空白处。
        // 让 React Flow 测量实际卡片宽度，连线才能接到卡片边缘。
        height: nodeHeight(node),
        style: { ...node.style, pointerEvents: 'all' as const },
      }
    }),
    edges,
    stageWidth,
    stageHeight,
    pointColumnX: pointX,
  }
}
