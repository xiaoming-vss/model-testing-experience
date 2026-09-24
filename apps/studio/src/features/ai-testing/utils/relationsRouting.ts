import { previewRelationsEdge, routeRelationsEdge, type RouteRect } from './relationsEdgePath'

export type RelationsRouteGeometry = {
  cards: RouteRect[]
  links: { id: string; source: string; target: string; straight: boolean }[]
}
export type RelationsRouteResult = { paths: [string, string][] }

/** Full obstacle routing is called only inside the worker. */
export function computeRelationsRoutes({ cards, links }: RelationsRouteGeometry): RelationsRouteResult {
  const byId = new Map(cards.map((card) => [card.id, card]))
  return { paths: links.map((edge) => {
    const source = byId.get(edge.source), target = byId.get(edge.target)
    return [edge.id, source && target ? routeRelationsEdge(source, target, cards, edge.straight) : '']
  }) }
}

/** Constant work per edge: keep endpoints attached while dragging or waiting. */
export function previewRelationsRoutes({ cards, links }: RelationsRouteGeometry) {
  const byId = new Map(cards.map((card) => [card.id, card]))
  return new Map(links.map((edge) => {
    const source = byId.get(edge.source), target = byId.get(edge.target)
    return [edge.id, source && target ? previewRelationsEdge(source, target) : '']
  }))
}
