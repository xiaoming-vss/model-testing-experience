import { StrictMode } from 'react'
import { act, cleanup, renderHook } from '@testing-library/react'
import { applyNodeChanges } from '@xyflow/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as routing from '../utils/relationsEdgePath'
import { computeRelationsRoutes, type RelationsRouteGeometry, type RelationsRouteResult } from '../utils/relationsRouting'
import { useRelationsEdgePaths } from './useRelationsEdgePaths'

class ControlledWorker {
  static instances: ControlledWorker[] = []
  onmessage: ((event: MessageEvent<RelationsRouteResult>) => void) | null = null
  onerror: (() => void) | null = null
  onmessageerror: (() => void) | null = null
  postMessage = vi.fn<(geometry: RelationsRouteGeometry) => void>()
  terminate = vi.fn()
  constructor() { ControlledWorker.instances.push(this) }
  finish() {
    const data = computeRelationsRoutes(this.postMessage.mock.calls[0][0])
    act(() => this.onmessage?.({ data } as MessageEvent<RelationsRouteResult>))
  }
}
const latestWorker = () => ControlledWorker.instances.at(-1)!
const initialNodes = [
  { id: 'a', position: { x: 0, y: 0 }, selected: false, dragging: false },
  { id: 'b', position: { x: 900, y: 0 }, selected: false, dragging: false },
  { id: 'c', position: { x: 400, y: 200 }, selected: false, dragging: false },
]
const initialEdges = [{ id: 'ab', source: 'a', target: 'b', style: { stroke: 'blue' } }]
const paths = [{ caseIds: ['a', 'b'] }]
beforeEach(() => {
  ControlledWorker.instances = []
  vi.stubGlobal('Worker', ControlledWorker)
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('reuses completed routes for selection, styling and unchanged measured sizes', () => {
  const { result, rerender } = renderHook(({ nodes, edges }) => useRelationsEdgePaths(nodes, edges, paths), {
    initialProps: { nodes: initialNodes, edges: initialEdges },
  })
  latestWorker().finish()
  const original = result.current.paths
  rerender({
    nodes: initialNodes.map((node) => ({ ...node, selected: true, measured: { width: 236, height: 96 } })),
    edges: initialEdges.map((edge) => ({ ...edge, style: { stroke: 'gray' } })),
  })
  expect(result.current.paths).toBe(original)
  expect(ControlledWorker.instances).toHaveLength(1)
})

it('restores full avoidance of an unrelated moved obstacle after release', () => {
  const { result, rerender } = renderHook(({ nodes }) => useRelationsEdgePaths(nodes, initialEdges, paths), {
    initialProps: { nodes: initialNodes },
  })
  latestWorker().finish()
  const original = result.current.paths.get('ab')
  const moved = initialNodes.map((node) => node.id === 'c' ? { ...node, dragging: true, position: { x: 400, y: 0 } } : node)
  rerender({ nodes: moved })
  expect(ControlledWorker.instances).toHaveLength(1)
  expect(result.current.pending).toBe(false)
  expect(result.current.paths.get('ab')).toBe(original) // temporary preview can cross c
  rerender({ nodes: moved.map((node) => ({ ...node, dragging: false })) })
  expect(result.current.pending).toBe(true)
  expect(ControlledWorker.instances).toHaveLength(2)
  latestWorker().finish()
  expect(result.current.paths.get('ab')).not.toBe(original)
  expect(result.current.paths.get('ab')).toContain('Q')
  expect(result.current.pending).toBe(false)
})

it('invalidates routes on size, orientation, membership, endpoint and removal changes', () => {
  const { result, rerender } = renderHook(({ nodes, edges, mainPaths }) => useRelationsEdgePaths(nodes, edges, mainPaths), {
    initialProps: { nodes: initialNodes, edges: initialEdges, mainPaths: paths },
  })
  latestWorker().finish()
  const horizontal = result.current.paths.get('ab')
  const vertical = initialNodes.map((node) => ({ ...node, position: { x: node.position.y, y: node.position.x } }))
  rerender({ nodes: vertical, edges: initialEdges, mainPaths: paths })
  latestWorker().finish()
  expect(result.current.paths.get('ab')).not.toBe(horizontal)
  rerender({ nodes: vertical.map((node) => ({ ...node, measured: { width: 240, height: 100 } })), edges: initialEdges, mainPaths: paths })
  expect(ControlledWorker.instances).toHaveLength(3)
  rerender({ nodes: initialNodes, edges: initialEdges, mainPaths: [] })
  latestWorker().finish()
  expect(result.current.paths.get('ab')).toContain('Q')
  rerender({ nodes: initialNodes, edges: [{ ...initialEdges[0], target: 'c' }], mainPaths: [] })
  expect(ControlledWorker.instances).toHaveLength(5)
  rerender({ nodes: initialNodes, edges: [], mainPaths: [] })
  expect(result.current.paths.size).toBe(0)
  expect(latestWorker().terminate).toHaveBeenCalled()
})

it('cancels obsolete jobs and ignores responses after a new drag or unmount', () => {
  const { result, rerender, unmount } = renderHook(({ nodes }) => useRelationsEdgePaths(nodes, initialEdges, paths), {
    initialProps: { nodes: initialNodes },
  })
  const obsolete = latestWorker()
  const moved = initialNodes.map((node) => node.id === 'a' ? { ...node, dragging: true, position: { x: 30, y: 40 } } : node)
  rerender({ nodes: moved })
  expect(obsolete.terminate).toHaveBeenCalled()
  const preview = result.current.paths
  obsolete.finish()
  expect(result.current.paths).toBe(preview)
  rerender({ nodes: moved.map((node) => ({ ...node, dragging: false })) })
  const fresh = latestWorker()
  fresh.finish()
  const final = result.current.paths
  obsolete.finish()
  expect(result.current.paths).toBe(final)
  unmount()
  expect(fresh.terminate).toHaveBeenCalled()
  fresh.finish()
})

it.each(['onerror', 'onmessageerror'] as const)('keeps previews responsive and allows retry after %s', (failure) => {
  const route = vi.spyOn(routing, 'routeRelationsEdge')
  const { result } = renderHook(() => useRelationsEdgePaths(initialNodes, initialEdges, paths))
  act(() => latestWorker()[failure]?.())
  expect(result.current.error).toBe(true)
  expect(result.current.paths.get('ab')).toBeTruthy()
  expect(route.mock.calls.length).toBe(0)
  act(() => result.current.retry())
  expect(result.current.pending).toBe(true)
  latestWorker().finish()
  expect(result.current.error).toBe(false)
  expect(result.current.pending).toBe(false)
})

it('reports worker construction failure without synchronous full routing', () => {
  vi.stubGlobal('Worker', class { constructor() { throw new Error('blocked') } })
  const route = vi.spyOn(routing, 'routeRelationsEdge')
  const { result } = renderHook(() => useRelationsEdgePaths(initialNodes, initialEdges, paths))
  expect(result.current.error).toBe(true)
  expect(route.mock.calls.length).toBe(0)
})

it('cleans up the first StrictMode worker before accepting the active response', () => {
  const { result, unmount } = renderHook(() => useRelationsEdgePaths(initialNodes, initialEdges, paths), { wrapper: StrictMode })
  expect(ControlledWorker.instances).toHaveLength(2)
  expect(ControlledWorker.instances[0].terminate).toHaveBeenCalled()
  ControlledWorker.instances[0].finish()
  expect(result.current.pending).toBe(true)
  latestWorker().finish()
  expect(result.current.pending).toBe(false)
  unmount()
  expect(latestWorker().terminate).toHaveBeenCalled()
})

it('keeps 60 drag updates under the frame budget without full routing or worker jobs', () => {
  const route = vi.spyOn(routing, 'routeRelationsEdge')
  let nodes = Array.from({ length: 126 }, (_, i) => ({ id: String(i), position: { x: (i % 14) * 300, y: Math.floor(i / 14) * 160 }, data: {} }))
  const edges = nodes.map((node, i) => ({ id: `e${i}`, source: node.id, target: String((i + 16) % 126) }))
  const { result, rerender } = renderHook(({ nodes }) => useRelationsEdgePaths(nodes, edges, []), { initialProps: { nodes } })
  const original = result.current.paths.get('e60')
  const start = performance.now()
  for (let i = 1; i <= 60; i++) {
    nodes = applyNodeChanges([{ id: '60', type: 'position', position: { x: 1200 + i * 3, y: 640 + i * 2 }, dragging: true }], nodes)
    rerender({ nodes })
  }
  const elapsed = performance.now() - start
  expect(route.mock.calls.length).toBe(0)
  expect(ControlledWorker.instances).toHaveLength(1)
  expect(result.current.paths.get('e60')).not.toBe(original)
  expect(result.current.paths.size).toBe(126)
  expect(elapsed / 60).toBeLessThan(16.7)
  nodes = applyNodeChanges([{ id: '60', type: 'position', dragging: false }], nodes)
  rerender({ nodes })
  expect(ControlledWorker.instances).toHaveLength(2)
  expect(route.mock.calls.length).toBe(0)
})
