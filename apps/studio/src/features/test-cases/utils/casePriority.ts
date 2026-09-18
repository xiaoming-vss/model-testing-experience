export function priorityColor(priority?: string) {
  const colorMap: Record<string, string> = {
    P0: 'red',
    P1: 'orange',
    P2: 'blue',
    P3: 'default',
  }
  return priority ? colorMap[priority] ?? 'default' : 'default'
}
