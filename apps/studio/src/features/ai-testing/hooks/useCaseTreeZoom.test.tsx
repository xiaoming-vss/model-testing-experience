import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useCaseTreeZoom } from './useCaseTreeZoom'

function Tree({ enabled = true }) {
  const { zoom, viewportRef } = useCaseTreeZoom(enabled)
  return <><div ref={viewportRef} data-testid="tree"><div style={{ zoom }}>{zoom}</div></div><aside data-testid="details" /></>
}

afterEach(cleanup)

describe('useCaseTreeZoom', () => {
  it('uses Ctrl + wheel to zoom around the pointer and clamps the scale', () => {
    render(<Tree />)
    const tree = screen.getByTestId('tree')
    tree.scrollLeft = 200
    tree.scrollTop = 400
    fireEvent.wheel(tree, { ctrlKey: true, deltaY: -100, clientX: 100, clientY: 150 })
    const scale = Number(tree.textContent)
    expect(scale).toBeGreaterThan(1)
    expect(tree.scrollLeft).toBeCloseTo(300 * scale - 100)
    expect(tree.scrollTop).toBeCloseTo(550 * scale - 150)
    fireEvent.wheel(tree, { ctrlKey: true, deltaY: -10000 })
    expect(tree.textContent).toBe('1.5')
    fireEvent.wheel(tree, { ctrlKey: true, deltaY: 10000 })
    expect(tree.textContent).toBe('0.5')
  })

  it('leaves ordinary wheel scrolling to the browser', () => {
    render(<Tree />)
    const tree = screen.getByTestId('tree')
    const wheel = new WheelEvent('wheel', { deltaY: 100, cancelable: true })
    act(() => tree.dispatchEvent(wheel))
    expect(wheel.defaultPrevented).toBe(false)
    expect(tree.textContent).toBe('1')
  })

  it('leaves details and disabled trees scrolling normally', () => {
    const { rerender } = render(<Tree />)
    const wheel = new WheelEvent('wheel', { ctrlKey: true, deltaY: -100, cancelable: true })
    act(() => screen.getByTestId('tree').dispatchEvent(wheel))
    expect(wheel.defaultPrevented).toBe(true)
    const scale = screen.getByTestId('tree').textContent
    fireEvent.wheel(screen.getByTestId('details'), { ctrlKey: true, deltaY: -100 })
    expect(screen.getByTestId('tree').textContent).toBe(scale)
    rerender(<Tree enabled={false} />)
    const disabledWheel = new WheelEvent('wheel', { ctrlKey: true, deltaY: -100, cancelable: true })
    act(() => screen.getByTestId('tree').dispatchEvent(disabledWheel))
    expect(disabledWheel.defaultPrevented).toBe(false)
    expect(screen.getByTestId('tree').textContent).toBe(scale)
  })
})
