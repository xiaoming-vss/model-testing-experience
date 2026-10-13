import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useLocalDate } from './useLocalDate'

afterEach(() => { cleanup(); vi.useRealTimers() })
it('午夜后切换统计日期，休眠标签恢复焦点时同步日期', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 9, 13, 23, 59, 59))
  const { result } = renderHook(useLocalDate)
  expect(result.current).toBe('2026-10-13')
  act(() => vi.advanceTimersByTime(1100))
  expect(result.current).toBe('2026-10-14')
  vi.setSystemTime(new Date(2026, 9, 16, 9))
  act(() => window.dispatchEvent(new Event('focus')))
  expect(result.current).toBe('2026-10-16')
})
