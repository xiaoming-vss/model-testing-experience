import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { APP_MOTION } from '@/shared/ui/motion'
import { useScopeTransition } from './useScopeTransition'

function TestScope({ project = 'p1' }: { project?: string }) {
  const ref = useRef<HTMLElement>(null)
  const prepare = useScopeTransition(ref, project)
  return <><button onClick={() => prepare(project, 'p2', ['p1', 'p2'])}>选择上方项目</button><main ref={ref}>内容</main></>
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const expectedFrames = [
  { opacity: 0, transform: `translateY(${APP_MOTION.offset}px)` },
  { opacity: 1, transform: 'translateY(0)' },
]
const expectedOptions = { duration: APP_MOTION.duration, easing: APP_MOTION.easing }

describe('scope selection transition', () => {
  it('animates only explicit project selections', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    const animate = vi.fn(() => ({ id: '', cancel: vi.fn() }))
    const view = render(<TestScope />)
    Object.defineProperty(view.container.querySelector('main'), 'animate', { value: animate })
    view.rerender(<TestScope project="p2" />)
    expect(animate).not.toHaveBeenCalled()
    view.rerender(<TestScope project="p1" />)
    fireEvent.click(screen.getByRole('button', { name: '选择上方项目' }))
    view.rerender(<TestScope project="p2" />)
    expect(animate).toHaveBeenLastCalledWith(expectedFrames, expectedOptions)
  })

  it('respects the reduced motion preference', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const animate = vi.fn()
    const view = render(<TestScope />)
    Object.defineProperty(view.container.querySelector('main'), 'animate', { value: animate })
    fireEvent.click(screen.getByRole('button', { name: '选择上方项目' }))
    view.rerender(<TestScope project="p2" />)
    expect(animate).not.toHaveBeenCalled()
  })
})
