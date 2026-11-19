import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts'
import dayjs from 'dayjs'
import {
  SprintChartLegend,
  SprintChartTooltip,
} from './SprintChartPrimitives'
import { sprintChartTheme } from '../utils/sprintChartTheme'
import type { NormalizedDailyMetrics } from '../utils/sprintMetrics'

export function TrendLineChart({ data }: { data: NormalizedDailyMetrics[] }) {
  const chartTheme = sprintChartTheme
  const chartData = data.map((item) => ({
    date: dayjs(item.snapshotDate).isValid() ? dayjs(item.snapshotDate).format('MM-DD') : item.snapshotDate,
    total: item.totalCases,
    executed: item.functional.executed + item.api.executed + item.ui.executed,
    pending: item.functional.unexecuted + item.api.unexecuted + item.ui.unexecuted,
    success: item.functional.success + item.api.success + item.ui.success,
    failed: item.functional.failed + item.api.failed + item.ui.failed,
  }))

  return (
    <div className="sprint-overview-chart-host h-[210px] w-full min-h-[210px] min-w-0 flex-auto min-[1281px]:h-auto">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} syncId="sprint-trend-history" margin={{ top: 8, right: 18, left: -12, bottom: 0 }}>
          <CartesianGrid stroke={chartTheme.grid} vertical={false} />
          <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: chartTheme.axis, fontSize: 12 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: chartTheme.axis, fontSize: 12 }} allowDecimals={false} />
          <SprintChartTooltip chartTheme={chartTheme} />
          <SprintChartLegend chartTheme={chartTheme} />
          <Line name="总数" type="monotone" dataKey="total" stroke={chartTheme.total} strokeWidth={2.4} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          <Line name="已执行" type="monotone" dataKey="executed" stroke={chartTheme.positive} strokeWidth={2.2} dot={{ r: 3 }} />
          <Line name="未执行" type="monotone" dataKey="pending" stroke={chartTheme.pending} strokeWidth={2.2} dot={{ r: 3 }} />
          <Line name="成功" type="monotone" dataKey="success" stroke={chartTheme.success} strokeWidth={2.2} dot={{ r: 3 }} />
          <Line name="失败" type="monotone" dataKey="failed" stroke={chartTheme.negative} strokeWidth={2.2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function TrendBarChart({ data }: { data: NormalizedDailyMetrics[] }) {
  const chartTheme = sprintChartTheme
  const chartData = data.map((item) => ({
    date: dayjs(item.snapshotDate).isValid() ? dayjs(item.snapshotDate).format('MM-DD') : item.snapshotDate,
    total: item.bug.collected ? item.bug.total : null,
    resolved: item.bug.collected ? item.bug.resolved : null,
    closed: item.bug.collected ? item.bug.closed : null,
    unresolved: item.bug.collected ? item.bug.unresolved : null,
  }))

  return (
    <div className="sprint-overview-chart-host h-[210px] w-full min-h-[210px] min-w-0 flex-auto min-[1281px]:h-auto">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} syncId="sprint-trend-history" margin={{ top: 8, right: 18, left: -12, bottom: 0 }}>
          <CartesianGrid stroke={chartTheme.grid} vertical={false} />
          <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: chartTheme.axis, fontSize: 12 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: chartTheme.axis, fontSize: 12 }} allowDecimals={false} />
          <SprintChartTooltip chartTheme={chartTheme} />
          <SprintChartLegend chartTheme={chartTheme} />
          <Line name="Bug 总数" type="monotone" dataKey="total" stroke={chartTheme.total} strokeWidth={2.4} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          <Line name="已解决" type="monotone" dataKey="resolved" stroke={chartTheme.positive} strokeWidth={2.2} dot={{ r: 3 }} />
          <Line name="已关闭" type="monotone" dataKey="closed" stroke={chartTheme.success} strokeWidth={2.2} dot={{ r: 3 }} />
          <Line name="未解决" type="monotone" dataKey="unresolved" stroke={chartTheme.negative} strokeWidth={2.2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
