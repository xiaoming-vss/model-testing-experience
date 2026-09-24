import { useEffect, useMemo, useReducer, useState } from 'react'
import { RELATIONS_NODE_HEIGHT, RELATIONS_NODE_WIDTH } from '../utils/caseRelationsGraph'
import { previewRelationsRoutes, type RelationsRouteGeometry, type RelationsRouteResult } from '../utils/relationsRouting'

type RouteNode = { id: string; position: { x: number; y: number }; measured?: { width?: number; height?: number }; dragging?: boolean }
type RouteEdge = { id: string; source: string; target: string }
type MainPath = { caseIds: string[] }
type CompletedRoute = { key: string; attempt: number; paths: Map<string, string> | null }

/** Render cheap previews immediately; only settled geometry runs in a worker. */
export function useRelationsEdgePaths(nodes: RouteNode[], edges: RouteEdge[], paths: MainPath[]) {
  const [completed, setCompleted] = useState<CompletedRoute | null>(null)
  const [attempt, retry] = useReducer((value: number) => value + 1, 0)
  const cards = nodes.map((node) => ({
    id: node.id, ...node.position,
    width: node.measured?.width ?? RELATIONS_NODE_WIDTH,
    height: node.measured?.height ?? RELATIONS_NODE_HEIGHT,
  }))
  const mainPairs = new Set(paths.flatMap((path) => path.caseIds.slice(1).map((id, i) => JSON.stringify([path.caseIds[i], id]))))
  // Exclude presentation state and equal initial/measured sizes from the key.
  const geometryKey = JSON.stringify({
    cards,
    links: edges.map(({ id, source, target }) => ({ id, source, target, straight: mainPairs.has(JSON.stringify([source, target])) })),
  })
  const preview = useMemo(() => previewRelationsRoutes(JSON.parse(geometryKey) as RelationsRouteGeometry), [geometryKey])
  const dragging = nodes.some((node) => node.dragging)
  const jobKey = dragging || edges.length === 0 ? null : geometryKey

  useEffect(() => {
    if (!jobKey) return
    let active = true
    let worker: Worker | undefined
    const fail = () => {
      if (active) setCompleted({ key: jobKey, attempt, paths: null })
      worker?.terminate()
    }
    try {
      worker = new Worker(new URL('../workers/relationsRouting.worker.ts', import.meta.url), { type: 'module' })
      worker.onmessage = (event: MessageEvent<RelationsRouteResult>) => {
        if (active) setCompleted({ key: jobKey, attempt, paths: new Map(event.data.paths) })
        worker?.terminate()
      }
      worker.onerror = fail
      worker.onmessageerror = fail
      worker.postMessage(JSON.parse(jobKey) as RelationsRouteGeometry)
    } catch {
      // Never fall back to expensive synchronous routing on the UI thread.
      fail()
    }
    return () => {
      active = false
      worker?.terminate()
    }
  }, [jobKey, attempt])

  const current = completed?.key === geometryKey && completed.attempt === attempt ? completed : null
  return {
    paths: current?.paths ?? preview,
    error: !dragging && current !== null && current.paths === null,
    pending: jobKey !== null && current === null,
    retry,
  }
}
