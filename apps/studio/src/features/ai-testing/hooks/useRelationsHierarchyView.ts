import { useMemo, useState } from 'react'
import type { RelationsGraphModel } from '../utils/caseRelationsGraph'
import { buildHierarchyGroups, hierarchyChildren } from '../utils/relationsHierarchyGroups'
import { layoutHierarchy } from '../utils/relationsHierarchyLayout'

export function useRelationsHierarchyView(model: RelationsGraphModel) {
  const groups = useMemo(() => buildHierarchyGroups(model), [model])
  const [expanded, setExpanded] = useState(() => new Set(model.nodes.map((node) => node.caseId)))
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [layoutAnchorId, setLayoutAnchorId] = useState<string | null>(null)
  const childrenByGroup = useMemo(() => new Map(groups.map((group) => [group.id, hierarchyChildren(model, group)])), [model, groups])
  const children = (caseId: string, groupId: string) => childrenByGroup.get(groupId)?.(caseId) ?? []
  const expandable = useMemo(() => new Set(groups.flatMap((group) => [...group.caseIds].filter((id) => childrenByGroup.get(group.id)!(id).length))), [groups, childrenByGroup])
  const allExpanded = expandable.size > 0 && [...expandable].every((id) => expanded.has(id))
  const layout = useMemo(() => layoutHierarchy(model, groups, expanded), [model, groups, expanded])
  const selectedNode = selectedId ? layout.nodes.get(selectedId) ?? null : null
  const toggleNode = (id: string) => {
    const caseId = layout.nodes.get(id)?.meta.caseId
    if (!caseId) return
    setLayoutAnchorId(id)
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(caseId)) next.delete(caseId)
      else next.add(caseId)
      return next
    })
  }
  const toggleAll = () => {
    setLayoutAnchorId(null)
    setExpanded(allExpanded ? new Set() : new Set(expandable))
    if (allExpanded) setSelectedId(null)
  }
  const navigate = (caseId: string) => {
    setLayoutAnchorId(null)
    setExpanded(new Set(expandable))
    const revealed = layoutHierarchy(model, groups, new Set(expandable))
    const candidates = [...revealed.nodes].filter(([, node]) => node.meta.caseId === caseId)
    const target = candidates.find(([, node]) => node.groupId === selectedNode?.groupId) ?? candidates[0]
    setSelectedId(target?.[0] ?? null)
  }
  return { layout, layoutAnchorId, selectedNode, selectedId, expanded, children, allExpanded,
    canExpand: expandable.size > 0, toggleNode, toggleAll, navigate, select: setSelectedId }
}
