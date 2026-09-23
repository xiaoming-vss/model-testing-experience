/*
 * UI测试集详情页右栏（回放 / 快照 / 控制台）的纯展示数据。
 *
 * 设计稿的右栏是「录屏回放 + 关键帧快照 + Playwright 控制台 + 性能微指标」，其中录屏、视觉差异基线、
 * FCP / 网络请求数 / 内存占用都没有对应数据（见 STRUCTURE.md 的「设计稿里没实现的部分」）。
 * 这里只把已有的运行记录（UiTestCaseRun）整理成可渲染的形态：逐步快照、日志行、指标。
 *
 * 色调映射到 shared/styles/surface-tokens.css 的九色盘类名，页面里写成 `tone-${tone}`，
 * 不要在组件里写死颜色。
 */

import type { UiTestCaseRun, UiTestCaseRunStepResult, UiTestSuiteRunSummary } from '@/services/api'

import { getExecutionStatusMeta } from './runHelpers'

/** 九色盘里本页用到的色调，对应 `.tone-green` 等类名。 */
export type UiRunTone = 'green' | 'red' | 'orange' | 'blue' | 'slate'

export function getUiRunTone(status?: string): UiRunTone {
  switch (status) {
    case 'success':
      return 'green'
    case 'failed':
      return 'red'
    case 'error':
      return 'orange'
    case 'running':
    case 'claimed':
      return 'blue'
    default:
      return 'slate'
  }
}

export type UiSuiteReadiness = {
  label: string
  tone: UiRunTone
  /** 悬停说明，解释这个结论是从哪次运行推出来的。 */
  hint: string
}

/** 顶栏的就绪结论：取自最近一次测试集运行，没有运行记录时是「未运行」。 */
export function getUiSuiteReadiness(run?: UiTestSuiteRunSummary | null): UiSuiteReadiness {
  if (!run) {
    return { label: '未运行', tone: 'slate', hint: '当前测试集还没有运行记录' }
  }

  const status = run.status

  if (status === 'pending' || status === 'claimed' || status === 'running') {
    return { label: '运行中', tone: 'blue', hint: '最近一次测试集运行尚未结束' }
  }

  if (status === 'success') {
    return { label: '就绪 (Ready)', tone: 'green', hint: '最近一次测试集运行全部通过' }
  }

  if (status === 'failed' || status === 'error') {
    return { label: '存在失败', tone: 'red', hint: '最近一次测试集运行有失败或异常的用例' }
  }

  return { label: getExecutionStatusMeta(status).label, tone: 'slate', hint: '最近一次测试集运行的结论' }
}

/** 相对时间：控制台与顶栏都按「多久之前」读，超过 7 天回落到绝对时间。 */
export function formatUiRunRelativeTime(value?: string, now: number = Date.now()) {
  if (!value) return ''

  const timestamp = parseRunTime(value)
  if (timestamp === null) return ''

  const diffMs = now - timestamp
  if (diffMs < 0) return '刚刚'

  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`

  const days = Math.floor(hours / 24)
  if (days <= 7) return `${days}天前`

  return ''
}

/** 与 utils/format.tsx 的 formatTime 同一套时区假设：无时区的 ISO 字符串按 UTC 解读。 */
function parseRunTime(value: string) {
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
  const isIsoDateTime = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(value)
  const normalized = !hasTimezone && isIsoDateTime ? `${value.replace(' ', 'T')}Z` : value
  const date = new Date(normalized)

  return Number.isNaN(date.getTime()) ? null : date.getTime()
}

/** 控制台行首的时间戳：只要时分秒，带上毫秒以便对齐设计稿。 */
export function formatUiRunLogTime(value?: string) {
  if (!value) return ''

  const timestamp = parseRunTime(value)
  if (timestamp === null) return ''

  const date = new Date(timestamp)
  const clock = [date.getHours(), date.getMinutes(), date.getSeconds()]
    .map((part) => String(part).padStart(2, '0'))
    .join(':')

  return `${clock}.${String(date.getMilliseconds()).padStart(3, '0')}`
}

/** 用例序号徽标：`CASE-02`。没有 orderNo 时不编造编号。 */
export function formatUiCaseSerial(orderNo?: number) {
  if (typeof orderNo !== 'number' || orderNo <= 0) return ''

  return `CASE-${String(orderNo).padStart(2, '0')}`
}

/** 关键帧上的用时标签：设计稿写作 `0.3s`，超过一分钟折算成 `1:02`。 */
export function formatUiElapsedTime(offsetMs?: number) {
  if (typeof offsetMs !== 'number' || !Number.isFinite(offsetMs) || offsetMs < 0) return ''

  if (offsetMs < 60_000) return `${(offsetMs / 1000).toFixed(1)}s`

  const totalSeconds = Math.round(offsetMs / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  return `${minutes}:${String(totalSeconds % 60).padStart(2, '0')}`
}

export type UiStepSnapshot = {
  key: string
  orderNo?: number
  name: string
  keyword: string
  status?: string
  statusLabel: string
  tone: UiRunTone
  durationText: string
  /** 相对本次运行第一步开始时间的耗时，关键帧角标用。 */
  elapsedText: string
  screenshotPath?: string
  actualValue?: string
  errorMessage?: string
}

export function buildUiStepSnapshots(stepResults: UiTestCaseRunStepResult[]): UiStepSnapshot[] {
  const startedTimes = stepResults
    .map((stepResult) => parseRunTime(stepResult.startedAt ?? ''))
    .filter((value): value is number => value !== null)
  const runStartedAt = startedTimes.length > 0 ? Math.min(...startedTimes) : null

  return [...stepResults]
    .sort((left, right) => (left.orderNo ?? Number.MAX_SAFE_INTEGER) - (right.orderNo ?? Number.MAX_SAFE_INTEGER))
    .map((stepResult, index) => {
      const order = stepResult.orderNo ?? index + 1
      const meta = getExecutionStatusMeta(stepResult.status)
      const stepStartedAt = parseRunTime(stepResult.startedAt ?? '')

      return {
        key: `${stepResult.orderNo ?? index}-${stepResult.stepName ?? index}`,
        orderNo: stepResult.orderNo,
        name: stepResult.stepName?.trim() || `步骤 ${order}`,
        keyword: stepResult.keyword?.trim() || '',
        status: stepResult.status,
        statusLabel: stepResult.success === false ? '失败' : meta.label,
        tone: getUiRunTone(stepResult.status),
        durationText: formatUiStepDuration(stepResult.durationMs),
        elapsedText:
          runStartedAt === null || stepStartedAt === null ? '' : formatUiElapsedTime(stepStartedAt - runStartedAt),
        screenshotPath: stepResult.screenshotPath,
        actualValue: stepResult.actualValue,
        errorMessage: stepResult.errorMessage,
      }
    })
}

export function formatUiStepDuration(durationMs?: number) {
  if (typeof durationMs !== 'number') return ''

  return `${durationMs}ms`
}

/**
 * 按 orderNo 给步骤结果建索引，供步骤行按序号取自己那一条。
 * 同一序号出现多次时保留第一条，避免徽标在重复结果上闪来闪去。
 */
export function indexUiRunStepResultsByOrder(stepResults: UiTestCaseRunStepResult[]) {
  const byOrder = new Map<number, UiTestCaseRunStepResult>()

  stepResults.forEach((stepResult, index) => {
    const order = stepResult.orderNo ?? index + 1
    if (!byOrder.has(order)) byOrder.set(order, stepResult)
  })

  return byOrder
}

/** 步骤行上的运行结论徽标：`PASS` / `FAIL` / `SKIP` / `RUN`。 */
export function formatUiStepResultBadge(status?: string, success?: boolean) {
  switch (status) {
    case 'success':
      return 'PASS'
    case 'failed':
    case 'error':
      return 'FAIL'
    case 'skipped':
      return 'SKIP'
    case 'canceled':
      return 'CANCEL'
    case 'pending':
    case 'claimed':
    case 'running':
      return 'RUN'
    default:
      if (success === true) return 'PASS'
      if (success === false) return 'FAIL'
      return 'RUN'
  }
}

export type UiRunLogLevel = 'info' | 'wait' | 'assert' | 'error' | 'done'

export type UiRunLogLine = {
  key: string
  level: UiRunLogLevel
  time: string
  /** 主文案：`keyword("步骤名")`。 */
  command: string
  /** 右半段：状态、耗时、实际值与错误信息。 */
  result: string
}

const WAIT_KEYWORDS = new Set(['sleep', 'wait_text', 'wait_selector', 'wait'])

function getUiStepLogLevel(snapshot: UiStepSnapshot): UiRunLogLevel {
  if (snapshot.status === 'failed' || snapshot.status === 'error') return 'error'
  if (snapshot.keyword.startsWith('assert')) return 'assert'
  if (WAIT_KEYWORDS.has(snapshot.keyword)) return 'wait'

  return 'info'
}

/**
 * 把一次运行的步骤结果拼成控制台行。没有真实的 Playwright 日志通道，
 * 所以每行都直接来自该步骤的结果字段，最后一行的汇总结论也按实际计数生成。
 */
export function buildUiRunLogLines(run?: UiTestCaseRun | null): UiRunLogLine[] {
  const orderedResults = [...(run?.stepResults ?? [])].sort(
    (left, right) => (left.orderNo ?? Number.MAX_SAFE_INTEGER) - (right.orderNo ?? Number.MAX_SAFE_INTEGER),
  )
  const snapshots = buildUiStepSnapshots(orderedResults)
  const lines: UiRunLogLine[] = snapshots.map((snapshot, index) => ({
    key: `log-${snapshot.key}`,
    level: getUiStepLogLevel(snapshot),
    time: formatUiRunLogTime(orderedResults[index]?.startedAt),
    command: `${snapshot.keyword || 'step'}("${snapshot.name}")`,
    result: [snapshot.statusLabel, snapshot.durationText, snapshot.actualValue, snapshot.errorMessage]
      .filter(Boolean)
      .join(' · '),
  }))

  if (run?.errorMessage) {
    lines.push({
      key: 'log-run-error',
      level: 'error',
      time: '',
      command: 'run',
      result: run.errorMessage,
    })
  }

  if (!run) return lines

  const successCount = snapshots.filter((item) => item.status === 'success').length
  const failedCount = snapshots.filter((item) => item.status === 'failed' || item.status === 'error').length
  const durationText = typeof run.durationMs === 'number' ? `，总耗时 ${run.durationMs} ms` : ''

  lines.push({
    key: 'log-done',
    level: 'done',
    time: '',
    command: '',
    result: `测试用例执行完成，共 ${snapshots.length} 步，通过 ${successCount} 步，失败 ${failedCount} 步${durationText}。`,
  })

  return lines
}

export type UiRunMetric = {
  key: string
  label: string
  value: string
  tone?: UiRunTone
}

/** 设计稿的 FCP / 网络请求数 / 内存占用没有数据源，换成运行记录里真实存在的三项。 */
export function buildUiRunMetrics(run?: UiTestCaseRun | null): UiRunMetric[] {
  const snapshots = buildUiStepSnapshots(run?.stepResults ?? [])
  const successCount = snapshots.filter((item) => item.status === 'success').length
  const failedCount = snapshots.filter((item) => item.status === 'failed' || item.status === 'error').length

  return [
    {
      key: 'duration',
      label: '运行耗时',
      value: typeof run?.durationMs === 'number' ? `${run.durationMs} ms` : '-',
    },
    {
      key: 'passed',
      label: '通过步骤',
      value: `${successCount} / ${snapshots.length}`,
      tone: successCount > 0 ? 'green' : undefined,
    },
    {
      key: 'failed',
      label: '失败步骤',
      value: String(failedCount),
      tone: failedCount > 0 ? 'red' : undefined,
    },
  ]
}
