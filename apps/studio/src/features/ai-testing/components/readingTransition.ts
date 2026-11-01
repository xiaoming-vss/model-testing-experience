/** Locate the source card in the current canvas viewport, including pan and zoom. */
export function setReadingOrigin(stage: HTMLElement | null, card?: HTMLElement) {
  if (!stage) return
  if (!card) {
    stage.style.removeProperty('--gc-reading-origin-x')
    stage.style.removeProperty('--gc-reading-origin-y')
    return
  }
  const bounds = stage.getBoundingClientRect()
  const source = card.getBoundingClientRect()
  if (!bounds.width || !bounds.height) return
  const clamp = (value: number) => Math.min(100, Math.max(0, value))
  stage.style.setProperty('--gc-reading-origin-x', `${clamp(((source.left + source.width / 2 - bounds.left) / bounds.width) * 100)}%`)
  stage.style.setProperty('--gc-reading-origin-y', `${clamp(((source.top + source.height / 2 - bounds.top) / bounds.height) * 100)}%`)
}

/** Keep the reading area mounted until its return animation finishes. */
export function animateReadingExit(stage: HTMLElement | null, onComplete: () => void): Animation | null {
  const reader = stage?.querySelector<HTMLElement>(':scope > .gc-embedded-artifact')
  if (!reader || typeof reader.animate !== 'function' || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
    onComplete()
    return null
  }
  const animation = reader.animate(
    [{ opacity: 1, transform: 'scale(1)' }, { opacity: 0, transform: 'scale(.93)' }],
    { duration: 260, easing: 'ease-in', fill: 'forwards' },
  )
  animation.onfinish = onComplete
  return animation
}

/** Keep the inspector shell fixed while its contents settle into reading mode. */
export function animateInspectorContents(inspector: HTMLElement | null) {
  if (!inspector || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
  inspector.querySelectorAll<HTMLElement>(':scope > .gc-inspector-header, :scope > .gc-inspector-content, :scope > .gc-inspector-footer').forEach(element => {
    if (typeof element.animate !== 'function') return
    element.getAnimations?.().filter(animation => animation.id === 'gc-inspector-reading-change').forEach(animation => animation.cancel())
    const animation = element.animate(
      [{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'translateY(0)' }],
      { duration: 320, easing: 'cubic-bezier(.22, 1, .36, 1)' },
    )
    animation.id = 'gc-inspector-reading-change'
  })
}
