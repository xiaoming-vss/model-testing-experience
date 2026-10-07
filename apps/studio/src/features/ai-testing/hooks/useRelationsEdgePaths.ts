import { useEffect, useMemo, useReducer, useState } from 'react'
import { RELATIONS_NODE_HEIGHT, RELATIONS_NODE_WIDTH } from '../utils/caseRelationsGraph'
import { previewRelationsRoutes, validPreferredRelationPath, type RelationsRouteGeometry, type RelationsRouteResult } from '../utils/relationsRouting'

type RouteNode = { id: string; position: { x: number; y: number }; width?: number; height?: number; measured?: { width?: number; height?: number }; dragging?: boolean }
type RouteEdge = { id: string; source: string; target: string }
type MainPath = { caseIds: string[] }
type CompletedRoute = { key: string; attempt: number; paths: Map<string, string> | null; blockedEdgeIds?: string[]; done?: boolean; failed?: boolean }

/** Show validated worker batches progressively; dragging uses cheap temporary previews. */
export function useRelationsEdgePaths(nodes: RouteNode[], edges: RouteEdge[], paths: MainPath[], preferences?: { paths: Map<string, string>; orthogonal: boolean }) {
  const [completed, setCompleted] = useState<CompletedRoute | null>(null)
  const [attempt, retry] = useReducer((value: number) => value + 1, 0)
  const cards = nodes.map((node) => ({
    id: node.id, ...node.position,
    width: node.measured?.width ?? node.width ?? RELATIONS_NODE_WIDTH,
    height: node.measured?.height ?? node.height ?? RELATIONS_NODE_HEIGHT,
  }))
  const mainPairs = new Set(paths.flatMap((path) => path.caseIds.slice(1).map((id, i) => JSON.stringify([path.caseIds[i], id]))))
  // Exclude presentation state and equal initial/measured sizes from the key.
  const geometryKey = JSON.stringify({
    cards,
    links: edges.map(({ id, source, target }) => ({ id, source, target, straight: mainPairs.has(JSON.stringify([source, target])),
      ...(preferences ? { preferredPath: preferences.paths.get(id), orthogonal: preferences.orthogonal } : {}),
    })),
  })
  const preview = useMemo(() => previewRelationsRoutes(JSON.parse(geometryKey) as RelationsRouteGeometry), [geometryKey])
  const preferred = useMemo(() => {
    const geometry = JSON.parse(geometryKey) as RelationsRouteGeometry
    return new Map(geometry.links.filter((link) => link.preferredPath && validPreferredRelationPath(link.preferredPath, geometry.cards)).map((link) => [link.id, link.preferredPath!]))
  }, [geometryKey])
  const dragging = nodes.some((node) => node.dragging)
  const jobKey = dragging || edges.length === 0 ? null : geometryKey

  useEffect(() => {
    if (!jobKey) return
    let active = true
    let worker: Worker | undefined
    let watchdog: ReturnType<typeof setTimeout> | undefined
    let latestPaths: Map<string, string> | null = null
    let latestBlocked: string[] = []
    const fail = () => {
      if (active) setCompleted({ key: jobKey, attempt, paths: latestPaths, blockedEdgeIds: latestBlocked, done: true, failed: true })
      clearTimeout(watchdog)
      worker?.terminate()
    }
    try {
      worker = new Worker(new URL('../workers/relationsRouting.worker.ts', import.meta.url), { type: 'module' })
      worker.onmessage = (event: MessageEvent<RelationsRouteResult>) => {
        if (!active) return
        latestPaths = new Map(event.data.paths)
        latestBlocked = event.data.blockedEdgeIds ?? []
        const done = event.data.done !== false
        setCompleted({ key: jobKey, attempt, paths: latestPaths, blockedEdgeIds: latestBlocked, done })
        clearTimeout(watchdog)
        if (done) worker?.terminate()
        else watchdog = setTimeout(fail, 15000)
      }
      worker.onerror = fail
      worker.onmessageerror = fail
      watchdog = setTimeout(fail, 15000)
      worker.postMessage(JSON.parse(jobKey) as RelationsRouteGeometry)
    } catch {
      // Never fall back to expensive synchronous routing on the UI thread.
      fail()
    }
    return () => {
      active = false
      clearTimeout(watchdog)
      worker?.terminate()
    }
  }, [jobKey, attempt])

  const current = completed?.key === geometryKey && completed.attempt === attempt ? completed : null
  const currentPaths = current?.paths
  const visiblePaths = useMemo(() => {
    if (!preferred.size) return currentPaths ?? preferred
    const merged = new Map(preferred)
    currentPaths?.forEach((path, id) => merged.set(id, path))
    return merged
  }, [preferred, currentPaths])
  return {
    paths: dragging ? preview : visiblePaths,
    blockedEdgeIds: current?.blockedEdgeIds ?? [],
    error: !dragging && current !== null && Boolean(current.failed),
    pending: jobKey !== null && (!current || current.done === false),
    retry,
  }
}
