import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { APP_MOTION } from '@/shared/ui/motion'
import { useScopeTransition } from './useScopeTransition'

function TestScope({ project = 'p1', sprint = 's1' }: { project?: string; sprint?: string }) {
  const ref = useRef<HTMLElement>(null)
  const prepare = useScopeTransition(ref, project, sprint)
  return <><button onClick={() => prepare('sprint', sprint, 's2', ['all', 's1', 's2'])}>选择下方迭代</button>
    <button onClick={() => prepare('project', project, 'p1', ['p1', 'p2'])}>选择上方项目</button><main ref={ref}>内容</main></>
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const expectedFrames = [
  { opacity: 0, transform: `translateY(${APP_MOTION.offset}px)` },
  { opacity: 1, transform: 'translateY(0)' },
]
const expectedOptions = { duration: APP_MOTION.duration, easing: APP_MOTION.easing }

describe('scope selection transition', () => {
  it('animates only explicit selections', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    const animate = vi.fn(() => ({ id: '', cancel: vi.fn() }))
    const view = render(<TestScope />)
    Object.defineProperty(view.container.querySelector('main'), 'animate', { value: animate })
    view.rerender(<TestScope project="p2" />)
    expect(animate).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '选择下方迭代' }))
    view.rerender(<TestScope project="p2" sprint="s2" />)
    expect(animate).toHaveBeenLastCalledWith(expectedFrames, expectedOptions)
    fireEvent.click(screen.getByRole('button', { name: '选择上方项目' }))
    view.rerender(<TestScope project="p1" sprint="s2" />)
    expect(animate).toHaveBeenLastCalledWith(expectedFrames, expectedOptions)
  })

  it('keeps the project transition running when its sprint updates automatically', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    const cancel = vi.fn()
    const animate = vi.fn(() => ({ id: '', cancel }))
    const view = render(<TestScope project="p2" />)
    Object.defineProperty(view.container.querySelector('main'), 'animate', { value: animate })
    fireEvent.click(screen.getByRole('button', { name: '选择上方项目' }))
    view.rerender(<TestScope project="p1" />)
    expect(animate).toHaveBeenCalledTimes(1)
    view.rerender(<TestScope project="p1" sprint="s2" />)
    expect(cancel).not.toHaveBeenCalled()
    expect(animate).toHaveBeenCalledTimes(1)
  })

  it('respects the reduced motion preference', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const animate = vi.fn()
    const view = render(<TestScope />)
    Object.defineProperty(view.container.querySelector('main'), 'animate', { value: animate })
    fireEvent.click(screen.getByRole('button', { name: '选择下方迭代' }))
    view.rerender(<TestScope sprint="s2" />)
    expect(animate).not.toHaveBeenCalled()
  })
})
