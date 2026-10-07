import { useMemo } from 'react'
import { MarkerType, type Edge } from '@xyflow/react'
import { RELATIONS_NODE_WIDTH, type RelationsGraphModel } from '../utils/caseRelationsGraph'
import { HIERARCHY_NODE_HEIGHT } from '../utils/relationsHierarchyLayout'
import { hierarchyPreferredPaths } from '../utils/relationsHierarchyPaths'
import { useRelationsEdgePaths } from './useRelationsEdgePaths'
import type { HierarchyView } from '../components/HierarchyGraphToolbar'
import type { HierarchyCaseBadge, HierarchyCaseNode } from '../components/HierarchyGraphNodes'

export type HierarchyFlowEdge = Edge<{ path: string; label?: { id: string; x: number; y: number } }, 'hierarchy'>

export function useHierarchyFlow(view: HierarchyView, model: RelationsGraphModel, badges?: Record<string, HierarchyCaseBadge>) {
  const { layout, selectedNode, selectedId } = view
  const preferred = useMemo(() => layout ? hierarchyPreferredPaths(layout) : new Map<string, string>(), [layout])
  const neighbors = selectedNode ? model.neighborIdsByCase.get(selectedNode.meta.caseId) : null
  const activeEdges = selectedNode ? model.edgeIdsByCase.get(selectedNode.meta.caseId) : null
  const nodes: HierarchyCaseNode[] = layout ? [...layout.nodes].map(([id, placed]): HierarchyCaseNode => ({
    id, type: 'hierarchyCase', position: { x: placed.x, y: placed.y }, width: RELATIONS_NODE_WIDTH, height: HIERARCHY_NODE_HEIGHT,
    selected: id === selectedId, draggable: false,
    data: { placed, badge: badges?.[placed.meta.caseId], dimmed: Boolean(selectedNode) && placed.meta.caseId !== selectedNode?.meta.caseId && !neighbors?.has(placed.meta.caseId),
      count: view.children(placed.meta.caseId, placed.groupId).length, expanded: view.expanded.has(placed.meta.caseId), onToggle: view.toggleNode },
  })) : []
  const edges: HierarchyFlowEdge[] = layout?.edges.map((edge) => {
    const active = !selectedNode || activeEdges?.has(edge.relationId)
    const color = edge.relationType === 'next' ? active ? 'var(--graph-edge-next)' : 'var(--graph-edge-next-dim)' : active ? 'var(--graph-edge-branch)' : 'var(--graph-edge-branch-dim)'
    return { id: edge.edgeId, source: edge.source, target: edge.target, type: 'hierarchy', selectable: false,
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      style: { stroke: color, strokeWidth: edge.main ? 2 : 1.6, ...(edge.relationType === 'branch' ? { strokeDasharray: '6 5' } : {}) }, data: { path: '' } }
  }) ?? []
  const routing = useRelationsEdgePaths(nodes, edges, layout?.paths ?? [], { paths: preferred, orthogonal: true })
  const routedEdges = edges.map((edge) => {
    const placed = layout!.edges.find((item) => item.edgeId === edge.id)!
    const source = layout!.nodes.get(placed.source)!, target = layout!.nodes.get(placed.target)!
    const path = routing.paths.get(edge.id) ?? ''
    const label = !placed.main && path && path === preferred.get(edge.id) ? {
      id: placed.relationId,
      x: source.main ? source.x - 20 : (source.x + RELATIONS_NODE_WIDTH + target.x) / 2,
      y: target.y + HIERARCHY_NODE_HEIGHT / 2 - 12,
    } : undefined
    return { ...edge, data: { path, label } }
  })
  const drawnCount = new Set(layout?.edges.filter((edge) => routing.paths.get(edge.edgeId)).map((edge) => edge.relationId)).size
  return { nodes, edges: routedEdges, routing, drawnCount }
}
