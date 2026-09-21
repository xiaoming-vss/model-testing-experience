import { describe, expect, it } from 'vitest'
import { routeRelationsEdge, type RoutePoint, type RouteRect } from './relationsEdgePath'
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
  it('curves branches without cutting either endpoint card', () => {
    const a = card('a', 500, 500), b = card('b', 240, 124)
    const path = routeRelationsEdge(a, b, [a, b], false)
    expect(path).toContain('Q')
    expectClear(path, [a, b])
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
