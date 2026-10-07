import type { CaseRelationsEdge, RelationsGraphModel } from './caseRelationsGraph'

export type HierarchyGroup = {
  id: string
  label: string
  kind: 'path' | 'related' | 'isolated'
  spine: string[]
  caseIds: Set<string>
}

export function hierarchyOutgoing(model: RelationsGraphModel) {
  const outgoing = new Map<string, CaseRelationsEdge[]>()
  model.edges.forEach((edge) => {
    const list = outgoing.get(edge.fromCaseId) ?? []
    list.push(edge)
    outgoing.set(edge.fromCaseId, list)
  })
  outgoing.forEach((list) => list.sort((a, b) => a.order - b.order))
  return outgoing
}

/** Each path has its own view; incoming components and isolated cases remain accessible. */
export function buildHierarchyGroups(model: RelationsGraphModel): HierarchyGroup[] {
  const outgoing = hierarchyOutgoing(model)
  const mainIds = new Set(model.paths.flatMap((path) => path.caseIds))
  const groups: HierarchyGroup[] = model.paths.filter((path) => path.caseIds.length).map((path) => {
    const caseIds = new Set(path.caseIds), queue = [...caseIds]
    for (let i = 0; i < queue.length; i++) {
      for (const edge of outgoing.get(queue[i]) ?? []) {
        if (caseIds.has(edge.toCaseId)) continue
        caseIds.add(edge.toCaseId)
        // A reference to another path is visible but does not pull in that entire path.
        if (!mainIds.has(edge.toCaseId)) queue.push(edge.toCaseId)
      }
    }
    return { id: `path:${path.pathId}`, label: path.pathId, kind: 'path', spine: path.caseIds, caseIds }
  })
  const covered = new Set(groups.flatMap((group) => [...group.caseIds]))
  const remaining = new Set(model.nodes.filter((node) => !covered.has(node.caseId) && !node.isolated).map((node) => node.caseId))
  while (remaining.size) {
    const seed = remaining.values().next().value as string
    const component = new Set([seed]), queue = [seed]
    remaining.delete(seed)
    for (let i = 0; i < queue.length; i++) {
      for (const neighbor of model.neighborIdsByCase.get(queue[i]) ?? []) {
        if (!remaining.delete(neighbor)) continue
        component.add(neighbor)
        queue.push(neighbor)
      }
    }
    const caseIds = new Set(component)
    model.edges.forEach((edge) => {
      if (component.has(edge.fromCaseId) || component.has(edge.toCaseId)) {
        caseIds.add(edge.fromCaseId)
        caseIds.add(edge.toCaseId)
      }
    })
    const root = [...component].find((id) => !model.edges.some((edge) => edge.toCaseId === id && component.has(edge.fromCaseId))) ?? seed
    const spine = [root], seen = new Set(spine)
    while (true) {
      const candidates = (outgoing.get(spine.at(-1)!) ?? []).filter((edge) => edge.relationType === 'next' && caseIds.has(edge.toCaseId) && !seen.has(edge.toCaseId))
      const next = candidates.find((edge) => component.has(edge.toCaseId)) ?? candidates[0]
      if (!next) break
      spine.push(next.toCaseId)
      seen.add(next.toCaseId)
    }
    const index = groups.filter((group) => group.kind === 'related').length + 1
    groups.push({ id: `related:${index}`, label: index === 1 ? '其他关联' : `其他关联 ${index}`, kind: 'related', spine, caseIds })
  }
  const isolated = model.nodes.filter((node) => node.isolated && !covered.has(node.caseId)).map((node) => node.caseId)
  if (isolated.length) groups.push({ id: 'isolated', label: '独立用例', kind: 'isolated', spine: isolated, caseIds: new Set(isolated) })
  return groups
}

export function hierarchyChildren(model: RelationsGraphModel, group: HierarchyGroup) {
  const spine = new Set(group.spine)
  const outgoing = hierarchyOutgoing(model)
  return (caseId: string) => (outgoing.get(caseId) ?? []).filter((edge) => group.caseIds.has(edge.toCaseId) && !spine.has(edge.toCaseId))
}

export function hierarchyFamily(model: RelationsGraphModel, group: HierarchyGroup, rootId: string): Set<string> {
  const children = hierarchyChildren(model, group), ids = new Set([rootId]), queue = [rootId]
  for (let i = 0; i < queue.length; i++) {
    for (const edge of children(queue[i])) {
      if (ids.has(edge.toCaseId)) continue
      ids.add(edge.toCaseId)
      queue.push(edge.toCaseId)
    }
  }
  return ids
}
