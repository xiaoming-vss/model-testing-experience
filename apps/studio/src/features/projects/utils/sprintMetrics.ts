import type {
  SprintDailyMetricsSnapshot,
  SprintDailyMetricsTestStats,
} from '@/services/api'

function numberValue(...values: Array<number | undefined>) {
  return values.find((value) => typeof value === 'number' && Number.isFinite(value)) ?? 0
}

export function snapshotDate(snapshot?: SprintDailyMetricsSnapshot) {
  return snapshot?.snapshotDate ?? snapshot?.snapshot_date ?? snapshot?.date ?? '-'
}

function pickTestStats(
  snapshot: SprintDailyMetricsSnapshot | undefined,
  keys: Array<keyof SprintDailyMetricsSnapshot>,
): Required<SprintDailyMetricsTestStats> {
  const stats = keys.map((key) => snapshot?.[key]).find((value): value is SprintDailyMetricsTestStats => Boolean(value))
  return {
    total: numberValue(stats?.total),
    executed: numberValue(stats?.executed),
    pending: numberValue(stats?.pending, stats?.unexecuted),
    unexecuted: numberValue(stats?.unexecuted, stats?.pending),
    success: numberValue(stats?.success, stats?.passed),
    failed: numberValue(stats?.failed),
    passed: numberValue(stats?.passed, stats?.success),
  }
}

export function normalizeDailyMetrics(snapshot?: SprintDailyMetricsSnapshot) {
  const functional = pickTestStats(snapshot, ['functional', 'function', 'functionTesting', 'function_testing'])
  const apiStats = pickTestStats(snapshot, ['api'])
  const uiStats = pickTestStats(snapshot, ['ui'])
  const bugStats = snapshot?.bug ?? snapshot?.bugs

  return {
    snapshotDate: snapshotDate(snapshot),
    totalCases: numberValue(
      snapshot?.totalCases,
      snapshot?.total_cases,
      functional.total + apiStats.total + uiStats.total,
    ),
    functional: {
      total: numberValue(snapshot?.functionTotal, snapshot?.function_total, functional.total),
      executed: functional.executed,
      unexecuted: functional.pending,
      success: functional.success,
      failed: functional.failed,
    },
    api: {
      total: numberValue(snapshot?.apiTotal, snapshot?.api_total, apiStats.total),
      executed: apiStats.executed,
      unexecuted: apiStats.pending,
      success: apiStats.success,
      failed: apiStats.failed,
    },
    ui: {
      total: numberValue(snapshot?.uiTotal, snapshot?.ui_total, uiStats.total),
      executed: uiStats.executed,
      unexecuted: uiStats.pending,
      success: uiStats.success,
      failed: uiStats.failed,
    },
    bug: {
      collected: Boolean(snapshot) && snapshot?.bug !== null,
      total: numberValue(snapshot?.bugTotal, snapshot?.bug_total, bugStats?.total),
      resolved: numberValue(snapshot?.bugResolved, snapshot?.bug_resolved, bugStats?.resolved),
      closed: numberValue(snapshot?.bugClosed, snapshot?.bug_closed, bugStats?.closed),
      unresolved: numberValue(snapshot?.bugUnresolved, snapshot?.bug_unresolved, bugStats?.unresolved),
      fatal: numberValue(snapshot?.bugFatal, snapshot?.bug_fatal, bugStats?.fatal),
      severe: numberValue(snapshot?.bugSevere, snapshot?.bug_severe, bugStats?.serious, bugStats?.severe),
      normal: numberValue(snapshot?.bugNormal, snapshot?.bug_normal, bugStats?.normal),
      hint: numberValue(snapshot?.bugHint, snapshot?.bug_hint, bugStats?.suggestion, bugStats?.hint),
    },
  }
}

export type NormalizedDailyMetrics = ReturnType<typeof normalizeDailyMetrics>

export function percentValue(value: number, total: number) {
  if (!total) return 0
  return Math.round((value / total) * 100)
}
