import type { BugAction } from '../types'

/** 与后端 core/enums.py 的取值逐字对应。 */
export const BUG_STATUS_LABELS: Record<string, string> = {
  pending: '待确定',
  processing: '处理中',
  pending_regression: '待回归',
  closed: '已关闭',
  rejected: '已拒绝',
  reopened: '重新打开',
}

export const BUG_STATUS_TONES: Record<string, string> = {
  pending: 'amber',
  processing: 'blue',
  pending_regression: 'teal',
  closed: 'green',
  rejected: 'slate',
  reopened: 'red',
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

/** 流转按钮文案，与文档 5.2 的状态操作按钮一致。 */
export const BUG_ACTION_LABELS: Record<BugAction, string> = {
  confirm: '确定',
  reject: '拒绝',
  submit_fix: '提交修复',
  regression_pass: '回归通过',
  regression_fail: '回归失败',
  reopen: '重新打开',
}

/** 动态流里的动作说明文案。 */
export const BUG_ACTIVITY_ACTION_LABELS: Record<string, string> = {
  create: '提交了 Bug',
  confirm: '确定处理',
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

/** 各状态允许的流转操作，与后端 TRANSITIONS 表一致。 */
export const BUG_STATUS_ACTIONS: Record<string, BugAction[]> = {
  pending: ['confirm', 'reject'],
  processing: ['submit_fix', 'reject'],
  pending_regression: ['regression_pass', 'regression_fail'],
  closed: ['reopen'],
  rejected: ['reopen'],
  reopened: ['confirm', 'reject'],
}

/** 每个动作的说明填写要求：label + 是否必填。 */
export const BUG_ACTION_CONTENT: Partial<Record<BugAction, { label: string; required: boolean }>> = {
  submit_fix: { label: '修复说明', required: true },
  regression_pass: { label: '回归结果', required: true },
  regression_fail: { label: '失败说明', required: true },
  reopen: { label: '重开原因', required: true },
}

export const BUG_REJECT_REASON_LABELS: Record<string, string> = {
  by_design: '设计如此',
  not_reproducible: '无法复现',
  deferred: '遗留',
}

export function getBugStatusLabel(status: string): string {
  return BUG_STATUS_LABELS[status] ?? status
}

export function getBugStatusTone(status: string): string {
  return BUG_STATUS_TONES[status] ?? 'slate'
}

export function getBugSeverityLabel(severity: string): string {
  return BUG_SEVERITY_LABELS[severity] ?? severity
}

export function getBugPriorityLabel(priority: string): string {
  return BUG_PRIORITY_LABELS[priority] ?? priority
}

export function getBugPriorityTone(priority: string): string {
  return BUG_PRIORITY_TONES[priority] ?? 'slate'
}

export function formatBugNo(bugNo: number): string {
  return `BUG-${bugNo}`
}

export function getBugActionLabel(action: BugAction, status: string): string {
  return action === 'confirm' && status === 'reopened' ? '确定处理' : BUG_ACTION_LABELS[action]
}
