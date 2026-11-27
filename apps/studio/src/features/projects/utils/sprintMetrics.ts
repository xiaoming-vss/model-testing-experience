import type {
  SprintDailyMetricsSnapshot,
  SprintDailyMetricsTestStats,
} from '@/services/api'

export function snapshotDate(snapshot?: SprintDailyMetricsSnapshot) {
  return snapshot?.snapshotDate ?? '-'
}

function testStats(stats?: SprintDailyMetricsTestStats) {
  return {
    total: stats?.total ?? 0,
    executed: stats?.executed ?? 0,
    unexecuted: stats?.pending ?? 0,
    success: stats?.success ?? 0,
    failed: stats?.failed ?? 0,
  }
}

export function normalizeDailyMetrics(snapshot?: SprintDailyMetricsSnapshot) {
  const functional = testStats(snapshot?.function)
  const apiStats = testStats(snapshot?.api)
  const uiStats = testStats(snapshot?.ui)
  const bugStats = snapshot?.bug

  return {
    snapshotDate: snapshotDate(snapshot),
    totalCases: functional.total + apiStats.total + uiStats.total,
    functional,
    api: apiStats,
    ui: uiStats,
    bug: {
      collected: Boolean(snapshot) && snapshot?.bug !== null,
      total: bugStats?.total ?? 0,
      resolved: bugStats?.resolved ?? 0,
      closed: bugStats?.closed ?? 0,
      unresolved: bugStats?.unresolved ?? 0,
      fatal: bugStats?.fatal ?? 0,
      severe: bugStats?.serious ?? 0,
      normal: bugStats?.normal ?? 0,
      hint: bugStats?.suggestion ?? 0,
    },
  }
}

export type NormalizedDailyMetrics = ReturnType<typeof normalizeDailyMetrics>

export function percentValue(value: number, total: number) {
  if (!total) return 0
  return Math.round((value / total) * 100)
}
