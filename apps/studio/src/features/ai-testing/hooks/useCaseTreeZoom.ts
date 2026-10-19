import { useEffect, useLayoutEffect, useRef, useState } from 'react'

/** Zoom only the tree viewport, keeping the content under the pointer stationary. */
export function useCaseTreeZoom(enabled = true) {
  const [zoom, setZoom] = useState(1)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const scale = useRef(1)
  const anchor = useRef<{ x: number; y: number; contentX: number; contentY: number } | null>(null)

  useEffect(() => {
    const viewport = viewportRef.current
    if (!enabled || !viewport) return
    const onWheel = (event: WheelEvent) => {
      if (!event.deltaY) return
      event.preventDefault()
      const next = Math.max(0.5, Math.min(1.5, scale.current * Math.exp(-event.deltaY * (event.deltaMode === 1 ? 0.03 : 0.002))))
      if (next === scale.current) return
      const rect = viewport.getBoundingClientRect()
      // The viewport padding is outside the scaled canvas.
      const style = getComputedStyle(viewport)
      const x = event.clientX - rect.left - viewport.clientLeft - (parseFloat(style.paddingLeft) || 0)
      const y = event.clientY - rect.top - viewport.clientTop - (parseFloat(style.paddingTop) || 0)
      if (!anchor.current) anchor.current = {
        x, y,
        contentX: (viewport.scrollLeft + x) / scale.current,
        contentY: (viewport.scrollTop + y) / scale.current,
      }
      scale.current = next
      setZoom(next)
    }
    viewport.addEventListener('wheel', onWheel, { passive: false })
    return () => viewport.removeEventListener('wheel', onWheel)
  }, [enabled])

  useLayoutEffect(() => {
    const viewport = viewportRef.current
    const point = anchor.current
    if (!viewport || !point) return
    viewport.scrollLeft = point.contentX * zoom - point.x
    viewport.scrollTop = point.contentY * zoom - point.y
    anchor.current = null
  }, [zoom])

  return { zoom, viewportRef }
}
