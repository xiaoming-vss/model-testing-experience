import { useEffect } from 'react'
import type { Sprint } from '@/features/projects/types'
import { pickEndTime, pickStartTime } from '@/utils/format'

const MAX_TIMEOUT_MS = 2_147_483_647

export function getNextSprintBoundary(sprints: Sprint[], now = Date.now()) {
  let nextBoundary: number | undefined

  for (const sprint of sprints) {
    for (const value of [pickStartTime(sprint), pickEndTime(sprint)]) {
      if (!value) continue
      const timestamp = new Date(value).getTime()
      if (Number.isNaN(timestamp) || timestamp <= now) continue
      if (nextBoundary === undefined || timestamp < nextBoundary) nextBoundary = timestamp
    }
  }

  return nextBoundary
}

export function useSprintBoundaryRefresh({
  sprints,
  enabled,
  refresh,
}: {
  sprints: Sprint[]
  enabled: boolean
  refresh: () => unknown
}) {
  useEffect(() => {
    if (!enabled) return

    let timeoutId: ReturnType<typeof setTimeout> | undefined
    let disposed = false

    const scheduleBoundaryRefresh = () => {
      if (disposed) return
      const now = Date.now()
      const nextBoundary = getNextSprintBoundary(sprints, now)
      if (nextBoundary === undefined) return

      const remaining = nextBoundary - now
      if (remaining > MAX_TIMEOUT_MS) {
        timeoutId = setTimeout(scheduleBoundaryRefresh, MAX_TIMEOUT_MS)
        return
      }

      timeoutId = setTimeout(() => {
        if (!disposed) void refresh()
      }, remaining)
    }

    const refreshOnFocus = () => {
      void refresh()
    }

    scheduleBoundaryRefresh()
    window.addEventListener('focus', refreshOnFocus)

    return () => {
      disposed = true
      if (timeoutId !== undefined) clearTimeout(timeoutId)
      window.removeEventListener('focus', refreshOnFocus)
    }
  }, [enabled, refresh, sprints])
}
