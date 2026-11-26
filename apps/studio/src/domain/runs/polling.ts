import { isRunInProgress, normalizeRunStatus } from './status'

/** Run details own progress polling; expanded histories only discover changes. */
export const RUN_HISTORY_POLL_INTERVAL = 30_000
export const PERF_RUN_POLL_INTERVAL = 3_000
/** Candidate workspaces poll their current/live list while a stage is active. */
export const CANDIDATE_ACTIVE_POLL_INTERVAL = 5_000
export const CANDIDATE_IDLE_POLL_INTERVAL = 15_000

export function getRunPollingInterval(status?: string): number | false {
  if (!status) return 5_000
  const normalized = normalizeRunStatus(status)
  if (normalized === 'running' || normalized === 'stopping') return 5_000
  if (isRunInProgress(normalized)) return 15_000
  return false
}

/** Slow recovery checks only while the live connection is unavailable. */
export function getRunEventFallbackInterval(status?: string): number | false {
  return getRunPollingInterval(status) === false ? false : 30_000
}
