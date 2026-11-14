import { useLayoutEffect, useRef } from 'react'
import { animateTabPanel } from './tabMotion'

/** For view switches implemented as segmented controls instead of ARIA tabs. */
export function useViewMotion(index: number) {
  const panelRef = useRef<HTMLDivElement>(null)
  const previousIndex = useRef(index)
  useLayoutEffect(() => {
    const previous = previousIndex.current
    previousIndex.current = index
    if (previous >= 0 && index >= 0 && previous !== index && panelRef.current) animateTabPanel(panelRef.current)
  }, [index])
  return panelRef
}
