import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'
import { APP_MOTION } from '@/shared/ui/motion'

type Scope = 'project' | 'sprint'
type PendingTransition = { scope: Scope; target: string }

/** Animate only explicit changes in the project/sprint selectors. */
export function useScopeTransition(contentRef: RefObject<HTMLElement | null>, projectId: string | undefined, sprintId: string | undefined) {
  const pending = useRef<PendingTransition | null>(null)
  const running = useRef<Animation | null>(null)
  useEffect(() => () => { running.current?.cancel() }, [])

  useLayoutEffect(() => {
    const change = pending.current
    if (!change) return
    const current = change.scope === 'project' ? projectId : sprintId ?? 'all'
    if (current !== change.target) return
    pending.current = null
    const element = contentRef.current
    if (!element || typeof element.animate !== 'function' || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    running.current?.cancel()
    element.getAnimations?.().filter(animation => animation.id === 'app-page-transition').forEach(animation => animation.cancel())
    const animation = element.animate(
      [{ opacity: 0, transform: `translateY(${APP_MOTION.offset}px)` }, { opacity: 1, transform: 'translateY(0)' }],
      { duration: APP_MOTION.duration, easing: APP_MOTION.easing },
    )
    animation.id = 'app-page-transition'
    running.current = animation
  }, [contentRef, projectId, sprintId])

  function prepare(scope: Scope, current: string | undefined, target: string, validValues: string[]) {
    const currentValue = current ?? (scope === 'sprint' ? 'all' : '')
    const isValid = validValues.includes(currentValue) && validValues.includes(target)
    pending.current = isValid && currentValue !== target ? { scope, target } : null
  }

  return prepare
}
