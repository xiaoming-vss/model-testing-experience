/** Play the shared directional transition without affecting unrelated animations. */
export function animateTabPanel(panel: HTMLElement, direction: number) {
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || typeof panel.animate !== 'function') return
  panel.getAnimations?.().filter(animation => animation.id === 'shared-tab-motion').forEach(animation => animation.cancel())
  const motion = panel.animate(
    [{ opacity: 0, transform: `translateX(${direction > 0 ? 22 : -22}px)` }, { opacity: 1, transform: 'translateX(0)' }],
    { duration: 340, easing: 'cubic-bezier(.22, 1, .36, 1)' },
  )
  motion.id = 'shared-tab-motion'
}

type TabState = { indicator: HTMLSpanElement; host: HTMLElement; selected: HTMLElement | null; index: number }

/** Enhance actual ARIA tablists, including those rendered in portal-based dialogs. */
export function installTabMotion(root: HTMLElement) {
  const states = new Map<HTMLElement, TabState>()
  let frame = 0
  let disposed = false
  let resizeObserver: ResizeObserver | null = null

  function selectedTabs(list: HTMLElement) {
    return Array.from(list.querySelectorAll<HTMLElement>('[role="tab"]'))
      .filter(tab => tab.closest('[role="tablist"]') === list)
  }

  function update(list: HTMLElement, animate: boolean) {
    if (!list.isConnected) return
    let state = states.get(list)
    if (!state) {
      const indicator = document.createElement('span')
      indicator.className = 'shared-tab-motion-indicator'
      indicator.setAttribute('aria-hidden', 'true')
      const host = list.querySelector<HTMLElement>('.ant-tabs-nav-list') ?? list
      state = { indicator, host, selected: null, index: -1 }
      states.set(list, state)
      list.classList.add('has-shared-tab-motion')
      host.append(indicator)
    }
    const currentHost = list.querySelector<HTMLElement>('.ant-tabs-nav-list') ?? list
    if (state.host !== currentHost) {
      state.host = currentHost
      state.indicator.style.opacity = '0'
    }
    if (!state.host.contains(state.indicator)) state.host.append(state.indicator)
    const tabs = selectedTabs(list)
    const selected = tabs.find(tab => tab.getAttribute('aria-selected') === 'true') ?? null
    const index = selected ? tabs.indexOf(selected) : -1
    const changed = state.selected !== selected && state.index !== index && state.index >= 0 && index >= 0
    const previousIndex = state.index
    if (state.selected && state.selected !== selected) resizeObserver?.unobserve(state.selected.closest<HTMLElement>('.ant-tabs-tab') ?? state.selected)
    state.selected = selected
    state.index = index
    if (!selected) { state.indicator.style.opacity = '0'; return }

    const target = selected.closest<HTMLElement>('.ant-tabs-tab') ?? selected
    resizeObserver?.observe(list)
    resizeObserver?.observe(target)
    const bounds = target.getBoundingClientRect()
    const hostBounds = state.host.getBoundingClientRect()
    const indicator = state.indicator
    const initial = indicator.style.opacity !== '1'
    if (initial || !animate) indicator.style.transition = 'none'
    indicator.style.width = `${bounds.width}px`
    indicator.style.height = `${bounds.height}px`
    indicator.style.transform = `translate(${bounds.left - hostBounds.left + state.host.scrollLeft}px, ${bounds.top - hostBounds.top + state.host.scrollTop}px)`
    indicator.style.opacity = '1'
    if (initial || !animate) { void indicator.offsetWidth; indicator.style.removeProperty('transition') }

    if (!changed || !animate) return
    const usesScope = list.hasAttribute('data-tab-motion-scoped')
    const scoped = usesScope ? list.closest<HTMLElement>('[data-tab-motion-scope]')?.querySelector<HTMLElement>('[data-tab-motion-panel]') : null
    const panelId = selected.getAttribute('aria-controls')
    const panel = scoped ?? (panelId ? document.getElementById(panelId) : null)
    if (panel) animateTabPanel(panel, index - previousIndex)
  }

  function scan(node: ParentNode) {
    if (node instanceof HTMLElement && node.matches('[role="tablist"]')) update(node, false)
    node.querySelectorAll<HTMLElement>('[role="tablist"]').forEach(list => update(list, false))
  }
  scan(root)
  const observer = new MutationObserver(records => {
    const changed = new Set<HTMLElement>()
    for (const record of records) {
      const owner = record.target instanceof Element ? record.target.closest<HTMLElement>('[role="tablist"]') : null
      if (owner) changed.add(owner)
      record.addedNodes.forEach(node => { if (node instanceof HTMLElement && !node.classList.contains('shared-tab-motion-indicator')) scan(node) })
    }
    changed.forEach(list => update(list, true))
    for (const [list, state] of states) if (!list.isConnected) {
      resizeObserver?.unobserve(list)
      if (state.selected) resizeObserver?.unobserve(state.selected.closest<HTMLElement>('.ant-tabs-tab') ?? state.selected)
      state.indicator.remove()
      states.delete(list)
    }
  })
  observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['aria-selected'] })
  const resize = () => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => { if (!disposed) states.forEach((_, list) => update(list, false)) })
  }
  window.addEventListener('resize', resize)
  resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
  resizeObserver?.observe(root)
  states.forEach((_, list) => update(list, false))
  return () => {
    disposed = true
    observer.disconnect()
    resizeObserver?.disconnect()
    window.removeEventListener('resize', resize)
    cancelAnimationFrame(frame)
    states.forEach((state, list) => { state.indicator.remove(); list.classList.remove('has-shared-tab-motion') })
  }
}
