import { useLayoutEffect, useRef } from 'react'

export function useNavigationTransition(index: number | null) {
  const contentRef = useRef<HTMLElement>(null)
  const previous = useRef<number | null>(null)

  useLayoutEffect(() => {
    const prior = previous.current
    previous.current = index
    const element = contentRef.current
    if (prior === null || index === null || prior === index || !element || typeof element.animate !== 'function'
      || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return

    const fromX = index > prior ? 22 : -22
    element.getAnimations?.().filter(animation => animation.id === 'app-page-transition').forEach(animation => animation.cancel())
    const animation = element.animate(
      [{ opacity: 0, transform: `translateX(${fromX}px)` }, { opacity: 1, transform: 'translateX(0)' }],
      { duration: 340, easing: 'cubic-bezier(.22, 1, .36, 1)' },
    )
    animation.id = 'app-page-transition'
    return () => animation.cancel()
  }, [index])

  return contentRef
}
