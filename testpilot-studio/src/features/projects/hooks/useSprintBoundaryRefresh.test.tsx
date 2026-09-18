import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getNextSprintBoundary, useSprintBoundaryRefresh } from './useSprintBoundaryRefresh'

const sprint = {
  name: '边界刷新迭代',
  status: 'planned' as const,
  startTime: '2026-09-04T01:00:01.000Z',
  endTime: '2026-09-11T10:00:00.000Z',
}

afterEach(() => {
  vi.useRealTimers()
})

describe('迭代状态边界刷新', () => {
  it('选择所有迭代中最近的未来时间边界', () => {
    expect(getNextSprintBoundary([sprint], Date.parse('2026-09-04T01:00:00.000Z')))
      .toBe(Date.parse(sprint.startTime))
  })

  it('到达时间边界和窗口重新获得焦点时刷新后端数据', () => {
    vi.useFakeTimers()
    vi.setSystemTime('2026-09-04T01:00:00.000Z')
    const refresh = vi.fn()

    const { unmount } = renderHook(() => useSprintBoundaryRefresh({ sprints: [sprint], enabled: true, refresh }))

    act(() => {
      vi.advanceTimersByTime(1_000)
    })
    expect(refresh).toHaveBeenCalledTimes(1)

    act(() => {
      window.dispatchEvent(new Event('focus'))
    })
    expect(refresh).toHaveBeenCalledTimes(2)

    unmount()
    act(() => {
      window.dispatchEvent(new Event('focus'))
    })
    expect(refresh).toHaveBeenCalledTimes(2)
  })
})
