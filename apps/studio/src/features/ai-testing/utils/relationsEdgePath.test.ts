import { describe, expect, it } from 'vitest'
import { routeRelationsEdge, type RoutePoint, type RouteRect } from './relationsEdgePath'
import { computeRelationsRoutes } from './relationsRouting'
import { buildRelationsGraphModel, layoutRelationsFishbone, parseCaseRelationsContent } from './caseRelationsGraph'

const card = (id: string, x: number, y: number): RouteRect => ({ id, x, y, width: 236, height: 96 })
// Sample the actual SVG, independently of the routing collision checks.
function sample(path: string): RoutePoint[] {
  const tokens = path.match(/[MLQ]|-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/g) ?? []
  const points: RoutePoint[] = []
  let cursor = { x: 0, y: 0 }
  let i = 0
  const point = () => ({ x: Number(tokens[i++]), y: Number(tokens[i++]) })
  while (i < tokens.length) {
    const command = tokens[i++]
    if (command === 'M') { cursor = point(); points.push(cursor); continue }
    const control = command === 'Q' ? point() : null
    const end = point()
    for (let j = 1; j <= 300; j++) {
      const t = j / 300, u = 1 - t
      points.push(control ? {
        x: u * u * cursor.x + 2 * u * t * control.x + t * t * end.x,
        y: u * u * cursor.y + 2 * u * t * control.y + t * t * end.y,
      } : { x: cursor.x * u + end.x * t, y: cursor.y * u + end.y * t })
    }
    cursor = end
  }
  return points
}
function expectClear(path: string, cards: RouteRect[]) {
  expect(path).not.toBe('')
  for (const p of sample(path)) {
    expect(cards.some((r) => p.x > r.x + 0.01 && p.x < r.x + r.width - 0.01 && p.y > r.y + 0.01 && p.y < r.y + r.height - 0.01), `path enters a card at ${p.x},${p.y}`).toBe(false)
  }
}

describe('card-aware relation paths', () => {
  it('keeps unobstructed mainlines straight and clips both endpoints', () => {
    const a = card('a', 0, 0), b = card('b', 600, 0)
    const path = routeRelationsEdge(a, b, [a, b], true)
    expect(path).toBe('M 236,48 L 600,48')
    expectClear(path, [a, b])
  })
  it('curves branches while keeping mainlines straight and cards clear', () => {
    const a = card('a', 500, 500), b = card('b', 240, 124)
    const path = routeRelationsEdge(a, b, [a, b], false)
    expect(path).toContain('Q')
    expectClear(path, [a, b])
    const aligned = card('aligned', 900, 500)
    expect(routeRelationsEdge(a, aligned, [a, aligned], false)).toContain('Q')
  })
  it.each([false, true])('fans connections out through separate ports instead of sharing a trunk, main=%s', (straight) => {
    const cards = [card('a', 0, 0), card('b', 0, 260), card('c', 0, 520), card('d', 0, 780)]
    const links = cards.slice(1).map((target) => ({ id: target.id, source: 'a', target: target.id, straight }))
    const paths = computeRelationsRoutes({ cards, links }).paths.map(([, path]) => path)
    paths.forEach((path) => expectClear(path, cards))
    const starts = paths.map((path) => sample(path)[0])
    expect(new Set(starts.map((p) => `${p.x},${p.y}`)).size).toBe(links.length)
    // A repeated segment means two visible edges share the same corridor.
    const segments = paths.map((path) => {
      const points = sample(path)
      return points.slice(1).map((p, i) => [points[i], p])
    })
    segments.forEach((first, i) => segments.slice(i + 1).forEach((second) => {
      const overlapping = first.some(([a, b]) => second.some(([c, d]) => {
        const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy)
        if (length < 0.01) return false
        const onLine = (p: RoutePoint) => Math.abs(dx * (p.y - a.y) - dy * (p.x - a.x)) / length < 0.01
        if (!onLine(c) || !onLine(d)) return false
        const project = (p: RoutePoint) => ((p.x - a.x) * dx + (p.y - a.y) * dy) / length
        return Math.min(length, Math.max(project(c), project(d))) - Math.max(0, Math.min(project(c), project(d))) > 0.05
      }))
      expect(overlapping).toBe(false)
    }))
  })
  it.each([false, true])('takes a free outer corridor instead of crossing an existing mainline, main=%s', (straight) => {
    const cards = [card('left', 0, 400), card('right', 900, 400), card('top', 400, 0), card('bottom', 400, 800)]
    const result = new Map(computeRelationsRoutes({ cards, links: [
      { id: 'main', source: 'left', target: 'right', straight: true },
      { id: 'branch', source: 'top', target: 'bottom', straight },
    ] }).paths)
    const branch = result.get('branch')!
    expectClear(branch, cards)
    const points = sample(branch)
    points.slice(1).forEach((b, i) => {
      const a = points[i]
      if ((a.y < 448) === (b.y < 448)) return
      const x = a.x + (b.x - a.x) * (448 - a.y) / (b.y - a.y)
      expect(x < 0 || x > 1136).toBe(true)
    })
  })
  it.each([false, true])('avoids multiple blocking cards, vertical=%s', (vertical) => {
    const cards = [card('a', 0, 0), card('b', 1000, 0), card('c', 330, -30), card('d', 620, -70)]
      .map((r) => vertical ? { ...r, x: r.y, y: r.x, width: r.height, height: r.width } : r)
    const path = routeRelationsEdge(cards[0], cards[1], cards, true)
    expect(path).toContain('Q')
    expectClear(path, cards)
  })
  it('keeps edges visible when a nearby branch leaves only a narrow passage', () => {
    const a = card('a', 0, 0), b = card('b', 900, 0), c = card('c', 260, 56)
    expectClear(routeRelationsEdge(a, b, [a, b, c], true), [a, b, c])
  })
  it('reroutes when an unrelated card is dragged into a mainline', () => {
    const a = card('a', 0, 0), b = card('b', 900, 0), c = card('c', 400, 200)
    const before = routeRelationsEdge(a, b, [a, b, c], true)
    const moved = { ...c, y: 0 }
    const after = routeRelationsEdge(a, b, [a, b, moved], true)
    expect(after).not.toBe(before)
    expectClear(after, [a, b, moved])
  })
  it.each(['horizontal', 'vertical'] as const)('keeps all multi-level branch edges visible in %s', (orientation) => {
    const pairs = [['1', '8'], ['8', '9'], ['9', '21'], ['1', '2'], ['1', '3'], ['1', '4'], ['1', '5'], ['1', '6'], ['3', '7'], ['9', '10'], ['9', '12'], ['9', '14'], ['9', '15'], ['9', '16'], ['10', '11'], ['10', '22'], ['10', '13'], ['14', '17'], ['14', '18'], ['16', '19'], ['16', '20']]
    const data = parseCaseRelationsContent(JSON.stringify({
      main_paths: [{ case_ids: ['1', '8', '9', '21'] }],
      edges: pairs.map(([from, to], i) => ({ from_case_id: from, to_case_id: to, relation_type: i < 3 ? 'next' : 'branch', order: i })),
    }))!
    const model = buildRelationsGraphModel(data, new Map())
    const layout = layoutRelationsFishbone(model, orientation)
    const cards = [...layout.nodes.values()].map((n) => card(n.caseId, n.x, n.y))
    expect(cards).toHaveLength(22)
    for (const edge of model.edges) {
      const a = cards.find((r) => r.id === edge.fromCaseId)!, b = cards.find((r) => r.id === edge.toCaseId)!
      expectClear(routeRelationsEdge(a, b, cards, edge.relationType === 'next'), cards)
    }
  })
  it.each(['horizontal', 'vertical'] as const)('routes dense fishbone branches in %s layout', (orientation) => {
    const edges = Array.from({ length: 12 }, (_, i) => ({ from_case_id: 'root', to_case_id: `b${i}`, relation_type: 'branch' }))
    const data = parseCaseRelationsContent(JSON.stringify({ main_paths: [{ case_ids: ['root', 'end'] }], edges }))!
    const model = buildRelationsGraphModel(data, new Map())
    const layout = layoutRelationsFishbone(model, orientation)
    const cards = [...layout.nodes.values()].map((n) => card(n.caseId, n.x, n.y))
    for (const e of model.edges) {
      const a = cards.find((r) => r.id === e.fromCaseId)!, b = cards.find((r) => r.id === e.toCaseId)!
      expectClear(routeRelationsEdge(a, b, cards, false), cards)
    }
  })
})

// Match the reported test order, including routes across other rows. Full routing
// runs in a worker; the interactive frame budget is tested in useRelationsEdgePaths.
it('routes 126 cards without missing or intersecting paths', () => {
  const cards = Array.from({ length: 126 }, (_, i) => card(String(i), (i % 14) * 300, Math.floor(i / 14) * 160))
  const paths = cards.map((source, i) => routeRelationsEdge(source, cards[(i + 16) % cards.length], cards, false))
  expect(paths.every(Boolean)).toBe(true)
  for (const path of paths) expectClear(path, cards)
}, 30000)

it('keeps every relation in a 126-node multi-mainline layout without crossing or overlapping mainlines', () => {
  const paths = Array.from({ length: 6 }, (_, p) => ({ pathId: `p${p}`, caseIds: Array.from({ length: 7 }, (_, i) => `p${p}m${i}`) }))
  const edges = paths.flatMap((path) => path.caseIds.flatMap((id, i) => [
    ...(i ? [{ edgeId: `main-${id}`, fromCaseId: path.caseIds[i - 1], toCaseId: id, relationType: 'next' as const, order: i }] : []),
    ...[0, 1].map((b) => ({ edgeId: `${id}b${b}`, fromCaseId: id, toCaseId: `${id}b${b}`, relationType: 'branch' as const, order: b })),
  ]))
  edges.push({ edgeId: 'cross1', fromCaseId: 'p0m4', toCaseId: 'p2m6', relationType: 'next', order: 1 })
  edges.push({ edgeId: 'cross2', fromCaseId: 'p0m4', toCaseId: 'p4m3', relationType: 'next', order: 2 })
  const model = buildRelationsGraphModel({ paths, edges }, new Map())
  const layout = layoutRelationsFishbone(model, 'horizontal')
  const cards = [...layout.nodes.values()].map((n) => card(n.caseId, n.x, n.y))
  const links = edges.map((e) => ({ id: e.edgeId, source: e.fromCaseId, target: e.toCaseId, straight: e.edgeId.startsWith('main-') }))
  const result = computeRelationsRoutes({ cards, links })
  expect(cards).toHaveLength(126)
  expect(result.blockedEdgeIds).toEqual([])
  expect(result.paths).toHaveLength(122)
  const mains = result.paths.filter(([id]) => id.startsWith('main-')).map(([id, path]) => {
    expect(path).not.toContain('Q')
    const points = sample(path)
    return { id, a: points[0], b: points.at(-1)! }
  })
  for (const [id, path] of result.paths) {
    expectClear(path, cards)
    const points = sample(path)
    for (const main of mains) {
      if (main.id === id) continue
      points.slice(1).forEach((b, i) => {
        const a = points[i], y = main.a.y
        if (Math.abs(a.y - y) < 0.01 && Math.abs(b.y - y) < 0.01) {
          expect(Math.min(Math.max(a.x, b.x), main.b.x) - Math.max(Math.min(a.x, b.x), main.a.x)).toBeLessThanOrEqual(0)
        } else if ((a.y < y) !== (b.y < y)) {
          const x = a.x + (b.x - a.x) * (y - a.y) / (b.y - a.y)
          expect(x < main.a.x || x > main.b.x).toBe(true)
        }
      })
    }
  }
}, 30000)
