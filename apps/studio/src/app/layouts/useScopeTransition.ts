import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'
import { APP_MOTION } from '@/shared/ui/motion'

/** Animate the content only when the project selector changes explicitly. */
export function useScopeTransition(contentRef: RefObject<HTMLElement | null>, projectId: string | undefined) {
  const pending = useRef<string | null>(null)
  const running = useRef<Animation | null>(null)
  useEffect(() => () => { running.current?.cancel() }, [])

  useLayoutEffect(() => {
    const target = pending.current
    if (target === null || projectId !== target) return
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
  }, [contentRef, projectId])

  function prepare(current: string | undefined, target: string, validValues: string[]) {
    const currentValue = current ?? ''
    const isValid = validValues.includes(currentValue) && validValues.includes(target)
    pending.current = isValid && currentValue !== target ? target : null
  }

  return prepare
}
