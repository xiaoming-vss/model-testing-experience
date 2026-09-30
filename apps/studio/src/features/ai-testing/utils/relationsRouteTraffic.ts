import type { RoutePoint } from './relationsEdgePath'

type Segment = { a: RoutePoint; b: RoutePoint }
const CELL = 96
const cross = (a: RoutePoint, b: RoutePoint) => a.x * b.y - a.y * b.x
const delta = (a: RoutePoint, b: RoutePoint) => ({ x: b.x - a.x, y: b.y - a.y })

/** Samples only the M/L/Q commands emitted by our router, in graph coordinates. */
export function sampleRoute(path: string): RoutePoint[] {
  const tokens = path.match(/[MLQ]|-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/g) ?? []
  const points: RoutePoint[] = []
  let i = 0
  let cursor = { x: 0, y: 0 }
  const point = () => ({ x: Number(tokens[i++]), y: Number(tokens[i++]) })
  while (i < tokens.length) {
    const command = tokens[i++]
    if (command === 'M') { cursor = point(); points.push(cursor); continue }
    const control = command === 'Q' ? point() : null
    const end = point()
    const length = control
      ? Math.hypot(control.x - cursor.x, control.y - cursor.y) + Math.hypot(end.x - control.x, end.y - control.y)
      : Math.hypot(end.x - cursor.x, end.y - cursor.y)
    const steps = Math.max(1, Math.ceil(length / 12))
    for (let j = 1; j <= steps; j++) {
      const t = j / steps, u = 1 - t
      points.push(control ? {
        x: u * u * cursor.x + 2 * u * t * control.x + t * t * end.x,
        y: u * u * cursor.y + 2 * u * t * control.y + t * t * end.y,
      } : { x: cursor.x * u + end.x * t, y: cursor.y * u + end.y * t })
    }
    cursor = end
  }
  return points
}

/** Shared routing traffic: parallel runs are expensive; crossings are penalized too. */
export class RelationsRouteTraffic {
  private cells = new Map<string, Segment[]>()

  private keys(a: RoutePoint, b: RoutePoint) {
    const minX = Math.floor((Math.min(a.x, b.x) - 8) / CELL), maxX = Math.floor((Math.max(a.x, b.x) + 8) / CELL)
    const minY = Math.floor((Math.min(a.y, b.y) - 8) / CELL), maxY = Math.floor((Math.max(a.y, b.y) + 8) / CELL)
    const keys = new Set<string>()
    if ((maxX - minX + 1) * (maxY - minY + 1) <= 64) {
      for (let x = minX; x <= maxX; x++) {
        for (let y = minY; y <= maxY; y++) keys.add(`${x}:${y}`)
      }
    } else {
      // Follow the segment instead of scanning the entire bounding rectangle of a long diagonal.
      // Half-cell steps plus neighboring cells conservatively cover the 8px clearance.
      const steps = Math.ceil(Math.max(Math.abs(b.x - a.x), Math.abs(b.y - a.y)) / (CELL / 2))
      for (let i = 0; i <= steps; i++) {
        const x = Math.floor((a.x + (b.x - a.x) * i / steps) / CELL)
        const y = Math.floor((a.y + (b.y - a.y) * i / steps) / CELL)
        for (let dx = -1; dx <= 1; dx++) {
          for (let dy = -1; dy <= 1; dy++) keys.add(`${x + dx}:${y + dy}`)
        }
      }
    }
    return [...keys]
  }

  add(path: string) {
    const points = sampleRoute(path)
    points.slice(1).forEach((b, i) => {
      const segment = { a: points[i], b }
      this.keys(segment.a, b).forEach((key) => {
        const cell = this.cells.get(key) ?? []
        cell.push(segment)
        this.cells.set(key, cell)
      })
    })
  }

  cost = (a: RoutePoint, b: RoutePoint): number => {
    const ab = delta(a, b), length = Math.hypot(ab.x, ab.y)
    if (length < 0.001) return 0
    const candidates = new Set(this.keys(a, b).flatMap((key) => this.cells.get(key) ?? []))
    let cost = 0
    candidates.forEach(({ a: c, b: d }) => {
      const cd = delta(c, d), otherLength = Math.hypot(cd.x, cd.y)
      if (otherLength < 0.001) return
      const ac = delta(a, c), ad = delta(a, d)
      const determinant = cross(ab, cd)
      if (Math.abs(determinant) / (length * otherLength) < 0.12) {
        if (Math.min(Math.abs(cross(ab, ac)), Math.abs(cross(ab, ad))) / length >= 8) return
        const project = (v: RoutePoint) => (v.x * ab.x + v.y * ab.y) / length
        const overlap = Math.min(length, Math.max(project(ac), project(ad))) - Math.max(0, Math.min(project(ac), project(ad)))
        if (overlap > 0) cost += overlap * 200
      } else {
        const t = cross(ac, cd) / determinant, u = cross(ac, ab) / determinant
        if (t >= -0.000001 && t <= 1.000001 && u >= -0.000001 && u <= 1.000001) cost += 8000
      }
    })
    return cost
  }
}
