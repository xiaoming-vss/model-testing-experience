/** Shared run status vocabulary; backend values come from control-plane core/enums.py. */
export const RUN_ACTIVE_STATUSES = ['pending', 'queued', 'claimed', 'running', 'waiting_review'] as const
/** Worker still owns the run; deletion is rejected while any of these is set. */
export const RUN_WORKER_STATUSES = ['pending', 'queued', 'claimed', 'running'] as const
export const RUN_STOPPABLE_STATUSES = ['pending', 'queued', 'claimed', 'running'] as const

export type RunStatusMeta = {
  label: string
  color: string
  tone: 'processing' | 'success' | 'error' | 'muted'
}

const RUN_STATUS_META: Record<string, RunStatusMeta> = {
  draft: { label: '草稿', color: 'default', tone: 'muted' },
  pending: { label: '待执行', color: 'gold', tone: 'processing' },
  queued: { label: '排队中', color: 'gold', tone: 'processing' },
  claimed: { label: '已领取', color: 'cyan', tone: 'processing' },
  running: { label: '执行中', color: 'cyan', tone: 'processing' },
  stopping: { label: '停止中', color: 'cyan', tone: 'processing' },
  waiting_review: { label: '待审核', color: 'gold', tone: 'processing' },
  success: { label: '成功', color: 'success', tone: 'success' },
  failed: { label: '失败', color: 'error', tone: 'error' },
  error: { label: '异常', color: 'volcano', tone: 'error' },
  canceled: { label: '已取消', color: 'default', tone: 'muted' },
  skipped: { label: '已跳过', color: 'default', tone: 'muted' },
}

export function normalizeRunStatus(status?: string) {
  return (status ?? '').toLowerCase() || 'unknown'
}

export function runStatusMeta(status?: string): RunStatusMeta & { value: string } {
  const value = normalizeRunStatus(status)
  return { ...(RUN_STATUS_META[value] ?? { label: value, color: 'default', tone: 'muted' }), value }
}

export function isRunInProgress(status?: string) {
  return (RUN_ACTIVE_STATUSES as readonly string[]).includes(normalizeRunStatus(status))
}

export function isRunWorkerActive(status?: string) {
  return (RUN_WORKER_STATUSES as readonly string[]).includes(normalizeRunStatus(status))
}

export function isRunStoppable(status?: string) {
  return (RUN_STOPPABLE_STATUSES as readonly string[]).includes(normalizeRunStatus(status))
}
