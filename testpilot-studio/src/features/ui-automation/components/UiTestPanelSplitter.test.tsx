import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getNextEditorTopHeight } from '../utils/uiTestPanelResize'
import { UiTestPanelSplitter } from './UiTestPanelSplitter'

afterEach(cleanup)

describe('UI 测试编辑器分隔条', () => {
  it('允许向下拖动，直到结果区仅保留最小高度', () => {
    expect(getNextEditorTopHeight({
      currentHeight: 382,
      deltaY: 100,
      containerHeight: 520,
      minTopHeight: 220,
      minResultHeight: 48,
      splitterHeight: 18,
    })).toBe(454)
  })

  it('拖动时持续回传纵向位移', () => {
    const onResize = vi.fn()
    render(<UiTestPanelSplitter onResize={onResize} />)
    const splitter = screen.getByRole('separator')

    fireEvent.pointerDown(splitter, { clientY: 100 })
    fireEvent.pointerMove(window, { clientY: 135 })
    fireEvent.pointerMove(window, { clientY: 150 })
    fireEvent.pointerUp(window)

    expect(onResize).toHaveBeenNthCalledWith(1, 35)
    expect(onResize).toHaveBeenNthCalledWith(2, 15)
    expect(splitter).not.toHaveClass('resizing')
  })

  it('可以使用上下方向键调整', () => {
    const onResize = vi.fn()
    render(<UiTestPanelSplitter onResize={onResize} />)
    const splitter = screen.getByRole('separator')

    fireEvent.keyDown(splitter, { key: 'ArrowUp' })
    fireEvent.keyDown(splitter, { key: 'ArrowDown' })

    expect(onResize).toHaveBeenNthCalledWith(1, -24)
    expect(onResize).toHaveBeenNthCalledWith(2, 24)
  })
})
