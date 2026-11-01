import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'

type Scope = 'project' | 'sprint'
type PendingTransition = { scope: Scope; target: string; direction: number }

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
      [{ opacity: 0, transform: `translateY(${change.direction > 0 ? 22 : -22}px)` }, { opacity: 1, transform: 'translateY(0)' }],
      { duration: 340, easing: 'cubic-bezier(.22, 1, .36, 1)' },
    )
    animation.id = 'app-page-transition'
    running.current = animation
  }, [contentRef, projectId, sprintId])

  function prepare(scope: Scope, current: string | undefined, target: string, orderedValues: string[]) {
    const previousIndex = orderedValues.indexOf(current ?? (scope === 'sprint' ? 'all' : ''))
    const nextIndex = orderedValues.indexOf(target)
    pending.current = previousIndex < 0 || nextIndex < 0 || previousIndex === nextIndex
      ? null : { scope, target, direction: nextIndex - previousIndex }
  }

  return prepare
}
