import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { APP_MOTION } from '@/shared/ui/motion'
import { navigationIndex } from './navigation'
import { useNavigationTransition } from './useNavigationTransition'

function TestContent({ index, routeKey }: { index: number | null; routeKey: string }) {
  const ref = useNavigationTransition(index, routeKey)
  return <main ref={ref}>内容</main>
}

const expectedFrames = [
  { opacity: 0, transform: `translateY(${APP_MOTION.offset}px)` },
  { opacity: 1, transform: 'translateY(0)' },
]
const expectedOptions = { duration: APP_MOTION.duration, easing: APP_MOTION.easing }

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('top navigation page transition', () => {
  it('animates navigation changes and leaves same-route updates alone', () => {
    const cancel = vi.fn()
    const animate = vi.fn(() => ({ cancel }))
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    const view = render(<TestContent index={0} routeKey="/testing" />)
    Object.defineProperty(view.container.querySelector('main'), 'animate', { value: animate })

    view.rerender(<TestContent index={1} routeKey="/testing" />)
    expect(animate).toHaveBeenLastCalledWith(expectedFrames, expectedOptions)

    view.rerender(<TestContent index={1} routeKey="/testing" />)
    expect(animate).toHaveBeenCalledTimes(1)

    view.rerender(<TestContent index={0} routeKey="/testing" />)
    expect(cancel).toHaveBeenCalled()
    expect(animate).toHaveBeenLastCalledWith(expectedFrames, expectedOptions)
  })

  it('animates detail-route changes inside the same navigation section', () => {
    const animate = vi.fn(() => ({ cancel: vi.fn() }))
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    const view = render(<TestContent index={3} routeKey="/asset-library/interfaces/one" />)
    Object.defineProperty(view.container.querySelector('main'), 'animate', { value: animate })

    view.rerender(<TestContent index={3} routeKey="/asset-library/interfaces/two" />)
    expect(animate).toHaveBeenLastCalledWith(expectedFrames, expectedOptions)
  })

  it('honors reduced motion', () => {
    const animate = vi.fn()
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const view = render(<TestContent index={0} routeKey="/testing" />)
    Object.defineProperty(view.container.querySelector('main'), 'animate', { value: animate })
    view.rerender(<TestContent index={1} routeKey="/testing" />)
    expect(animate).not.toHaveBeenCalled()
  })

  it('maps related pages to their visible navigation item', () => {
    expect(navigationIndex('/projects', '?board=requirements', false)).toBe(1)
    expect(navigationIndex('/requirements/123', '', false)).toBe(1)
    expect(navigationIndex('/testing', '?tab=api', false)).toBe(2)
    expect(navigationIndex('/asset-library', '?tab=interfaces', false)).toBe(3)
    expect(navigationIndex('/bugs/123', '', false)).toBe(4)
    expect(navigationIndex('/profile', '', false)).toBeNull()
  })
})
