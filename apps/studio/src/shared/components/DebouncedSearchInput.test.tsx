import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { DebouncedSearchInput } from './DebouncedSearchInput'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

it('does not commit the initial empty value and debounces typed input', () => {
  vi.useFakeTimers()
  const onCommit = vi.fn()
  render(<DebouncedSearchInput ariaLabel="搜索用例" placeholder="搜索" className="test-search" onCommit={onCommit} />)

  act(() => vi.advanceTimersByTime(400))
  expect(onCommit).not.toHaveBeenCalled()

  fireEvent.change(screen.getByLabelText('搜索用例'), { target: { value: '登录' } })
  act(() => vi.advanceTimersByTime(400))
  expect(onCommit).toHaveBeenCalledWith('登录')
})
