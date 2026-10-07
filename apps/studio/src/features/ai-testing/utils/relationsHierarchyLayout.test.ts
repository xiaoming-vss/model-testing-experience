import source from './relationsHierarchy.fixture.json?raw'
import { expect, it } from 'vitest'
import { RELATIONS_NODE_WIDTH, buildRelationsGraphModel, parseCaseRelationsContent, parseDetailedCaseMeta, type RelationsGraphModel } from './caseRelationsGraph'
import { buildHierarchyGroups } from './relationsHierarchyGroups'
import { HIERARCHY_NODE_HEIGHT, layoutHierarchy, type HierarchyLayout } from './relationsHierarchyLayout'
import { hierarchyPreferredPaths } from './relationsHierarchyPaths'
import { computeRelationsRoutes, validPreferredRelationPath } from './relationsRouting'

const model = buildRelationsGraphModel(parseCaseRelationsContent(source)!, new Map())
const groups = buildHierarchyGroups(model)
const allExpanded = new Set(model.nodes.map((node) => node.caseId))
function cards(layout: HierarchyLayout) {
  return [...layout.nodes].map(([id, node]) => ({ id, x: node.x, y: node.y, width: RELATIONS_NODE_WIDTH, height: HIERARCHY_NODE_HEIGHT }))
}
function expectNoOverlap(layout: HierarchyLayout) {
  const rects = cards(layout)
  rects.forEach((a, i) => rects.slice(i + 1).forEach((b) => {
    expect(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y, `${a.id} overlaps ${b.id}`).toBe(true)
  }))
}
function routes(layout: HierarchyLayout) {
  const preferred = hierarchyPreferredPaths(layout)
  return computeRelationsRoutes({ cards: cards(layout), links: layout.edges.map((edge) => ({ id: edge.edgeId, source: edge.source, target: edge.target, straight: edge.main, orthogonal: true, preferredPath: preferred.get(edge.edgeId) })) })
}

it('shows all three horizontal main paths together when branches are collapsed', () => {
  const layout = layoutHierarchy(model, groups, new Set())
  model.paths.forEach((path) => {
    const main = [...layout.nodes.values()].filter((node) => node.main && node.groupId === `path:${path.pathId}`)
    expect(main.map((node) => node.meta.caseId)).toEqual(path.caseIds)
    expect(new Set(main.map((node) => node.y)).size).toBe(1)
    expect(main.every((node, i) => i === 0 || node.x > main[i - 1].x)).toBe(true)
  })
  expect([...layout.nodes.values()].some((node) => node.groupLabel === '其他关联')).toBe(true)
  expect([...layout.nodes.values()].some((node) => node.meta.caseId.startsWith('b29fd7e4'))).toBe(false)
  expectNoOverlap(layout)
})

it('retains all 78 cases and 76 relations together when expanded, without overlapping cards', () => {
  const layout = layoutHierarchy(model, groups, allExpanded)
  expect(new Set([...layout.nodes.values()].map((node) => node.meta.caseId)).size).toBe(78)
  expect(new Set(layout.edges.map((edge) => edge.relationId)).size).toBe(76)
  expectNoOverlap(layout)
  hierarchyPreferredPaths(layout).forEach((path) => expect(validPreferredRelationPath(path, cards(layout))).toBe(true))
})

it('expands a real three-level branch in successive columns and collapses only its descendants', () => {
  const expanded = new Set(['5c64e328-3d35-4185-a659-6c4f05a2de42', 'b29fd7e4-c888-4e27-ba3f-65b5ac962173', '6d44efda-feb8-44fe-8e75-3c458e7088bd'])
  const layout = layoutHierarchy(model, groups, expanded)
  const find = (prefix: string) => [...layout.nodes.values()].find((node) => node.meta.caseId.startsWith(prefix))!
  const [root, child, leaf] = ['b29fd7e4', '6d44efda', 'bbdcdee1'].map(find)
  expect([root.depth, child.depth, leaf.depth]).toEqual([1, 2, 3])
  expect(root.x).toBeLessThan(child.x)
  expect(child.x).toBeLessThan(leaf.x)
  expectNoOverlap(layout)
  expanded.delete(child.meta.caseId)
  const collapsed = layoutHierarchy(model, groups, expanded)
  expect([...collapsed.nodes.values()].some((node) => node.meta.caseId === leaf.meta.caseId)).toBe(false)
  expect([...collapsed.nodes.values()].filter((node) => node.depth === 2)).toHaveLength(3)
  expect(collapsed.paths).toHaveLength(4)
  expectNoOverlap(collapsed)
})

function synthetic(edges: [string, string][], paths = [['main', 'end']]): RelationsGraphModel {
  return buildRelationsGraphModel({ paths: paths.map((caseIds, i) => ({ pathId: `P${i + 1}`, caseIds })),
    edges: edges.map(([fromCaseId, toCaseId], i) => ({ edgeId: `E${i}`, fromCaseId, toCaseId, relationType: i === 0 ? 'next' : 'branch', order: i })) }, new Map())
}

it('retains shared descendants and cycle edges without duplicating cases within a path', () => {
  const cyclic = synthetic([['main', 'end'], ['main', 'a'], ['a', 'b'], ['a', 'c'], ['b', 'd'], ['c', 'd'], ['d', 'a']])
  const layout = layoutHierarchy(cyclic, buildHierarchyGroups(cyclic), new Set(cyclic.nodes.map((node) => node.caseId)))
  expect(layout.nodes.size).toBe(6)
  expect(layout.edges).toHaveLength(7)
  expectNoOverlap(layout)
  expect(routes(layout).paths.filter(([, path]) => path)).toHaveLength(7)
})

it('keeps shared main-case identity across paths and includes isolated cases', () => {
  const shared = synthetic([['main', 'end'], ['main', 'other']], [['main', 'end'], ['main', 'other']])
  const layout = layoutHierarchy(shared, buildHierarchyGroups(shared), new Set())
  const mainCopies = [...layout.nodes.values()].filter((node) => node.meta.caseId === 'main')
  expect(mainCopies).toHaveLength(2)
  expect(mainCopies.every((node) => node.meta.shared)).toBe(true)
  expectNoOverlap(layout)
  const withIsolated = buildRelationsGraphModel({ paths: [{ pathId: 'P', caseIds: ['main'] }], edges: [] }, parseDetailedCaseMeta(JSON.stringify({ cases: [{ case_id: 'solo', case_title: '独立用例' }] })))
  const isolated = layoutHierarchy(withIsolated, buildHierarchyGroups(withIsolated), new Set())
  expect([...isolated.nodes.values()].some((node) => node.meta.caseId === 'solo')).toBe(true)
})
