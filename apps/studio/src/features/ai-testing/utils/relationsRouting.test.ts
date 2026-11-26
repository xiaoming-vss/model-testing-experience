import { expect, it } from 'vitest'
import { RELATIONS_NODE_HEIGHT, RELATIONS_NODE_WIDTH } from './caseRelationsGraph'
import { computeRelationsRoutes } from './relationsRouting'

it('streams routes for a 126-card layout before completing every link', () => {
  const cards = Array.from({ length: 126 }, (_, index) => ({
    id: `card-${index}`,
    x: (index % 14) * (RELATIONS_NODE_WIDTH + 64),
    y: Math.floor(index / 14) * (RELATIONS_NODE_HEIGHT + 64),
    width: RELATIONS_NODE_WIDTH,
    height: RELATIONS_NODE_HEIGHT,
  }))
  const links: { id: string; source: string; target: string; straight: boolean }[] = []
  for (let row = 0; row < 9; row++) {
    for (let column = 0; column < 13; column++) {
      links.push({ id: `right-${row}-${column}`, source: `card-${row * 14 + column}`, target: `card-${row * 14 + column + 1}`, straight: true })
    }
  }
  for (const [row, column] of [[0, 7], [2, 3], [4, 11], [6, 5], [7, 9]]) {
    links.push({ id: `down-${row}-${column}`, source: `card-${row * 14 + column}`, target: `card-${(row + 1) * 14 + column}`, straight: false })
  }
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
  expect(cards).toHaveLength(126)
  expect(links).toHaveLength(122)
  expect(firstVisibleMs).toBeLessThan(500)
  expect(firstVisibleCount).toBeLessThan(links.length)
  expect(result.done).toBe(true)
  expect(result.blockedEdgeIds).toEqual([])
  expect(result.paths.filter(([, path]) => Boolean(path))).toHaveLength(122)
  expect(performance.now() - start).toBeLessThan(5000)
}, 30000)
