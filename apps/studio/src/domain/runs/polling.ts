/** Run details own progress polling; expanded histories only discover changes. */
export const RUN_HISTORY_POLL_INTERVAL = 30_000

export function getRunPollingInterval(status?: string): number | false {
  if (!status) return 5_000
  if (status === 'running' || status === 'stopping') return 5_000
  if (status === 'pending' || status === 'queued' || status === 'claimed' || status === 'waiting_review') return 15_000
  return false
}

/** Slow recovery checks only while the live connection is unavailable. */
export function getRunEventFallbackInterval(status?: string): number | false {
  return getRunPollingInterval(status) === false ? false : 30_000
}
