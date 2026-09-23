/**
 * 测试单的进度与结论统计，供列表里的「进度与指标」列使用。
 *
 * 数据全部来自测试单自身的计数字段（entries*），不做前端推算，也不写死总数。
 */

export type TestOrderProgressKey = 'passed' | 'failed' | 'blocked' | 'skipped'

/** 进度条上还会多出一段「待执行」余量，它不是一个条目结论，所以单独一个 key。 */
export type TestOrderProgressSegmentKey = TestOrderProgressKey | 'pending'

export type TestOrderProgressMetric = {
  key: TestOrderProgressKey
  label: string
  count: number
}

export type TestOrderProgressSegment = {
  key: TestOrderProgressSegmentKey
  label: string
  count: number
  /** 相对条目总数的宽度百分比，保留一位小数。 */
  percent: number
}

export type TestOrderProgress = {
  total: number
  executed: number
  /** 已执行占比，四舍五入到整数百分比。 */
  percent: number
  /** 非零的结论项，顺序固定为通过 / 失败 / 阻塞 / 跳过。 */
  metrics: TestOrderProgressMetric[]
  /** 进度条分段：非零结论 + 末尾的待执行余量，宽度合计 100%。 */
  segments: TestOrderProgressSegment[]
  /** 还没执行的条目数，作为进度条余量。 */
  pending: number
}

const METRIC_LABELS: Array<[TestOrderProgressKey, string]> = [
  ['passed', '通过'],
  ['failed', '失败'],
  ['blocked', '阻塞'],
  ['skipped', '跳过'],
]

const METRIC_FIELDS: Record<TestOrderProgressKey, keyof TestOrderCounts> = {
  passed: 'entriesPassed',
  failed: 'entriesFailed',
  blocked: 'entriesBlocked',
  skipped: 'entriesSkipped',
}

type TestOrderCounts = {
  entriesTotal?: number
  entriesExecuted?: number
  entriesPassed?: number
  entriesFailed?: number
  entriesBlocked?: number
  entriesSkipped?: number
}

/** 相对总数的宽度百分比，保留一位小数；总数为 0 时一律给 0，避免除零和 NaN。 */
function toPercent(part: number, total: number) {
  if (total <= 0) return 0
  return Math.round((part / total) * 1000) / 10
}

export function buildTestOrderProgress(order: TestOrderCounts): TestOrderProgress {
  const total = Math.max(order.entriesTotal ?? 0, 0)
  const executed = Math.max(order.entriesExecuted ?? 0, 0)

  const metrics = METRIC_LABELS.map(([key, label]) => ({
    key,
    label,
    count: Math.max(order[METRIC_FIELDS[key]] ?? 0, 0),
  })).filter((metric) => metric.count > 0)

  const segments: TestOrderProgressSegment[] = metrics.map((metric) => ({
    ...metric,
    percent: toPercent(metric.count, total),
  }))

  const pending = Math.max(total - executed, 0)
  if (pending > 0) {
    segments.push({ key: 'pending', label: '待执行', count: pending, percent: toPercent(pending, total) })
  }

  return {
    total,
    executed,
    percent: total > 0 ? Math.round((executed / total) * 100) : 0,
    metrics,
    segments,
    pending,
  }
}
