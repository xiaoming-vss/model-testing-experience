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

const ENTRY_STATUS_DOT: Record<string, string> = {
  pending: 'rgba(84, 104, 132, 0.22)',
  passed: '#52c41a',
  failed: '#ff4d4f',
  blocked: '#faad14',
  skipped: '#bfbfbf',
}

/** 紧凑条目行首的状态圆点颜色。 */
export function getTestOrderEntryDotColor(status?: string) {
  return ENTRY_STATUS_DOT[status ?? ''] ?? ENTRY_STATUS_DOT.pending
}
