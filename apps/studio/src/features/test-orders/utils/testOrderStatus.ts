type StatusMeta = {
  label: string
  color: string
}

const ORDER_STATUS: Record<string, StatusMeta> = {
  pending: { label: '未开始', color: 'default' },
  in_progress: { label: '执行中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
}

const ENTRY_STATUS: Record<string, StatusMeta> = {
  pending: { label: '未执行', color: 'default' },
  passed: { label: '通过', color: 'success' },
  failed: { label: '失败', color: 'error' },
  blocked: { label: '阻塞', color: 'warning' },
  skipped: { label: '跳过', color: 'default' },
}

export function getTestOrderStatusMeta(status?: string): StatusMeta {
  return ORDER_STATUS[status ?? ''] ?? { label: status || '-', color: 'default' }
}

export function getTestOrderEntryStatusMeta(status?: string): StatusMeta {
  return ENTRY_STATUS[status ?? ''] ?? { label: status || '-', color: 'default' }
}

/** 条目进度文案：已执行 N/M · 通过 x · 失败 y · 阻塞 z · 跳过 w。 */
export function formatEntryProgress(order: {
  entriesTotal?: number
  entriesExecuted?: number
  entriesPassed?: number
  entriesFailed?: number
  entriesBlocked?: number
  entriesSkipped?: number
}) {
  const total = order.entriesTotal ?? 0
  const executed = order.entriesExecuted ?? 0
  const parts = [`已执行 ${executed}/${total}`]
  ;(['entriesPassed', 'entriesFailed', 'entriesBlocked', 'entriesSkipped'] as const).forEach(
    (key, index) => {
      const value = order[key] ?? 0
      if (!value) return
      parts.push(`${['通过', '失败', '阻塞', '跳过'][index]} ${value}`)
    },
  )
  return parts.join(' · ')
}

/** 测试单状态的色调：未开始灰 / 执行中蓝 / 已完成绿。 */
const ORDER_STATUS_TONES: Record<string, string> = {
  pending: 'slate',
  in_progress: 'blue',
  completed: 'green',
}

/** 执行条目结论的色调，与进度条分段（--srf-result-*）同一组语义。 */
const ENTRY_STATUS_TONES: Record<string, string> = {
  pending: 'slate',
  passed: 'green',
  failed: 'red',
  blocked: 'amber',
  skipped: 'slate',
}

/** 共享色盘里的色调名，供列表页与执行工作台给胶囊 / 按钮上色。 */
export function getTestOrderStatusTone(status?: string) {
  return ORDER_STATUS_TONES[status ?? ''] ?? 'slate'
}

export function getTestOrderEntryStatusTone(status?: string) {
  return ENTRY_STATUS_TONES[status ?? ''] ?? 'slate'
}
