import { expect, it } from 'vitest'
import { buildRelationsGraphModel, layoutRelationsFishbone, RELATIONS_NODE_HEIGHT, RELATIONS_NODE_WIDTH } from './caseRelationsGraph'
import { computeRelationsRoutes } from './relationsRouting'

it('streams mainlines before completing a 126-node graph with shared mainline roots', () => {
  const paths = [4, 4, 4, 4, 22, 4].map((length, p) => ({
    pathId: `p${p}`, caseIds: ['root', ...Array.from({ length: length - 1 }, (_, i) => `p${p}-${i}`)],
  }))
  const anchors = [...new Set(paths.flatMap((p) => p.caseIds))]
  const edges = paths.flatMap((path) => path.caseIds.slice(1).map((id, i) => ({
    edgeId: `main-${id}`, fromCaseId: path.caseIds[i], toCaseId: id, relationType: 'next' as const, order: i,
  })))
  const data = { paths, edges: [...edges, ...Array.from({ length: 86 }, (_, i) => ({
    edgeId: `branch-${i}`, fromCaseId: anchors[1 + (i * 7) % (anchors.length - 1)], toCaseId: `branch-${i}`, relationType: 'branch' as const, order: i,
  }))] }
  const model = buildRelationsGraphModel(data, new Map())
  const layout = layoutRelationsFishbone(model, 'horizontal')
  const cards = [...layout.nodes].map(([id, n]) => ({ id, x: n.x, y: n.y, width: RELATIONS_NODE_WIDTH, height: RELATIONS_NODE_HEIGHT }))
  for (let i = 0; i < 3; i++) cards.push({ id: `solo-${i}`, x: 48 + i * 416, y: layout.height + 200, width: 236, height: 96 })
  const links = layout.edges.map((e) => ({ id: e.edgeId, source: e.fromCaseId, target: e.toCaseId, straight: e.edgeId.startsWith('main-') }))
  const start = performance.now()
  let firstVisibleMs: number | undefined
  let firstVisibleCount = 0
  const result = computeRelationsRoutes({ cards, links }, (progress) => {
    if (firstVisibleMs === undefined && progress.paths.some(([, path]) => path)) {
      firstVisibleMs = performance.now() - start
      firstVisibleCount = progress.paths.length
      expect(progress.done).toBe(false)
    }
  })
  expect(model.nodes).toHaveLength(123) // plus 3 isolated cases, and 5 visual copies of the shared root
  expect(cards).toHaveLength(131)
  expect(links).toHaveLength(122)
  expect(firstVisibleMs).toBeLessThan(500)
  expect(firstVisibleCount).toBeLessThan(links.length)
  expect(result.done).toBe(true)
  expect(result.blockedEdgeIds).toEqual([])
  expect(result.paths.filter(([, path]) => Boolean(path))).toHaveLength(122)
  expect(performance.now() - start).toBeLessThan(5000)
}, 30000)
