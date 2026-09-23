import { describe, expect, it } from 'vitest'

import {
  buildUiRunLogLines,
  buildUiRunMetrics,
  buildUiStepSnapshots,
  formatUiCaseSerial,
  formatUiRunLogTime,
  formatUiRunRelativeTime,
  getUiRunTone,
  getUiSuiteReadiness,
  indexUiRunStepResultsByOrder,
} from './detailRunView'

const stepResults = [
  { orderNo: 2, stepName: '输入用户名', keyword: 'input', status: 'failed' as const, durationMs: 45, startedAt: '2026-09-23T02:42:01.442', actualValue: 'admin', errorMessage: '元素未找到' },
  { orderNo: 1, stepName: '打开登录页', keyword: 'open', status: 'success' as const, durationMs: 312, startedAt: '2026-09-23T02:42:01.120' },
]

describe('UI 运行视图数据', () => {
  it('把步骤结果按顺序号整理成快照，并给出色调与用时', () => {
    const snapshots = buildUiStepSnapshots(stepResults)

    expect(snapshots.map((item) => item.name)).toEqual(['打开登录页', '输入用户名'])
    expect(snapshots[0].tone).toBe('green')
    expect(snapshots[0].durationText).toBe('312ms')
    // 失败以 success=false 为准，状态文案不跟着 status 走
    expect(snapshots[1].statusLabel).toBe('失败')
    expect(snapshots[1].tone).toBe('red')
  })

  it('日志行按关键字分级，末行汇总来自实际计数', () => {
    const lines = buildUiRunLogLines({ runId: 'run-1', status: 'failed', durationMs: 1840, stepResults })

    expect(lines.map((line) => line.level)).toEqual(['info', 'error', 'done'])
    expect(lines[0].command).toBe('open("打开登录页")')
    expect(lines[0].result).toBe('成功 · 312ms')
    expect(lines[1].result).toContain('元素未找到')
    expect(lines[2].result).toBe('测试用例执行完成，共 2 步，通过 1 步，失败 1 步，总耗时 1840 ms。')
  })

  it('等待与断言步骤各有自己的日志级别', () => {
    const lines = buildUiRunLogLines({
      status: 'success',
      stepResults: [
        { orderNo: 1, stepName: '等待', keyword: 'sleep', status: 'success' },
        { orderNo: 2, stepName: '断言 URL', keyword: 'assert_url', status: 'success' },
      ],
    })

    expect(lines[0].level).toBe('wait')
    expect(lines[1].level).toBe('assert')
  })

  it('指标取真实的耗时与通过 / 失败步骤数，没有运行记录时是空值', () => {
    expect(buildUiRunMetrics({ runId: 'run-1', durationMs: 1840, stepResults })).toEqual([
      { key: 'duration', label: '运行耗时', value: '1840 ms' },
      { key: 'passed', label: '通过步骤', value: '1 / 2', tone: 'green' },
      { key: 'failed', label: '失败步骤', value: '1', tone: 'red' },
    ])
    expect(buildUiRunMetrics(null).map((item) => item.value)).toEqual(['-', '0 / 0', '0'])
  })

  it('就绪结论取自最近一次测试集运行', () => {
    expect(getUiSuiteReadiness(null).label).toBe('未运行')
    expect(getUiSuiteReadiness({ status: 'success' })).toMatchObject({ label: '就绪 (Ready)', tone: 'green' })
    expect(getUiSuiteReadiness({ status: 'failed' })).toMatchObject({ label: '存在失败', tone: 'red' })
    expect(getUiSuiteReadiness({ status: 'running' })).toMatchObject({ label: '运行中', tone: 'blue' })
  })

  it('相对时间按分钟 / 小时 / 天分档，超过七天不给相对值', () => {
    const now = new Date('2026-09-23T10:00:00Z').getTime()

    expect(formatUiRunRelativeTime('2026-09-23T09:58:30Z', now)).toBe('1分钟前')
    expect(formatUiRunRelativeTime('2026-09-23T07:00:00Z', now)).toBe('3小时前')
    expect(formatUiRunRelativeTime('2026-09-20T10:00:00Z', now)).toBe('3天前')
    expect(formatUiRunRelativeTime('2026-09-01T10:00:00Z', now)).toBe('')
    expect(formatUiRunRelativeTime(undefined, now)).toBe('')
  })

  it('按顺序号建索引，重复的顺序号保留第一条', () => {
    const byOrder = indexUiRunStepResultsByOrder([
      { orderNo: 2, stepName: '晚到的第二条' },
      { orderNo: 1, stepName: '第一条' },
      { orderNo: 2, stepName: '重复的第二条' },
    ])

    expect([...byOrder.keys()].sort()).toEqual([1, 2])
    expect(byOrder.get(2)?.stepName).toBe('晚到的第二条')
    expect(indexUiRunStepResultsByOrder([{ stepName: '没有序号' }]).get(1)?.stepName).toBe('没有序号')
  })

  it('日志时间戳带毫秒，用例序号补齐两位', () => {
    expect(formatUiRunLogTime('2026-09-23T02:42:01.120Z')).toMatch(/^\d{2}:\d{2}:\d{2}\.120$/)
    expect(formatUiCaseSerial(2)).toBe('CASE-02')
    expect(formatUiCaseSerial(undefined)).toBe('')
    expect(getUiRunTone('success')).toBe('green')
    expect(getUiRunTone('canceled')).toBe('slate')
  })
})
