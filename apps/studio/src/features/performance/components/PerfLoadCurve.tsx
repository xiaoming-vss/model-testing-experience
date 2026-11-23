import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { PerfLoadCurvePoint } from '../utils/perfLoadModel'
import { formatPerfLoadDuration } from '../utils/perfLoadModel'

const formatAxisTime = (value: number) => value === 0 ? '0' : formatPerfLoadDuration(value)

/** 在保持折线形状不变的前提下补采样点，让悬停提示沿曲线连续取值。 */
function buildCurveData(points: PerfLoadCurvePoint[], totalSeconds: number) {
  if (points.length === 0) return [{ t: 0, v: 0 }]
  if (points.length === 1) return points
  const total = Math.max(1, totalSeconds)
  const step = Math.max(1, total / 240)
  const data: PerfLoadCurvePoint[] = []
  let segment = 0
  for (let t = 0; t <= total; t += step) {
    while (segment < points.length - 2 && points[segment + 1].t < t) segment += 1
    const from = points[segment]
    const to = points[Math.min(segment + 1, points.length - 1)]
    const span = to.t - from.t
    const ratio = span > 0 ? Math.min(1, Math.max(0, (t - from.t) / span)) : 0
    data.push({ t, v: from.v + (to.v - from.v) * ratio })
  }
  const last = points[points.length - 1]
  if (!data.length || data[data.length - 1].t < total) data.push({ t: total, v: last.v })
  return data
}

export function PerfLoadCurve({
  points,
  totalSeconds,
  maxVus,
}: {
  points: PerfLoadCurvePoint[]
  totalSeconds: number
  maxVus: number
}) {
  const totalX = Math.max(1, totalSeconds)
  const maxY = Math.max(1, maxVus)
  const data = buildCurveData(points, totalX)
  const yTicks = [...new Set([0, 0.25, 0.5, 0.75, 1].map(ratio => Math.round(maxY * ratio)))]

  return <div className="rounded-lg border border-app-surface-border bg-app-surface-hover px-2 pt-2" role="img" aria-label="负载曲线预览">
    <ResponsiveContainer width="100%" aspect={680 / 150}>
      <AreaChart data={data} margin={{ top: 14, right: 18, left: 0, bottom: 4 }}>
        <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 5" vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          domain={[0, totalX]}
          ticks={[0, totalX]}
          axisLine={{ stroke: 'var(--chart-axis)', strokeWidth: 1 }}
          tickLine={false}
          tick={{ fill: 'var(--chart-axis)', fontSize: 10 }}
          tickFormatter={formatAxisTime}
        />
        <YAxis
          domain={[0, maxY]}
          ticks={yTicks}
          width={40}
          axisLine={{ stroke: 'var(--chart-axis)', strokeWidth: 1 }}
          tickLine={false}
          tick={{ fill: 'var(--chart-axis)', fontSize: 10 }}
          tickFormatter={(value: number) => value === 0 ? '0' : value === maxY ? `${maxY} VU` : ''}
        />
        <RechartsTooltip
          cursor={{ stroke: 'var(--app-accent)', strokeWidth: 1, strokeDasharray: '3 3' }}
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null
            return <div className="rounded-lg border border-[var(--chart-tooltip-border)] bg-[var(--chart-tooltip-bg)] px-2.5 py-1.5 text-[11px] leading-4 shadow-[0_6px_16px_var(--app-glass-shadow-card)]">
              <div className="font-semibold text-[var(--chart-tooltip-text)]">时间 {formatPerfLoadDuration(Number(label))}</div>
              <div className="text-[var(--chart-axis)]">负载 {Math.round(Number(payload[0].value))} VU</div>
            </div>
          }}
        />
        <Area
          type="linear"
          dataKey="v"
          stroke="var(--app-accent)"
          strokeWidth={1.6}
          fill="var(--app-accent)"
          fillOpacity={0.1}
          dot={false}
          activeDot={{ r: 3, strokeWidth: 1.5 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  </div>
}
