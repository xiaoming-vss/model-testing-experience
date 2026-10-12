export function priorityColor(priority?: string) {
  const colorMap: Record<string, string> = {
    P0: 'red',
    P1: 'orange',
    P2: 'blue',
    P3: 'default',
  }
  return priority ? colorMap[priority] ?? 'default' : 'default'
}

/** 显示时兼容历史数字档位，保留未知值，不改写已存储的优先级。 */
export function formatCasePriority(priority?: string | number | null): string {
  const value = String(priority ?? '').trim()
  return /^[pP]?[0-3]$/.test(value) ? `P${value.slice(-1)}` : value || '-'
}
