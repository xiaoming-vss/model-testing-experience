import { useCallback, useMemo, useState } from 'react'
import type { RelationsGraphModel } from '../utils/caseRelationsGraph'
import { buildHierarchyGroups, hierarchyChildren } from '../utils/relationsHierarchyGroups'
import { layoutHierarchy } from '../utils/relationsHierarchyLayout'

type HierarchyLayout = ReturnType<typeof layoutHierarchy>
/*
 * 布局是图谱里最贵的一步（dagre 全量重排）。navigate 需要先算出展开后的节点才能定位选中项，
 * 把结果按 model + expanded 缓存起来，下一次渲染的 useMemo 直接复用，避免同一组输入连算两遍。
 * 用模块级 WeakMap 而不是 ref：渲染期间读取 ref 会被 react-hooks/refs 判定为不安全。
 */
const layoutCacheByModel = new WeakMap<object, WeakMap<Set<string>, HierarchyLayout>>()

function cachedLayout(
  model: RelationsGraphModel,
  groups: ReturnType<typeof buildHierarchyGroups>,
  expanded: Set<string>,
): HierarchyLayout {
  let cache = layoutCacheByModel.get(model)
  if (!cache) {
    cache = new WeakMap()
    layoutCacheByModel.set(model, cache)
  }
  const hit = cache.get(expanded)
  if (hit) return hit
  const layout = layoutHierarchy(model, groups, expanded)
  cache.set(expanded, layout)
  return layout
}

export function useRelationsHierarchyView(model: RelationsGraphModel) {
  const groups = useMemo(() => buildHierarchyGroups(model), [model])
  const [expanded, setExpanded] = useState(() => new Set(model.nodes.map((node) => node.caseId)))
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [layoutAnchorId, setLayoutAnchorId] = useState<string | null>(null)
  const childrenByGroup = useMemo(() => new Map(groups.map((group) => [group.id, hierarchyChildren(model, group)])), [model, groups])
  const children = useCallback((caseId: string, groupId: string) => childrenByGroup.get(groupId)?.(caseId) ?? [], [childrenByGroup])
  const expandable = useMemo(() => new Set(groups.flatMap((group) => [...group.caseIds].filter((id) => childrenByGroup.get(group.id)!(id).length))), [groups, childrenByGroup])
  const allExpanded = expandable.size > 0 && [...expandable].every((id) => expanded.has(id))
  const layout = useMemo(() => cachedLayout(model, groups, expanded), [model, groups, expanded])
  const selectedNode = selectedId ? layout.nodes.get(selectedId) ?? null : null
  const toggleNode = useCallback((id: string) => {
    const caseId = layout.nodes.get(id)?.meta.caseId
    if (!caseId) return
    setLayoutAnchorId(id)
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(caseId)) next.delete(caseId)
      else next.add(caseId)
      return next
    })
  }, [layout.nodes])
  const toggleAll = useCallback(() => {
    setLayoutAnchorId(null)
    setExpanded(allExpanded ? new Set() : new Set(expandable))
    if (allExpanded) setSelectedId(null)
  }, [allExpanded, expandable])
  const navigate = useCallback((caseId: string) => {
    setLayoutAnchorId(null)
    const nextExpanded = new Set(expandable)
    const revealed = cachedLayout(model, groups, nextExpanded)
    setExpanded(nextExpanded)
    const candidates = [...revealed.nodes].filter(([, node]) => node.meta.caseId === caseId)
    const target = candidates.find(([, node]) => node.groupId === selectedNode?.groupId) ?? candidates[0]
    setSelectedId(target?.[0] ?? null)
  }, [expandable, groups, model, selectedNode?.groupId])
  const select = useCallback((id: string | null) => setSelectedId(id), [])
  return { layout, layoutAnchorId, selectedNode, selectedId, expanded, children, allExpanded,
    canExpand: expandable.size > 0, toggleNode, toggleAll, navigate, select }
}
