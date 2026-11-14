import { useLayoutEffect, useRef } from 'react'
import { APP_MOTION } from '@/shared/ui/motion'

export function useNavigationTransition(index: number | null, routeKey: string) {
  const contentRef = useRef<HTMLElement>(null)
  const previous = useRef<{ index: number | null; routeKey: string } | null>(null)

  useLayoutEffect(() => {
    const prior = previous.current
    previous.current = { index, routeKey }
    const element = contentRef.current
    if (!prior || index === null || (prior.index === index && prior.routeKey === routeKey)
      || !element || typeof element.animate !== 'function'
      || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return

    element.getAnimations?.().filter(animation => animation.id === 'app-page-transition').forEach(animation => animation.cancel())
    const animation = element.animate(
      [{ opacity: 0, transform: `translateY(${APP_MOTION.offset}px)` }, { opacity: 1, transform: 'translateY(0)' }],
      { duration: APP_MOTION.duration, easing: APP_MOTION.easing },
    )
    animation.id = 'app-page-transition'
    return () => animation.cancel()
  }, [index, routeKey])

  return contentRef
}
