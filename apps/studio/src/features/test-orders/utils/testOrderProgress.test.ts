import { describe, expect, it } from 'vitest'
import { buildTestOrderProgress } from './testOrderProgress'

describe('测试单进度统计', () => {
  it('按条目计数算出执行率、非零结论项与待执行余量', () => {
    const progress = buildTestOrderProgress({
      entriesTotal: 24,
      entriesExecuted: 18,
      entriesPassed: 15,
      entriesFailed: 3,
    })

    expect(progress.total).toBe(24)
    expect(progress.executed).toBe(18)
    expect(progress.percent).toBe(75)
    expect(progress.pending).toBe(6)
    expect(progress.metrics).toEqual([
      { key: 'passed', label: '通过', count: 15 },
      { key: 'failed', label: '失败', count: 3 },
    ])
    // 分段宽度是相对总数的比例，待执行段补足到 100%
    expect(progress.segments.map((segment) => [segment.key, segment.percent])).toEqual([
      ['passed', 62.5],
      ['failed', 12.5],
      ['pending', 25],
    ])
  })

  it('一条都没执行时没有结论项，只有整条待执行', () => {
    const progress = buildTestOrderProgress({ entriesTotal: 84, entriesExecuted: 0 })

    expect(progress.percent).toBe(0)
    expect(progress.metrics).toEqual([])
    expect(progress.segments).toEqual([{ key: 'pending', label: '待执行', count: 84, percent: 100 }])
  })

  it('跳过单独成段，不与待执行混为一谈', () => {
    const progress = buildTestOrderProgress({
      entriesTotal: 4,
      entriesExecuted: 3,
      entriesPassed: 1,
      entriesSkipped: 2,
    })

    expect(progress.metrics.map((metric) => metric.key)).toEqual(['passed', 'skipped'])
    expect(progress.segments.map((segment) => segment.key)).toEqual(['passed', 'skipped', 'pending'])
    expect(progress.segments.map((segment) => segment.percent)).toEqual([25, 50, 25])
  })

  it('缺字段、总数为 0、计数为负都不产生 NaN 或负宽度', () => {
    expect(buildTestOrderProgress({})).toMatchObject({ total: 0, executed: 0, percent: 0, pending: 0, segments: [] })

    const odd = buildTestOrderProgress({ entriesTotal: 0, entriesExecuted: -3, entriesPassed: -1 })
    expect(odd.executed).toBe(0)
    expect(odd.metrics).toEqual([])
    expect(odd.segments).toEqual([])
  })

  it('执行数超过总数时不出现负数余量', () => {
    const progress = buildTestOrderProgress({ entriesTotal: 2, entriesExecuted: 5, entriesPassed: 5 })

    expect(progress.pending).toBe(0)
    expect(progress.percent).toBe(250)
    expect(progress.segments.map((segment) => segment.key)).toEqual(['passed'])
  })
})
