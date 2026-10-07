import { useCallback, useEffect, useImperativeHandle, useRef, type Ref } from 'react'
import { useReactFlow } from '@xyflow/react'
import { RELATIONS_NODE_WIDTH } from '../utils/caseRelationsGraph'
import { HIERARCHY_NODE_HEIGHT, HIERARCHY_MIN_ZOOM, type HierarchyLayout } from '../utils/relationsHierarchyLayout'
import type { FunctionalCaseRelationsGraphHandle } from '../components/FunctionalCaseRelationsGraph'

export function useHierarchyViewport(layout: HierarchyLayout | null, selectedId: string | null, handleRef: Ref<FunctionalCaseRelationsGraphHandle>, anchorId: string | null) {
  const canvasRef = useRef<HTMLDivElement>(null)
  const previousLayout = useRef<HierarchyLayout | null>(null)
  const flow = useReactFlow(), flowRef = useRef(flow)
  useEffect(() => { flowRef.current = flow }, [flow])
  const stateRef = useRef({ layout, selectedId })
  useEffect(() => { stateRef.current = { layout, selectedId } }, [layout, selectedId])
  const fitView = useCallback((readable = false) => {
    const canvas = canvasRef.current, state = stateRef.current
    const nodes = state.layout ? [...state.layout.nodes.values()] : []
    if (!canvas || !nodes.length || canvas.clientHeight <= 0) return
    const width = canvas.clientWidth
    const minX = Math.min(...nodes.map((node) => node.x)), minY = Math.min(...nodes.map((node) => node.y))
    const maxX = Math.max(...nodes.map((node) => node.x + RELATIONS_NODE_WIDTH))
    const maxY = Math.max(...nodes.map((node) => node.y + HIERARCHY_NODE_HEIGHT))
    let zoom = Math.max(HIERARCHY_MIN_ZOOM, Math.min((width - 64) / (maxX - minX), (canvas.clientHeight - 64) / (maxY - minY), 1))
    if (readable && zoom < 0.75) {
      zoom = 0.85
      void flowRef.current.setViewport({ x: 32 - minX * zoom, y: 32 - minY * zoom, zoom })
    } else void flowRef.current.setViewport({ x: (width - (maxX - minX) * zoom) / 2 - minX * zoom, y: (canvas.clientHeight - (maxY - minY) * zoom) / 2 - minY * zoom, zoom })
  }, [])
  const locateSelected = useCallback(() => {
    const canvas = canvasRef.current, state = stateRef.current
    const node = state.selectedId ? state.layout?.nodes.get(state.selectedId) : null
    if (!canvas || !node) return
    const zoom = flowRef.current.getZoom()
    void flowRef.current.setViewport({ x: canvas.clientWidth / 2 - (node.x + RELATIONS_NODE_WIDTH / 2) * zoom, y: canvas.clientHeight / 2 - (node.y + HIERARCHY_NODE_HEIGHT / 2) * zoom, zoom }, { duration: 180 })
  }, [])
  useImperativeHandle(handleRef, () => ({ fitView: () => fitView(), locateSelected }), [fitView, locateSelected])
  useEffect(() => {
    const previous = previousLayout.current
    previousLayout.current = layout
    const before = anchorId ? previous?.nodes.get(anchorId) : null
    const after = anchorId ? layout?.nodes.get(anchorId) : null
    if (before && after) {
      const viewport = flowRef.current.getViewport()
      void flowRef.current.setViewport({ ...viewport, x: viewport.x + (before.x - after.x) * viewport.zoom, y: viewport.y + (before.y - after.y) * viewport.zoom })
      return
    }
    const timer = window.setTimeout(() => fitView(true), 50)
    return () => window.clearTimeout(timer)
  }, [layout, anchorId, fitView])
  useEffect(() => {
    if (!selectedId) return
    const timer = window.setTimeout(locateSelected, 70)
    return () => window.clearTimeout(timer)
  }, [selectedId, locateSelected])
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      if (stateRef.current.selectedId) locateSelected()
      else fitView(true)
    })
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [fitView, locateSelected])
  return { canvasRef, fitView }
}
