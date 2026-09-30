import { boundary, previewRelationsEdge, routeRelationsEdge, type RoutePoint, type RouteRect } from './relationsEdgePath'
import { RelationsRouteTraffic } from './relationsRouteTraffic'

export type RelationsRouteGeometry = {
  cards: RouteRect[]
  links: { id: string; source: string; target: string; straight: boolean }[]
}
export type RelationsRouteResult = { paths: [string, string][]; blockedEdgeIds?: string[]; done?: boolean }

/** Allocate both incoming and outgoing ports together; mainline ports stay centered. */
function connectionPorts({ cards, links }: RelationsRouteGeometry) {
  const byId = new Map(cards.map((card) => [card.id, card]))
  const groups = new Map<string, { key: string; port: RoutePoint; card: RouteRect; side: string; straight: boolean; order: number }[]>()
  links.forEach((link) => {
    ;(['source', 'target'] as const).forEach((end) => {
      const card = byId.get(link[end]), other = byId.get(link[end === 'source' ? 'target' : 'source'])
      if (!card || !other) return
      const center = { x: other.x + other.width / 2, y: other.y + other.height / 2 }
      const port = boundary(card, center)
      const side = Math.abs(port.x - card.x) < 0.001 ? 'left'
        : Math.abs(port.x - card.x - card.width) < 0.001 ? 'right'
          : Math.abs(port.y - card.y) < 0.001 ? 'top' : 'bottom'
      const key = `${card.id}:${side}`, group = groups.get(key) ?? []
      group.push({ key: `${link.id}:${end}`, card, port, side, straight: link.straight, order: side === 'left' || side === 'right' ? center.y : center.x })
      groups.set(key, group)
    })
  })
  const ports = new Map<string, RoutePoint>()
  groups.forEach((group) => {
    group.sort((a, b) => a.order - b.order || a.key.localeCompare(b.key))
    const main = group.filter((entry) => entry.straight)
    // Only a single mainline can reserve the center; shared-node mainlines need separate ports too.
    const hasMain = main.length === 1
    const branches = hasMain ? group.filter((entry) => !entry.straight) : group
    if (hasMain) ports.set(main[0].key, main[0].port)
    branches.forEach((entry, i) => {
      if (group.length === 1) { ports.set(entry.key, entry.port); return }
      const { card, side } = entry
      // Reserve a gap at the center when a straight mainline also uses this side.
      const slots = branches.length + (hasMain ? 1 : 0)
      let slot = i + 1
      if (hasMain && slot >= Math.ceil((slots + 1) / 2)) slot++
      const fraction = 0.1 + 0.8 * slot / (slots + 1)
      ports.set(entry.key, side === 'left' || side === 'right'
        ? { x: side === 'left' ? card.x : card.x + card.width, y: card.y + fraction * card.height }
        : { x: card.x + fraction * card.width, y: side === 'top' ? card.y : card.y + card.height })
    })
  })
  return ports
}

/** Route mainlines first, then local branches, reserving each visible corridor. */
export function computeRelationsRoutes(geometry: RelationsRouteGeometry, onProgress?: (result: RelationsRouteResult) => void): RelationsRouteResult {
  const { cards, links } = geometry
  const byId = new Map(cards.map((card) => [card.id, card]))
  const ports = connectionPorts(geometry)
  const traffic = new RelationsRouteTraffic()
  const mainTraffic = new RelationsRouteTraffic()
  const blockedEdgeIds: string[] = []
  const span = (edge: RelationsRouteGeometry['links'][number]) => {
    const a = byId.get(edge.source), b = byId.get(edge.target)
    return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0
  }
  const ordered = [...links].sort((a, b) => Number(b.straight) - Number(a.straight) || (a.straight && b.straight ? 0 : span(a) - span(b) || a.id.localeCompare(b.id)))
  const result = new Map<string, string>()
  let lastProgress = performance.now()
  ordered.forEach((edge, index) => {
    const source = byId.get(edge.source), target = byId.get(edge.target)
    const path = source && target ? routeRelationsEdge(source, target, cards, edge.straight, {
      sourcePort: ports.get(`${edge.id}:source`), targetPort: ports.get(`${edge.id}:target`), trafficCost: traffic.cost,
      blockedSegment: (a, b) => mainTraffic.cost(a, b) > 0,
    }) : ''
    result.set(edge.id, path)
    if (!path) blockedEdgeIds.push(edge.id)
    traffic.add(path)
    if (edge.straight) mainTraffic.add(path)
    if (onProgress && (index === 0 || edge.straight || index % 8 === 7 || performance.now() - lastProgress > 32)) {
      onProgress({ paths: [...result], blockedEdgeIds: [...blockedEdgeIds], done: false })
      lastProgress = performance.now()
    }
  })
  return { paths: links.map((edge) => [edge.id, result.get(edge.id) ?? '']), blockedEdgeIds, done: true }
}

/** Constant work per edge: keep endpoints attached while dragging or waiting. */
export function previewRelationsRoutes({ cards, links }: RelationsRouteGeometry) {
  const byId = new Map(cards.map((card) => [card.id, card]))
  return new Map(links.map((edge) => {
    const source = byId.get(edge.source), target = byId.get(edge.target)
    return [edge.id, source && target ? previewRelationsEdge(source, target) : '']
  }))
}
