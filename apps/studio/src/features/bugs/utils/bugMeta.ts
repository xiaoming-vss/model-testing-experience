import type { Bug, BugAction } from '../types'

/** 与后端 core/enums.py 的取值逐字对应。 */
export const BUG_STATUS_LABELS: Record<string, string> = {
  active: '激活', resolved: '已解决', closed: '已关闭',
}
const LEGACY_STATUS_LABELS: Record<string, string> = {
  pending: '待确定', processing: '处理中', pending_regression: '待回归',
  rejected: '已拒绝', reopened: '重新打开',
}
export const BUG_RESOLUTION_LABELS: Record<string, string> = {
  fixed: '已修复', bydesign: '设计如此', duplicate: '重复 Bug', external: '外部原因',
  notrepro: '无法复现', postponed: '延期处理', willnotfix: '不予解决', tostory: '转为需求',
}
export const BUG_STATUS_TONES: Record<string, string> = {
  active: 'blue', resolved: 'teal', closed: 'green',
}

export const BUG_SEVERITY_LABELS: Record<string, string> = {
  fatal: '致命',
  serious: '严重',
  normal: '一般',
  minor: '轻微',
}

export const BUG_PRIORITY_LABELS: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

export const BUG_PRIORITY_TONES: Record<string, string> = {
  high: 'red',
  medium: 'amber',
  low: 'slate',
}

export const BUG_ACTION_LABELS: Record<BugAction, string> = {
  confirm: '确认', resolve: '解决', close: '关闭', activate: '激活',
}

/** 动态流里的动作说明文案。 */
export const BUG_ACTIVITY_ACTION_LABELS: Record<string, string> = {
  zentao_push: '推送到禅道',
  create: '提交了 Bug',
  confirm: '确认 Bug',
  resolve: '解决 Bug',
  close: '关闭 Bug',
  activate: '重新激活',
  reject: '拒绝',
  submit_fix: '提交修复',
  regression_pass: '回归通过',
  regression_fail: '回归失败',
  reopen: '重新打开',
  transfer: '转派',
  edit: '编辑了信息',
  attachment: '补充了附件',
  comment: '评论',
}

/** 确认是独立标志，不能仅按主状态决定可用操作。 */
export function getBugActions(bug: Pick<Bug, 'status' | 'confirmed'>): BugAction[] {
  if (bug.status === 'active') return bug.confirmed ? ['resolve'] : ['confirm', 'resolve']
  if (bug.status === 'resolved') return ['close', 'activate']
  if (bug.status === 'closed') return ['activate']
  return []
}

export const BUG_ACTION_CONTENT: Partial<Record<BugAction, { label: string; required: boolean }>> = {
  resolve: { label: '处理说明', required: true },
  close: { label: '验证与关闭说明', required: true },
  activate: { label: '重新激活原因', required: true },
}

export const BUG_REJECT_REASON_LABELS: Record<string, string> = {
  by_design: '设计如此',
  not_reproducible: '无法复现',
  deferred: '遗留',
}

export function getBugStatusLabel(status: string): string {
  return BUG_STATUS_LABELS[status] ?? LEGACY_STATUS_LABELS[status] ?? status
}

export function getBugStatusTone(status: string): string {
  return BUG_STATUS_TONES[status] ?? 'slate'
}

export function getBugPriorityTone(priority: string): string {
  return BUG_PRIORITY_TONES[priority] ?? 'slate'
}

export function formatBugNo(bugNo: number): string {
  return `BUG-${bugNo}`
}

export function getBugActionLabel(action: BugAction): string {
  return BUG_ACTION_LABELS[action]
}

export function getBugStateLabel(bug: Pick<Bug, 'status' | 'confirmed' | 'resolution'>): string {
  const state = getBugStatusLabel(bug.status)
  if (bug.status === 'active') return `${state} · ${bug.confirmed ? '已确认' : '未确认'}`
  return bug.resolution ? `${state} · ${BUG_RESOLUTION_LABELS[bug.resolution] ?? bug.resolution}` : state
}
