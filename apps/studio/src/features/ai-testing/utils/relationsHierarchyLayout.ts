import { RELATIONS_NODE_WIDTH, type CaseRelationsEdge, type RelationsGraphModel, type RelationsGraphNode } from './caseRelationsGraph'
import { hierarchyChildren, hierarchyFamily, type HierarchyGroup } from './relationsHierarchyGroups'

export const HIERARCHY_NODE_HEIGHT = 144
export const HIERARCHY_MIN_ZOOM = 0.05
const WIDTH = RELATIONS_NODE_WIDTH
const GAP = 72
const ROW = HIERARCHY_NODE_HEIGHT + 40
const PAD = 32

export type HierarchyPlacedNode = {
  meta: RelationsGraphNode
  x: number
  y: number
  depth: number
  main: boolean
  reference: boolean
  groupId: string
  groupLabel: string
}
export type HierarchyPlacedEdge = CaseRelationsEdge & {
  relationId: string
  source: string
  target: string
  main: boolean
  tree: boolean
}
export type HierarchyLayout = {
  nodes: Map<string, HierarchyPlacedNode>
  edges: HierarchyPlacedEdge[]
  paths: { caseIds: string[] }[]
}

/** All main paths share one canvas; expanded trees reserve their own columns and rows. */
export function layoutHierarchy(model: RelationsGraphModel, groups: HierarchyGroup[], expanded: Set<string>): HierarchyLayout {
  const nodes = new Map<string, HierarchyPlacedNode>(), edges: HierarchyPlacedEdge[] = [], paths: HierarchyLayout['paths'] = []
  const shared = new Set(model.nodes.filter((node) => model.paths.filter((path) => path.caseIds.includes(node.caseId)).length > 1).map((node) => node.caseId))
  let top = 40
  for (const group of groups) {
    const children = hierarchyChildren(model, group), byCase = new Map<string, string>(), treePairs = new Set<string>()
    const groupNodes: HierarchyPlacedNode[] = []
    const put = (id: string, caseId: string, x: number, y: number, depth: number, main = false) => {
      const original = model.nodeById.get(caseId)!
      const reference = original.onMainPath && group.kind !== 'path' || !main && original.onMainPath
      const node = { meta: { ...original, shared: shared.has(caseId) || reference }, x, y, depth, main, reference, groupId: group.id, groupLabel: group.label }
      nodes.set(id, node)
      groupNodes.push(node)
      if (!byCase.has(caseId)) byCase.set(caseId, id)
      return node
    }
    const spineIds = group.spine.map((caseId, index) => {
      const id = `${group.id}:main:${index}:${caseId}`
      put(id, caseId, PAD, top, 0, true)
      return id
    })
    if (group.kind === 'isolated') {
      spineIds.forEach((id, i) => Object.assign(nodes.get(id)!, { x: PAD + i % 4 * (WIDTH + GAP), y: top + Math.floor(i / 4) * ROW }))
    } else {
      let leafY = top + HIERARCHY_NODE_HEIGHT + 96
      const place = (caseId: string, x: number, depth: number): number | null => {
        if (byCase.has(caseId)) return null
        const node = put(`${group.id}:case:${caseId}`, caseId, x, leafY, depth)
        const ys: number[] = []
        for (const edge of expanded.has(caseId) ? children(caseId) : []) {
          const y = place(edge.toCaseId, x + WIDTH + GAP, depth + 1)
          if (y === null) continue
          ys.push(y)
          treePairs.add(JSON.stringify([caseId, edge.toCaseId]))
        }
        if (ys.length) node.y = (ys[0] + ys.at(-1)!) / 2
        else { node.y = leafY; leafY += ROW }
        return node.y
      }
      let x = PAD
      for (const id of spineIds) {
        const parent = nodes.get(id)!
        parent.x = x
        leafY = top + HIERARCHY_NODE_HEIGHT + 96
        const start = groupNodes.length
        for (const edge of expanded.has(parent.meta.caseId) ? children(parent.meta.caseId) : []) {
          if (place(edge.toCaseId, x + 24, 1) !== null) treePairs.add(JSON.stringify([parent.meta.caseId, edge.toCaseId]))
        }
        x = Math.max(parent.x + WIDTH, ...groupNodes.slice(start).map((node) => node.x + WIDTH)) + GAP
      }
      // Incoming components can have several roots. Keep each root available while its descendants are collapsed.
      const reachable = new Set(group.spine.flatMap((id) => [...hierarchyFamily(model, group, id)]))
      const remaining = new Set([...group.caseIds].filter((id) => !reachable.has(id)))
      leafY = Math.max(top + ROW, ...groupNodes.map((node) => node.y + ROW))
      while (remaining.size) {
        const root = [...remaining].find((id) => !model.edges.some((edge) => edge.toCaseId === id && remaining.has(edge.fromCaseId))) ?? remaining.values().next().value!
        hierarchyFamily(model, group, root).forEach((id) => remaining.delete(id))
        place(root, PAD, 1)
      }
      paths.push({ caseIds: spineIds })
    }
    const mainPairs = new Map<string, [string, string][]>()
    group.spine.slice(1).forEach((caseId, i) => {
      const key = JSON.stringify([group.spine[i], caseId]), pairs = mainPairs.get(key) ?? []
      pairs.push([spineIds[i], spineIds[i + 1]])
      mainPairs.set(key, pairs)
    })
    model.edges.forEach((edge) => {
      const key = JSON.stringify([edge.fromCaseId, edge.toCaseId])
      const pairs = edge.relationType === 'next' && group.kind !== 'isolated' ? mainPairs.get(key) : undefined
      if (pairs) pairs.forEach(([source, target], i) => edges.push({ ...edge, edgeId: `${group.id}:${edge.edgeId}:${i}`, relationId: edge.edgeId, source, target, main: true, tree: false }))
      else {
        const source = byCase.get(edge.fromCaseId), target = byCase.get(edge.toCaseId)
        if (source && target) edges.push({ ...edge, edgeId: `${group.id}:${edge.edgeId}`, relationId: edge.edgeId, source, target, main: false, tree: treePairs.has(key) })
      }
    })
    top = Math.max(...groupNodes.map((node) => node.y + HIERARCHY_NODE_HEIGHT)) + 120
  }
  return { nodes, edges, paths }
}
