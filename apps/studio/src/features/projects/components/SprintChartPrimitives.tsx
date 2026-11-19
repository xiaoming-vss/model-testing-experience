import { Legend, Tooltip as RechartsTooltip } from 'recharts'
import type { SprintChartTheme } from '../utils/sprintChartTheme'

export function SprintChartTooltip({ chartTheme }: { chartTheme: SprintChartTheme }) {
  return (
    <RechartsTooltip
      contentStyle={{
        backgroundColor: chartTheme.tooltipBackground,
        borderColor: chartTheme.tooltipBorder,
        borderRadius: 8,
        color: chartTheme.tooltipText,
      }}
      labelStyle={{ color: chartTheme.tooltipText, fontWeight: 600 }}
    />
  )
}

export function SprintChartLegend({ chartTheme }: { chartTheme: SprintChartTheme }) {
  return (
    <Legend
      verticalAlign="bottom"
      height={32}
      iconType="circle"
      formatter={(value) => <span style={{ color: chartTheme.axis }}>{value}</span>}
    />
  )
}
