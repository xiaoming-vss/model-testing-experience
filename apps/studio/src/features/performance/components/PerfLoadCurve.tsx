import type { PerfLoadCurvePoint } from '../utils/perfLoadModel'
import { formatPerfLoadDuration } from '../utils/perfLoadModel'

export function PerfLoadCurve({
  points,
  totalSeconds,
  maxVus,
}: {
  points: PerfLoadCurvePoint[]
  totalSeconds: number
  maxVus: number
}) {
  const width = 680
  const height = 150
  const padL = 38
  const padR = 18
  const padT = 18
  const padB = 26
  const totalX = Math.max(1, totalSeconds)
  const maxY = Math.max(1, maxVus)
  const px = (t: number) => padL + (t / totalX) * (width - padL - padR)
  const py = (v: number) => height - padB - (v / maxY) * (height - padT - padB)
  const safePoints = points.length > 0 ? points : [{ t: 0, v: 0 }]
  const line = safePoints
    .map((point, index) => `${index ? 'L' : 'M'}${px(point.t).toFixed(1)} ${py(point.v).toFixed(1)}`)
    .join(' ')
  const area = `${line} L ${px(totalX).toFixed(1)} ${height - padB} L ${px(0).toFixed(1)} ${height - padB} Z`
  const grid = [0, 0.25, 0.5, 0.75, 1].map(ratio => {
    const y = padT + ratio * (height - padT - padB)
    return <line
      key={ratio}
      x1={padL}
      y1={y}
      x2={width - padR}
      y2={y}
      className="stroke-app-surface-border"
      strokeWidth={1}
      strokeDasharray="3 5"
      opacity={0.65}
    />
  })

  return <div className="rounded-lg border border-app-surface-border bg-app-surface-hover px-2 pt-1.5">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="负载曲线预览" className="block h-auto w-full">
      <g>{grid}</g>
      <path d={area} className="fill-app-accent/10" />
      <path
        d={line}
        className="fill-none stroke-app-accent"
        strokeWidth={2.2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <text x={padL} y={padT - 4} className="fill-app-surface-text-muted" fontSize={10}>{maxVus} VU</text>
      <text x={padL - 6} y={height - padB + 4} className="fill-app-surface-text-muted" fontSize={10} textAnchor="end">0</text>
      <text x={padL} y={height - 8} className="fill-app-surface-text-muted" fontSize={10}>0</text>
      <text x={width - padR} y={height - 8} className="fill-app-surface-text-muted" fontSize={10} textAnchor="end">{formatPerfLoadDuration(totalSeconds)}</text>
    </svg>
  </div>
}
