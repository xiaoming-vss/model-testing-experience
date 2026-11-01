import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { navigationIndex } from './navigation'
import { useNavigationTransition } from './useNavigationTransition'

function TestContent({ index }: { index: number | null }) {
  const ref = useNavigationTransition(index)
  return <main ref={ref}>内容</main>
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('top navigation page transition', () => {
  it('slides in the direction of navigation and leaves same-section updates alone', () => {
    const cancel = vi.fn()
    const animate = vi.fn(() => ({ cancel }))
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    const view = render(<TestContent index={0} />)
    Object.defineProperty(view.container.querySelector('main'), 'animate', { value: animate })
    view.rerender(<TestContent index={1} />)
    expect(animate).toHaveBeenLastCalledWith(
      [{ opacity: 0, transform: 'translateX(22px)' }, { opacity: 1, transform: 'translateX(0)' }],
      { duration: 340, easing: 'cubic-bezier(.22, 1, .36, 1)' },
    )
    view.rerender(<TestContent index={1} />)
    expect(animate).toHaveBeenCalledTimes(1)
    view.rerender(<TestContent index={0} />)
    expect(cancel).toHaveBeenCalled()
    expect(animate).toHaveBeenLastCalledWith(
      [{ opacity: 0, transform: 'translateX(-22px)' }, { opacity: 1, transform: 'translateX(0)' }],
      { duration: 340, easing: 'cubic-bezier(.22, 1, .36, 1)' },
    )
  })

  it('honors reduced motion', () => {
    const animate = vi.fn()
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const view = render(<TestContent index={0} />)
    Object.defineProperty(view.container.querySelector('main'), 'animate', { value: animate })
    view.rerender(<TestContent index={1} />)
    expect(animate).not.toHaveBeenCalled()
  })

  it('maps related pages to their visible navigation item', () => {
    expect(navigationIndex('/projects', '?board=requirements', false)).toBe(1)
    expect(navigationIndex('/requirements/123', '', false)).toBe(1)
    expect(navigationIndex('/testing', '?tab=api', false)).toBe(2)
    expect(navigationIndex('/bugs/123', '', false)).toBe(3)
    expect(navigationIndex('/profile', '', false)).toBeNull()
  })
})
