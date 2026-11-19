export const sprintChartTheme = {
  grid: 'var(--chart-grid)',
  axis: 'var(--chart-axis)',
  tooltipBackground: 'var(--chart-tooltip-bg)',
  tooltipBorder: 'var(--chart-tooltip-border)',
  tooltipText: 'var(--chart-tooltip-text)',
  total: 'var(--chart-total)',
  positive: 'var(--chart-positive)',
  pending: 'var(--chart-pending)',
  success: 'var(--chart-success)',
  negative: 'var(--chart-negative)',
  empty: 'var(--chart-empty)',
} as const

export type SprintChartTheme = typeof sprintChartTheme
