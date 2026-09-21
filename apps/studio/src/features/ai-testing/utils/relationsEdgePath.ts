export type RoutePoint = { x: number; y: number }
export type RouteRect = RoutePoint & { id: string; width: number; height: number }
const EPS = 0.001
const distance = (a: RoutePoint, b: RoutePoint) => Math.hypot(b.x - a.x, b.y - a.y)
const lerp = (a: RoutePoint, b: RoutePoint, t: number): RoutePoint => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t })
const coord = (p: RoutePoint) => `${p.x},${p.y}`

// Open rectangle intersection allows touching a routing boundary.
export function segmentHitsCard(a: RoutePoint, b: RoutePoint, r: RouteRect): boolean {
  let low = 0
  let high = 1
  for (const axis of ['x', 'y'] as const) {
    const min = r[axis] + EPS
    const max = r[axis] + (axis === 'x' ? r.width : r.height) - EPS
    const delta = b[axis] - a[axis]
    if (Math.abs(delta) < EPS) {
      if (a[axis] <= min || a[axis] >= max) return false
    } else {
      const t1 = (min - a[axis]) / delta
      const t2 = (max - a[axis]) / delta
      low = Math.max(low, Math.min(t1, t2))
      high = Math.min(high, Math.max(t1, t2))
      if (low >= high) return false
    }
  }
  return low < high
}
function expand(r: RouteRect, pad: number): RouteRect {
  return { ...r, x: r.x - pad, y: r.y - pad, width: r.width + 2 * pad, height: r.height + 2 * pad }
}
function boundary(r: RouteRect, toward: RoutePoint): RoutePoint {
  const center = { x: r.x + r.width / 2, y: r.y + r.height / 2 }
  const dx = toward.x - center.x
  const dy = toward.y - center.y
  const scale = Math.min(r.width / 2 / (Math.abs(dx) || EPS), r.height / 2 / (Math.abs(dy) || EPS))
  return { x: center.x + dx * scale, y: center.y + dy * scale }
}
function roundedPath(points: RoutePoint[], clearance: number): string {
  let path = `M ${coord(points[0])}`
  for (let i = 1; i < points.length - 1; i++) {
    const before = points[i - 1], corner = points[i], after = points[i + 1]
    // Rounding remains inside the obstacle clearance.
    const radius = Math.min(clearance / 2, distance(before, corner) / 3, distance(corner, after) / 3)
    const entry = lerp(corner, before, radius / (distance(before, corner) || 1))
    const exit = lerp(corner, after, radius / (distance(corner, after) || 1))
    path += ` L ${coord(entry)} Q ${coord(corner)} ${coord(exit)}`
  }
  return `${path} L ${coord(points[points.length - 1])}`
}

export function routeRelationsEdge(source: RouteRect, target: RouteRect, cards: RouteRect[], straight: boolean): string {
  // Preserve narrow passages in the existing layout before giving up on an overlapping port.
  for (const clearance of [16, 4, 0.5]) {
    const path = routeWithClearance(source, target, cards, straight, clearance)
    if (path) return path
  }
  return ''
}

function routeWithClearance(source: RouteRect, target: RouteRect, cards: RouteRect[], straight: boolean, clearance: number): string {
  const sourceCenter = { x: source.x + source.width / 2, y: source.y + source.height / 2 }
  const targetCenter = { x: target.x + target.width / 2, y: target.y + target.height / 2 }
  if (distance(sourceCenter, targetCenter) < EPS) return ''
  const start = boundary(source, targetCenter), end = boundary(target, sourceCenter)
  const obstacles = cards.filter((r) => r.id !== source.id && r.id !== target.id).map((r) => expand(r, clearance))
  const clear = (a: RoutePoint, b: RoutePoint, rects = obstacles) => !rects.some((r) => segmentHitsCard(a, b, r))
  if (straight && clear(start, end, [...obstacles, source, target])) return `M ${coord(start)} L ${coord(end)}`
  // Try shallow curves on either side; reject any that cross cards.
  const length = distance(start, end)
  for (const direction of [1, -1]) {
    const bow = Math.min(48, length * 0.18) * direction
    const control = { x: (start.x + end.x) / 2 - (end.y - start.y) / (length || 1) * bow, y: (start.y + end.y) / 2 + (end.x - start.x) / (length || 1) * bow }
    const steps = Math.max(24, Math.ceil(length / 8))
    let previous = start
    let safe = true
    for (let i = 1; i <= steps; i++) {
      const t = i / steps
      const p = lerp(lerp(start, control, t), lerp(control, end, t), t)
      if (!clear(previous, p, [...obstacles, source, target])) { safe = false; break }
      previous = p
    }
    if (safe) return `M ${coord(start)} Q ${coord(control)} ${coord(end)}`
  }
  // Shortest visibility route around padded card corners, with rounded turns.
  const rects = cards.map((r) => expand(r, clearance))
  const outerStart = boundary(expand(source, clearance), targetCenter), outerEnd = boundary(expand(target, clearance), sourceCenter)
  const vertices = [outerStart, outerEnd, ...rects.flatMap((r) => [
    { x: r.x, y: r.y }, { x: r.x + r.width, y: r.y },
    { x: r.x, y: r.y + r.height }, { x: r.x + r.width, y: r.y + r.height },
  ])]
  const costs = vertices.map(() => Infinity), previous = vertices.map(() => -1)
  const visited = new Set<number>()
  costs[0] = 0
  while (visited.size < vertices.length) {
    let current = -1
    vertices.forEach((_, i) => { if (!visited.has(i) && (current < 0 || costs[i] < costs[current])) current = i })
    if (current < 0 || !Number.isFinite(costs[current]) || current === 1) break
    visited.add(current)
    vertices.forEach((point, i) => {
      if (visited.has(i)) return
      const cost = costs[current] + distance(vertices[current], point)
      if (cost < costs[i] && clear(vertices[current], point, rects)) { costs[i] = cost; previous[i] = current }
    })
  }
  // Fully overlapping cards can seal an endpoint; never draw through a card.
  if (!Number.isFinite(costs[1])) return ''
  const route = [vertices[1]]
  let cursor = 1
  while (previous[cursor] >= 0) { cursor = previous[cursor]; route.unshift(vertices[cursor]) }
  if (!clear(start, outerStart, cards) || !clear(outerEnd, end, cards)) return ''
  return roundedPath([start, ...route, end], clearance)
}
