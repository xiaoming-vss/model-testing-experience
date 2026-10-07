import { RELATIONS_NODE_WIDTH } from './caseRelationsGraph'
import { HIERARCHY_NODE_HEIGHT, type HierarchyLayout } from './relationsHierarchyLayout'
import { validPreferredRelationPath } from './relationsRouting'

/** Short orthogonal tree paths; references and cycles use the routing worker. */
export function hierarchyPreferredPaths(layout: HierarchyLayout) {
  const width = RELATIONS_NODE_WIDTH, height = HIERARCHY_NODE_HEIGHT
  const cards = [...layout.nodes].map(([id, node]) => ({ id, x: node.x, y: node.y, width, height }))
  const paths = new Map<string, string>()
  for (const edge of layout.edges) {
    const source = layout.nodes.get(edge.source)!, target = layout.nodes.get(edge.target)!
    let path = ''
    if (edge.main) {
      path = `M ${source.x + width},${source.y + height / 2} L ${target.x},${target.y + height / 2}`
    } else if (edge.tree && source.main) {
      const sx = source.x + width / 2, sy = source.y + height, rail = source.x - 20, ty = target.y + height / 2
      path = `M ${sx},${sy} L ${sx},${sy + 24} L ${rail},${sy + 24} L ${rail},${ty} L ${target.x},${ty}`
    } else if (edge.tree && target.x > source.x + width) {
      const sx = source.x + width, sy = source.y + height / 2, ty = target.y + height / 2, rail = (sx + target.x) / 2
      path = `M ${sx},${sy} L ${rail},${sy} L ${rail},${ty} L ${target.x},${ty}`
    }
    if (path && validPreferredRelationPath(path, cards)) paths.set(edge.edgeId, path)
  }
  return paths
}
