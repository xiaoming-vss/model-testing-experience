import sprintOverviewStyles from '../styles/sprint-overview.module.css'
import { useLocalDate } from '@/domain/projects/hooks/useLocalDate'
import { saveBlob } from '@/shared/utils/download'
import { ActionButton } from '@/shared/components/ActionButton'
import { usePendingRequestId } from '@/shared/hooks/usePendingRequestId'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { ProjectAccessScope } from '@/domain/projects/components/ProjectAccessScope'
import { AppstoreOutlined, ArrowLeftOutlined, CodeOutlined, DesktopOutlined, FileTextOutlined } from '@ant-design/icons'
import { workbenchTabsCompactClass } from '@/shared/utils/surfaceClasses'
import { Alert, Button, Card, DatePicker, Drawer, Empty, Form, Input, Modal, Select, Space, Spin, Tooltip, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import type { FormInstance } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import { goBackOrFallback } from '@/shared/utils/backNavigation'
import {
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import dayjs, { type Dayjs } from 'dayjs'
import { TestReportHistoryDrawer } from '@/features/projects/components/TestReportHistoryDrawer'
import { useSprintBoundaryRefresh } from '@/domain/projects/hooks/useSprintBoundaryRefresh'
import { api, listItems, type SprintDailyMetricsSnapshot, type SprintDailyMetricsTestStats, type TestReportGenerateRun } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

const { Text, Title } = Typography
const { RangePicker } = DatePicker

const sprintChartTheme = {
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

type SprintChartTheme = typeof sprintChartTheme

function SprintChartTooltip({ chartTheme }: { chartTheme: SprintChartTheme }) {
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

function SprintChartLegend({ chartTheme }: { chartTheme: SprintChartTheme }) {
  return (
    <Legend
      verticalAlign="bottom"
      height={32}
      iconType="circle"
      formatter={(value) => <span style={{ color: chartTheme.axis }}>{value}</span>}
    />
  )
}

function numberValue(...values: Array<number | undefined>) {
  return values.find((value) => typeof value === 'number' && Number.isFinite(value)) ?? 0
}

function snapshotDate(snapshot?: SprintDailyMetricsSnapshot) {
  return snapshot?.snapshotDate ?? snapshot?.snapshot_date ?? snapshot?.date ?? '-'
}

function pickTestStats(
  snapshot: SprintDailyMetricsSnapshot | undefined,
  keys: Array<keyof SprintDailyMetricsSnapshot>,
): Required<SprintDailyMetricsTestStats> {
  const stats = keys.map((key) => snapshot?.[key]).find((value): value is SprintDailyMetricsTestStats => Boolean(value))
  return {
    total: numberValue(stats?.total),
    executed: numberValue(stats?.executed),
    pending: numberValue(stats?.pending, stats?.unexecuted),
    unexecuted: numberValue(stats?.unexecuted, stats?.pending),
    success: numberValue(stats?.success, stats?.passed),
    failed: numberValue(stats?.failed),
    passed: numberValue(stats?.passed, stats?.success),
  }
}

function normalizeDailyMetrics(snapshot?: SprintDailyMetricsSnapshot) {
  const functional = pickTestStats(snapshot, ['functional', 'function', 'functionTesting', 'function_testing'])
  const apiStats = pickTestStats(snapshot, ['api'])
  const uiStats = pickTestStats(snapshot, ['ui'])
  const bugStats = snapshot?.bug ?? snapshot?.bugs

  return {
    snapshotDate: snapshotDate(snapshot),
    totalCases: numberValue(
      snapshot?.totalCases,
      snapshot?.total_cases,
      functional.total + apiStats.total + uiStats.total,
    ),
    functional: {
      total: numberValue(snapshot?.functionTotal, snapshot?.function_total, functional.total),
      executed: functional.executed,
      unexecuted: functional.pending,
      success: functional.success,
      failed: functional.failed,
    },
    api: {
      total: numberValue(snapshot?.apiTotal, snapshot?.api_total, apiStats.total),
      executed: apiStats.executed,
      unexecuted: apiStats.pending,
      success: apiStats.success,
      failed: apiStats.failed,
    },
    ui: {
      total: numberValue(snapshot?.uiTotal, snapshot?.ui_total, uiStats.total),
      executed: uiStats.executed,
      unexecuted: uiStats.pending,
      success: uiStats.success,
      failed: uiStats.failed,
    },
    bug: {
      collected: Boolean(snapshot) && snapshot?.bug !== null,
      total: numberValue(snapshot?.bugTotal, snapshot?.bug_total, bugStats?.total),
      resolved: numberValue(snapshot?.bugResolved, snapshot?.bug_resolved, bugStats?.resolved),
      closed: numberValue(snapshot?.bugClosed, snapshot?.bug_closed, bugStats?.closed),
      unresolved: numberValue(snapshot?.bugUnresolved, snapshot?.bug_unresolved, bugStats?.unresolved),
      fatal: numberValue(snapshot?.bugFatal, snapshot?.bug_fatal, bugStats?.fatal),
      severe: numberValue(snapshot?.bugSevere, snapshot?.bug_severe, bugStats?.serious, bugStats?.severe),
      normal: numberValue(snapshot?.bugNormal, snapshot?.bug_normal, bugStats?.normal),
      hint: numberValue(snapshot?.bugHint, snapshot?.bug_hint, bugStats?.suggestion, bugStats?.hint),
    },
  }
}

function SummaryMetric({ label, value, icon }: { label: string; value: number | string; icon?: ReactNode }) {
  return (
    <div className="sprint-overview-summary-metric flex min-h-8 min-w-0 items-center gap-2.5 rounded-[10px] border border-[var(--app-info-border)] bg-[var(--app-info-surface)] px-2">
      {icon ? <span className="sprint-overview-summary-icon inline-flex h-7 w-7 flex-none items-center justify-center rounded-[8px] bg-[var(--app-accent-soft)] text-[var(--app-accent)]">{icon}</span> : null}
      <span className="sprint-overview-summary-copy flex min-w-0 items-baseline gap-2 whitespace-nowrap">
        <span className="sprint-overview-summary-label text-[12px] leading-[18px] text-[var(--app-text-caption)]">{label}</span>
        <strong className="sprint-overview-summary-value text-[14px] font-bold leading-[18px] text-[var(--app-shell-text)]">{value}</strong>
      </span>
    </div>
  )
}

function percentValue(value: number, total: number) {
  if (!total) return 0
  return Math.round((value / total) * 100)
}

function SprintHealthSummary({ metrics }: { metrics: NormalizedDailyMetrics }) {
  const unexecuted = metrics.functional.unexecuted + metrics.api.unexecuted + metrics.ui.unexecuted
  const executed = metrics.functional.executed + metrics.api.executed + metrics.ui.executed
  const success = metrics.functional.success + metrics.api.success + metrics.ui.success
  const failed = metrics.functional.failed + metrics.api.failed + metrics.ui.failed
  const executionPercent = percentValue(executed, metrics.totalCases)

  return (
    <div className="sprint-dashboard-health-band grid rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-none grid-cols-[minmax(200px,0.7fr)_minmax(280px,1fr)_minmax(300px,1fr)] items-center gap-4 p-4 max-[1280.01px]:grid-cols-2 max-[768.01px]:grid-cols-1">
      <div className="sprint-dashboard-health-title flex min-h-14 min-w-0 items-center gap-3">
        <span className="sprint-dashboard-health-icon inline-flex h-9 w-9 flex-none items-center justify-center rounded-[8px] bg-[var(--app-accent-emphasis)] text-xl text-[var(--app-accent)]">
          <FileTextOutlined />
        </span>
        <div className="sprint-dashboard-health-copy flex min-w-0 flex-col gap-[7px]">
          <div className="sprint-dashboard-health-title-row flex min-w-0 flex-wrap items-center gap-2">
            <Title level={4} className="m-0 text-[15px] font-semibold leading-6">迭代健康摘要</Title>
          </div>
          <Text type="secondary" className="sprint-dashboard-health-caption block text-[13px] leading-[22px]">
            {metrics.totalCases} 个用例，{metrics.bug.collected ? `${metrics.bug.total} 个缺陷` : '缺陷未采集'}
          </Text>
        </div>
      </div>
      <div className="sprint-dashboard-health-progress flex min-w-0 flex-col gap-2 border-x border-[var(--app-frame-divider)] px-5 max-[1200.01px]:border-r-0 max-[1200.01px]:pr-0">
        <div className="sprint-dashboard-health-progress-head flex items-baseline justify-between gap-3">
          <Text strong>执行进度</Text>
          <strong className="text-[14px] leading-6 text-[var(--app-shell-text)]">{executionPercent}%</strong>
        </div>
        <div className="sprint-dashboard-health-track flex h-2 w-full overflow-hidden rounded-full bg-[var(--app-progress-track)]">
          <span className="sprint-dashboard-health-fill sprint-dashboard-health-fill-executed h-full bg-[var(--app-result-success)]" style={{ width: `${executionPercent}%` }} />
          <span className="sprint-dashboard-health-fill sprint-dashboard-health-fill-pending h-full bg-[var(--app-result-pending)]" style={{ width: `${percentValue(unexecuted, metrics.totalCases)}%` }} />
        </div>
        <div className="sprint-dashboard-health-legend flex [&_span]:inline-flex [&_span]:items-center [&_span]:gap-[5px] [&_strong]:text-[var(--app-shell-text)] flex-wrap items-center gap-[18px] text-[12px] leading-[18px] text-[var(--app-text-label)]">
          <span style={{ '--legend-color': 'var(--chart-pending)' } as CSSProperties}>未执行 <strong>{unexecuted}</strong></span>
          <span style={{ '--legend-color': 'var(--chart-positive)' } as CSSProperties}>已执行 <strong>{executed}</strong></span>
          <span style={{ '--legend-color': 'var(--chart-total)' } as CSSProperties}>成功 <strong>{success}</strong></span>
          <span style={{ '--legend-color': 'var(--chart-negative)' } as CSSProperties}>失败 <strong>{failed}</strong></span>
        </div>
      </div>
      <div className="sprint-dashboard-health-defects grid grid-cols-5 gap-3 max-[1280.01px]:col-span-2 max-[768.01px]:col-span-1 [&>span]:flex [&>span]:min-w-0 [&>span]:flex-col [&>span]:gap-0.5 [&>span]:text-[12px] [&>span]:leading-[18px] [&>span]:text-[var(--app-text-caption)] [&_strong]:text-xl [&_strong]:leading-7 [&_strong]:text-[var(--app-shell-text)]">
        <span>
          缺陷
          <strong>{metrics.bug.collected ? metrics.bug.total : '—'}</strong>
        </span>
        <span>
          已解决
          <strong className="sprint-dashboard-health-green text-[var(--app-result-success)]">{metrics.bug.collected ? metrics.bug.resolved : '—'}</strong>
        </span>
        <span>
          已关闭
          <strong className="sprint-dashboard-health-blue text-[var(--app-accent)]">{metrics.bug.collected ? metrics.bug.closed : '—'}</strong>
        </span>
        <span>
          未解决
          <strong className="sprint-dashboard-health-red text-[var(--app-result-failed)]">{metrics.bug.collected ? metrics.bug.unresolved : '—'}</strong>
        </span>
        <span>
          解决率
          <strong className="sprint-dashboard-health-green text-[var(--app-result-success)]">{metrics.bug.collected ? `${percentValue(metrics.bug.resolved, metrics.bug.total)}%` : '—'}</strong>
        </span>
      </div>
    </div>
  )
}

function MiniProgress({
  value,
  total,
  color,
}: {
  value: number
  total: number
  color: string
}) {
  return (
    <span className="sprint-dashboard-progress flex min-w-0 flex-col gap-1.5">
      <span className="sprint-dashboard-progress-meta flex items-baseline gap-1 text-[12px] leading-4 text-[var(--app-text-caption)] [&_strong]:text-[var(--app-text-strong)]">
        <strong>{value}</strong>
        <span>({percentValue(value, total)}%)</span>
      </span>
      <span className="sprint-dashboard-progress-track block h-1.5 w-full overflow-hidden rounded-full bg-[var(--app-progress-track)]">
        <span
          className="sprint-dashboard-progress-fill block h-full min-w-1 rounded-[inherit]"
          style={{ width: `${percentValue(value, total)}%`, '--progress-color': color } as CSSProperties}
        />
      </span>
    </span>
  )
}

function TestTypeIcon({ type }: { type: 'functional' | 'api' | 'ui' }) {
  const icon = {
    functional: <AppstoreOutlined />,
    api: <CodeOutlined />,
    ui: <DesktopOutlined />,
  }[type]

  return <span className="sprint-dashboard-test-icon inline-flex h-[34px] w-[34px] flex-none items-center justify-center rounded-[10px] bg-[var(--app-accent-selection)] text-[18px] text-[var(--app-accent)]">{icon}</span>
}

function TestExecutionOverviewCard({ metrics }: { metrics: NormalizedDailyMetrics }) {
  const rows = [
    { key: 'functional' as const, title: '功能测试', stats: metrics.functional },
    { key: 'api' as const, title: 'API 测试', stats: metrics.api },
    { key: 'ui' as const, title: 'UI 测试', stats: metrics.ui },
  ]

  return (
    <Card className="sprint-overview-card sprint-overview-card-rich rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-none sprint-dashboard-panel min-h-0 max-[768.01px]:overflow-x-auto">
      <div className="sprint-dashboard-card-head mb-1.5 flex flex-wrap items-start justify-between gap-3">
        <Title level={4} className="m-0 text-[15px] font-semibold leading-6">测试执行概览</Title>
      </div>
      <div className="sprint-dashboard-test-table grid min-h-0 flex-auto grid-rows-[32px_repeat(3,56px)] content-stretch border-t border-[var(--app-frame-divider-soft)] max-[768.01px]:min-w-[640px] min-[1281px]:grid-rows-[32px_repeat(3,minmax(56px,1fr))]">
        <div className="sprint-dashboard-test-row sprint-dashboard-test-row-head grid grid-cols-[minmax(120px,1.2fr)_72px_repeat(4,minmax(92px,1fr))] items-center gap-2.5 border-b border-[var(--app-list-row-border)] bg-[var(--app-frame-row-hover)] py-1.5 text-[12px] font-bold leading-[18px] text-[var(--app-text-label)] last:border-b-0">
          <span>测试类型</span>
          <span>总数</span>
          <span>已执行</span>
          <span>未执行</span>
          <span>成功</span>
          <span>失败</span>
        </div>
        {rows.map((row) => (
          <div className="sprint-dashboard-test-row grid grid-cols-[minmax(120px,1.2fr)_72px_repeat(4,minmax(92px,1fr))] items-center gap-2.5 border-b border-[var(--app-list-row-border)] py-1.5 last:border-b-0" key={row.key}>
            <span className="sprint-dashboard-test-name flex min-w-0 items-center gap-2.5 text-[var(--app-shell-text)]">
              <TestTypeIcon type={row.key} />
              <strong>{row.title}</strong>
            </span>
            {row.key === 'functional' && row.stats.total === 0 ? (
              <Tooltip title="功能用例的执行结果由平台测试单产生，本迭代还没有测试单">
                <span className="sprint-dashboard-test-empty col-[2/-1] min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] leading-[18px] text-[var(--app-shell-text-muted)]">本迭代暂无平台执行记录</span>
              </Tooltip>
            ) : (
              <>
                <strong className="sprint-dashboard-test-total text-[18px] leading-6 text-[var(--app-shell-text)]">{row.stats.total}</strong>
                <MiniProgress value={row.stats.executed} total={row.stats.total} color="var(--chart-positive)" />
                <MiniProgress value={row.stats.unexecuted} total={row.stats.total} color="var(--chart-pending)" />
                <MiniProgress value={row.stats.success} total={row.stats.total} color="var(--chart-success)" />
                <MiniProgress value={row.stats.failed} total={row.stats.total} color="var(--chart-negative)" />
              </>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}

function SeverityLine({
  label,
  value,
  total,
  color,
}: {
  label: string
  value: number
  total: number
  color: string
}) {
  return (
    <div className="sprint-dashboard-severity-row grid grid-cols-[32px_minmax(0,1fr)_62px] items-center gap-2 text-[12px] leading-5 text-[var(--app-text-label)] [&_strong]:text-right [&_strong]:font-semibold [&_strong]:text-[var(--app-text-strong)]">
      <span>{label}</span>
      <span className="sprint-dashboard-severity-track block h-1.5 w-full overflow-hidden rounded-full bg-[var(--app-progress-track)]">
        <span
          className="sprint-dashboard-severity-fill block h-full min-w-1 rounded-[inherit]"
          style={{ width: `${percentValue(value, total)}%`, '--severity-color': color } as CSSProperties}
        />
      </span>
      <strong>
        {value} ({percentValue(value, total)}%)
      </strong>
    </div>
  )
}

function BugRiskOverviewCard({ bug }: { bug: NormalizedDailyMetrics['bug'] }) {
  if (!bug.collected) return (
    <Card className="sprint-overview-card sprint-overview-card-rich rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-none sprint-dashboard-panel min-h-0">
      <div className="sprint-dashboard-card-head mb-1.5 flex flex-wrap items-start justify-between gap-3"><Title level={4} className="m-0 text-[15px] font-semibold leading-6">缺陷风险画像</Title></div>
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="缺陷数据未采集，暂不统计" />
    </Card>
  )
  const chartTheme = sprintChartTheme
  const chartData = [
    { name: '已解决', value: bug.resolved, color: chartTheme.positive },
    { name: '已关闭', value: bug.closed, color: chartTheme.total },
    { name: '未解决', value: bug.unresolved, color: chartTheme.negative },
  ].filter((item) => item.value > 0)
  const metricData = [
    { name: '已解决', value: bug.resolved, color: chartTheme.positive },
    { name: '已关闭', value: bug.closed, color: chartTheme.total },
    { name: '未解决', value: bug.unresolved, color: chartTheme.negative },
  ]
  const severityData = [
    { name: '致命', value: bug.fatal, color: 'var(--chart-negative)' },
    { name: '严重', value: bug.severe, color: 'var(--chart-pending)' },
    { name: '一般', value: bug.normal, color: 'var(--chart-severity-normal)' },
    { name: '提示', value: bug.hint, color: 'var(--chart-severity-hint)' },
  ]

  return (
    <Card className="sprint-overview-card sprint-overview-card-rich rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-none sprint-dashboard-panel min-h-0">
      <div className="sprint-dashboard-card-head mb-1.5 flex flex-wrap items-start justify-between gap-3">
        <Title level={4} className="m-0 text-[15px] font-semibold leading-6">缺陷风险画像</Title>
      </div>
      <div className="sprint-dashboard-risk-layout grid flex-auto grid-cols-[minmax(240px,1fr)_minmax(0,1fr)] items-stretch gap-4 max-[600.01px]:grid-cols-1">
        <div className="sprint-dashboard-risk-summary flex min-w-0 flex-col">
          <Text className="sprint-overview-card-label text-[13px] leading-5 text-[var(--app-text-axis)]">Bug 总数</Text>
          <Title level={3} className="sprint-overview-card-value mt-[3px] text-[22px] leading-[28px]">
            {bug.total}
          </Title>
          <div className="sprint-overview-donut-layout grid flex-none grid-cols-[100px_minmax(0,1fr)] items-center gap-2.5 max-[768.01px]:grid-cols-1 max-[768.01px]:justify-items-center">
            <div className="sprint-overview-mini-chart relative h-[100px] w-[100px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={chartData.length ? chartData : [{ name: '暂无数据', value: 1, color: chartTheme.empty }]} dataKey="value" innerRadius="62%" outerRadius="86%" paddingAngle={4}>
                    {(chartData.length ? chartData : [{ color: chartTheme.empty }]).map((item) => (
                      <Cell key={item.color} fill={item.color} />
                    ))}
                  </Pie>
                  <SprintChartTooltip chartTheme={chartTheme} />
                </PieChart>
              </ResponsiveContainer>
              <div className="sprint-overview-donut-center pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-[20px] font-bold leading-8 text-[var(--app-shell-text)]">{bug.total}</div>
            </div>
            <div className="sprint-overview-chart-metrics grid min-w-0 grid-cols-1 gap-3.5 [&>span]:flex [&>span]:min-w-0 [&>span]:items-center [&>span]:justify-between [&>span]:gap-1.5 [&>span]:whitespace-nowrap [&>span]:text-[12px] [&>span]:leading-[22px] [&>span]:text-[var(--app-text-label)] [&_strong]:ml-auto [&_strong]:text-[12px] [&_strong]:leading-6 [&_strong]:text-[var(--app-shell-text)]">
              {metricData.map((item) => (
                <span key={item.name} style={{ '--metric-color': item.color } as CSSProperties}>
                  {item.name}
                  <strong>
                    {item.value} ({percentValue(item.value, bug.total)}%)
                  </strong>
                </span>
              ))}
            </div>
          </div>
        </div>
        <div className="sprint-dashboard-severity-list flex min-w-0 flex-col justify-center gap-3 border-l border-[var(--app-frame-divider)] pl-4 max-[1200.01px]:border-l-0 max-[1200.01px]:pl-0">
          <Text className="sprint-overview-card-label text-[13px] leading-5 text-[var(--app-text-axis)]">严重程度分布</Text>
          {severityData.map((item) => (
            <SeverityLine key={item.name} label={item.name} value={item.value} total={bug.total} color={item.color} />
          ))}
        </div>
      </div>
    </Card>
  )
}

type NormalizedDailyMetrics = ReturnType<typeof normalizeDailyMetrics>

function TrendLineChart({ data }: { data: NormalizedDailyMetrics[] }) {
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

function TrendBarChart({ data }: { data: NormalizedDailyMetrics[] }) {
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

type TestReportGenerateFormValues = {
  connectionId: string
  instruction?: string
}

function getRunStatusMeta(status?: TestReportGenerateRun['status']) {
  const value = status ?? 'unknown'
  const meta: Record<string, { label: string; color: string }> = {
    pending: { label: '待执行', color: 'gold' },
    claimed: { label: '已领取', color: 'cyan' },
    running: { label: '执行中', color: 'green' },
    waiting_review: { label: '待审核', color: 'gold' },
    success: { label: '成功', color: 'success' },
    failed: { label: '失败', color: 'error' },
    error: { label: '异常', color: 'volcano' },
    canceled: { label: '已取消', color: 'default' },
  }

  return { value, ...(meta[value] ?? { label: value, color: 'default' }) }
}

function isTestReportRunGenerating(run?: TestReportGenerateRun) {
  return ['pending', 'queued', 'claimed', 'running', 'waiting_review'].includes(getRunStatusMeta(run?.status).value)
}

function getRunId(run?: TestReportGenerateRun) {
  return run?.runId ?? run?.run_id ?? ''
}

function getRunReportMarkdown(run?: TestReportGenerateRun) {
  return run?.resultYaml ?? run?.result_yaml ?? ''
}

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean)
  return parts.map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>
    }
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>
    }
    return <span key={`${part}-${index}`}>{part}</span>
  })
}

function parseMarkdownTable(lines: string[]) {
  if (lines.length < 2 || !/^\s*\|?[\s:-]+\|[\s|:-]*$/.test(lines[1])) return null

  const toCells = (line: string) =>
    line
      .trim()
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((cell) => cell.trim())

  const headers = toCells(lines[0])
  const rows = lines.slice(2).map(toCells)
  return { headers, rows }
}

function renderMarkdownBlocks(markdown: string) {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      index += 1
      continue
    }

    if (line.trim().startsWith('```')) {
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      index += 1
      blocks.push(
        <pre key={`code-${index}`}>
          <code>{codeLines.join('\n')}</code>
        </pre>,
      )
      continue
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      const content = renderInlineMarkdown(heading[2])
      if (level === 1) blocks.push(<h1 key={`heading-${index}`}>{content}</h1>)
      else if (level === 2) blocks.push(<h2 key={`heading-${index}`}>{content}</h2>)
      else if (level === 3) blocks.push(<h3 key={`heading-${index}`}>{content}</h3>)
      else blocks.push(<h4 key={`heading-${index}`}>{content}</h4>)
      index += 1
      continue
    }

    if (line.includes('|') && index + 1 < lines.length && lines[index + 1].includes('|')) {
      const tableLines: string[] = []
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        tableLines.push(lines[index])
        index += 1
      }
      const table = parseMarkdownTable(tableLines)
      if (table) {
        blocks.push(
          <div className="sprint-report-markdown-table-wrap my-3 overflow-auto rounded-[8px] border border-[var(--app-document-table-border)]" key={`table-${index}`}>
            <table>
              <thead>
                <tr>
                  {table.headers.map((header, headerIndex) => (
                    <th key={`${header}-${headerIndex}`}>{renderInlineMarkdown(header)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, rowIndex) => (
                  <tr key={`row-${rowIndex}`}>
                    {row.map((cell, cellIndex) => (
                      <td key={`${cell}-${cellIndex}`}>{renderInlineMarkdown(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        )
        continue
      }
      blocks.push(<p key={`paragraph-${index}`}>{renderInlineMarkdown(tableLines.join(' '))}</p>)
      continue
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ''))
        index += 1
      }
      blocks.push(
        <ul key={`list-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>,
      )
      continue
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, ''))
        index += 1
      }
      blocks.push(
        <ol key={`ordered-list-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ol>,
      )
      continue
    }

    if (/^\s*>\s+/.test(line)) {
      const quotes: string[] = []
      while (index < lines.length && /^\s*>\s+/.test(lines[index])) {
        quotes.push(lines[index].replace(/^\s*>\s+/, ''))
        index += 1
      }
      blocks.push(<blockquote key={`quote-${index}`}>{renderInlineMarkdown(quotes.join(' '))}</blockquote>)
      continue
    }

    const paragraph: string[] = []
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^(#{1,4})\s+/.test(lines[index]) &&
      !lines[index].trim().startsWith('```') &&
      !/^\s*[-*]\s+/.test(lines[index]) &&
      !/^\s*\d+\.\s+/.test(lines[index]) &&
      !/^\s*>\s+/.test(lines[index])
    ) {
      paragraph.push(lines[index])
      index += 1
    }
    blocks.push(<p key={`paragraph-${index}`}>{renderInlineMarkdown(paragraph.join(' '))}</p>)
  }

  return blocks
}

function TestReportMarkdownModal({
  open,
  run,
  loading,
  error,
  downloading,
  onClose,
  onDownloadPdf,
}: {
  open: boolean
  run?: TestReportGenerateRun
  loading?: boolean
  error?: unknown
  downloading?: boolean
  onClose: () => void
  onDownloadPdf: (run: TestReportGenerateRun) => void
}) {
  const markdown = getRunReportMarkdown(run)
  const canDownload = Boolean(run && getRunStatusMeta(run.status).value === 'success' && getRunId(run) && markdown)

  return (
    <Modal
      title="测试报告"
      open={open}
      onCancel={onClose}
      width={960}
      footer={
        <Space>
          <Button onClick={onClose}>关闭</Button>
          <ActionButton
            type="primary"
            operation="download"
            disabled={!canDownload}
            loading={downloading}
            onClick={() => {
              if (run) onDownloadPdf(run)
            }}
          >
            导出 PDF
          </ActionButton>
        </Space>
      }
      destroyOnHidden={false}
      className={`sprint-report-markdown-modal ${sprintOverviewStyles.root}`}
    >
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} style={{ marginBottom: 16 }} /> : null}
      {loading ? (
        <div className="sprint-report-markdown-state flex min-h-[220px] items-center justify-center">
          <Spin />
        </div>
      ) : markdown ? (
        <article className="sprint-report-markdown text-[14px] leading-[1.72] text-[var(--app-document-text)] [&_blockquote]:my-3 [&_blockquote]:border-l-[3px] [&_blockquote]:border-[var(--app-accent)] [&_blockquote]:bg-[var(--app-document-quote-bg)] [&_blockquote]:px-3.5 [&_blockquote]:py-2.5 [&_blockquote]:text-[var(--app-document-quote-text)] [&_code]:rounded-[5px] [&_code]:bg-[var(--app-document-code-bg)] [&_code]:px-[5px] [&_code]:py-0.5 [&_code]:text-[12px] [&_code]:text-[var(--app-document-code-text)] [&_h1]:mb-2.5 [&_h1]:mt-5 [&_h1]:text-[24px] [&_h1]:font-[750] [&_h1]:text-[var(--app-document-heading)] [&_h2]:mb-2.5 [&_h2]:mt-5 [&_h2]:text-[20px] [&_h2]:font-[750] [&_h2]:text-[var(--app-document-heading)] [&_h3]:mb-2.5 [&_h3]:mt-5 [&_h3]:text-[17px] [&_h3]:font-[750] [&_h3]:text-[var(--app-document-heading)] [&_h4]:mb-2.5 [&_h4]:mt-5 [&_h4]:text-[15px] [&_h4]:font-[750] [&_h4]:text-[var(--app-document-heading)] [&_li]:my-1 [&_ol]:my-2 [&_ol]:mb-3 [&_ol]:pl-6 [&_p]:my-2 [&_pre]:my-3 [&_pre]:overflow-auto [&_pre]:rounded-[8px] [&_pre]:bg-[var(--app-document-code-block-bg)] [&_pre]:p-3 [&_pre_code]:whitespace-pre [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-[var(--app-document-code-block-text)] [&_table]:w-full [&_table]:min-w-[560px] [&_table]:border-collapse [&_td]:border-b [&_td]:border-[var(--app-frame-divider)] [&_td]:px-3 [&_td]:py-2.5 [&_td]:text-left [&_td]:align-top [&_th]:border-b [&_th]:border-[var(--app-frame-divider)] [&_th]:bg-[var(--app-document-table-heading-bg)] [&_th]:px-3 [&_th]:py-2.5 [&_th]:text-left [&_th]:align-top [&_th]:font-bold [&_th]:text-[var(--app-text-strong)] [&_ul]:my-2 [&_ul]:mb-3 [&_ul]:pl-6">{renderMarkdownBlocks(markdown)}</article>
      ) : (
        <Empty description="暂无可查看的报告内容" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </Modal>
  )
}

function TestReportGenerateDrawer({
  open,
  projectId,
  form,
  snapshotDate,
  loading,
  error,
  onClose,
  onFinish,
}: {
  open: boolean
  projectId?: string
  form: FormInstance<TestReportGenerateFormValues>
  snapshotDate: string
  loading?: boolean
  error?: unknown
  onClose: () => void
  onFinish: (values: TestReportGenerateFormValues) => void
}) {
  const navigate = useNavigate()
  const connectionsQuery = useQuery({
    queryKey: ['llmConnections', projectId, 'testReportGenerate'],
    queryFn: () => api.getLlmConnections(projectId!),
    enabled: open && Boolean(projectId),
  })
  const activeConnections = useMemo(
    () => listItems(connectionsQuery.data).filter((connection) => connection.status === 'active'),
    [connectionsQuery.data],
  )

  function handleGoToConfig() {
    onClose()
    navigate('/base-services?tab=llm')
  }

  return (
    <Drawer
      title="生成测试报告"
      open={open}
      onClose={onClose}
      width={520}
      destroyOnHidden
      rootClassName={sprintOverviewStyles.root}
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <ProjectActionButton action="execute" type="primary" loading={loading} disabled={activeConnections.length === 0} onClick={() => form.submit()}>
            确认生成
          </ProjectActionButton>
        </Space>
      }
    >
      {connectionsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(connectionsQuery.error)} style={{ marginBottom: 16 }} /> : null}
      {!projectId ? <Alert showIcon type="info" title="缺少项目信息，无法加载 LLM 连接" style={{ marginBottom: 16 }} /> : null}
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} style={{ marginBottom: 16 }} /> : null}
      <Form form={form} layout="vertical" requiredMark={false} onFinish={onFinish}>
        <Form.Item label="快照日期">
          <Input value={snapshotDate} readOnly />
        </Form.Item>
        <Form.Item name="connectionId" label="LLM 连接" rules={[{ required: true, message: '请选择 LLM 连接' }]}>
          <Select
            loading={connectionsQuery.isLoading}
            placeholder="请选择用于生成报告的 LLM 连接"
            options={activeConnections.map((connection) => ({
              value: connection.connectionId,
              label: connection.modelId ? `${connection.name} (${connection.modelId})` : connection.name,
            }))}
            notFoundContent={
              connectionsQuery.isLoading ? <Spin size="small" /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可用的 LLM 连接" />
            }
          />
        </Form.Item>
        {activeConnections.length === 0 && !connectionsQuery.isLoading && !connectionsQuery.error ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可用的 LLM 连接" className="sprint-report-drawer-empty m-0 mb-4">
            <Button type="primary" onClick={handleGoToConfig}>
              去配置
            </Button>
          </Empty>
        ) : null}
        <Form.Item name="instruction" label="生成说明">
          <Input.TextArea maxLength={1000} rows={5} placeholder="可选，补充本次报告生成要求" showCount />
        </Form.Item>
      </Form>
    </Drawer>
  )
}

function useQueryErrorToast(error: unknown, key: string) {
  useEffect(() => {
    if (error) message.error({ key, content: getErrorMessage(error) })
  }, [error, key])
}

export function SprintDetailPage() {
  const { projectId: routeProjectId = '', sprintId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [reportDrawerOpen, setReportDrawerOpen] = useState(false)
  const [reportHistoryOpen, setReportHistoryOpen] = useState(false)
  const [reportModalRunId, setReportModalRunId] = useState('')
  const [historyDateRange, setHistoryDateRange] = useState<[Dayjs, Dayjs]>(() => [dayjs().subtract(6, 'day'), dayjs()])
  const [reportForm] = Form.useForm<TestReportGenerateFormValues>()

  const sprintQuery = useQuery({
    queryKey: ['sprint', sprintId],
    queryFn: () => api.getSprint(sprintId),
    enabled: Boolean(sprintId),
  })
  const projectId = sprintQuery.data?.projectId || sprintQuery.data?.project_id || ''
  const projectMismatch = Boolean(routeProjectId && projectId && routeProjectId !== projectId)
  const projectScopeError = sprintQuery.error ?? (projectMismatch
    ? new Error('迭代所属项目与访问路径不一致')
    : sprintQuery.isSuccess && !projectId ? new Error('无法确认迭代所属项目') : undefined)
  const sprintForBoundaryRefresh = useMemo(() => (sprintQuery.data ? [sprintQuery.data] : []), [sprintQuery.data])
  useSprintBoundaryRefresh({
    sprints: sprintForBoundaryRefresh,
    enabled: Boolean(sprintId),
    refresh: sprintQuery.refetch,
  })
  const metricsRange = useMemo(() => {
    const [start, end] = historyDateRange
    const startDate = start.format('YYYY-MM-DD')
    const endDate = end.format('YYYY-MM-DD')
    return { startDate, endDate }
  }, [historyDateRange])
  const todayDate = useLocalDate()
  const currentMetricsQuery = useQuery({
    queryKey: ['sprintDailyMetricsByDate', sprintId, todayDate],
    queryFn: () => api.getSprintDailyMetricsByDate(sprintId, todayDate),
    enabled: Boolean(sprintId && projectId && !projectScopeError),
  })
  const historyMetricsQuery = useQuery({
    queryKey: ['sprintDailyMetrics', sprintId, metricsRange.startDate, metricsRange.endDate],
    queryFn: () => api.getSprintDailyMetrics(sprintId, metricsRange),
    enabled: Boolean(sprintId && projectId && !projectScopeError),
  })

  const generateMetricsMutation = useMutation({
    mutationFn: async () => {
      return api.generateSprintDailyMetrics(sprintId, todayDate)
    },
    onSuccess: () => {
      message.success('已生成最新统计快照')
      queryClient.invalidateQueries({ queryKey: ['sprintDailyMetricsByDate', sprintId, todayDate] })
      queryClient.invalidateQueries({ queryKey: ['sprintDailyMetrics', sprintId] })
    },
    onError: (error) => {
      const content = getErrorMessage(error)
      if (content === '已取消操作' || content === '页面已关闭') return
      message.error(content)
    },
  })

  const sprintName = sprintQuery.data?.name ?? '迭代详情'
  const latestMetrics = normalizeDailyMetrics(currentMetricsQuery.data)
  const historyMetrics = listItems(historyMetricsQuery.data).map(normalizeDailyMetrics)
  const reportRunsQuery = useQuery({
    queryKey: ['testReportGenerateRuns', projectId, sprintId],
    queryFn: () => api.getTestReportGenerateRuns(projectId, { sprintId }),
    enabled: Boolean(projectId && sprintId && !projectScopeError),
  })
  useQueryErrorToast(currentMetricsQuery.error, `sprint-metrics-${sprintId}`)
  useQueryErrorToast(historyMetricsQuery.error, `sprint-history-${sprintId}`)
  useQueryErrorToast(reportRunsQuery.error, `sprint-reports-${sprintId}`)

  const reportRunDetailQuery = useQuery({
    queryKey: ['testReportGenerateRun', reportModalRunId],
    queryFn: () => api.getTestReportGenerateRun(reportModalRunId),
    enabled: Boolean(reportModalRunId),
  })

  const pendingReportRequest = usePendingRequestId()
  const createReportRunMutation = useMutation({
    mutationFn: (values: TestReportGenerateFormValues) => {
      if (!projectId) throw new Error('缺少项目信息，无法生成测试报告')
      const input = {
        sprintId,
        snapshotDate: todayDate,
        connectionId: values.connectionId,
        instruction: values.instruction?.trim() || undefined,
      }
      const requestId = pendingReportRequest.forInput(JSON.stringify({ projectId, ...input }))
      return api.createTestReportGenerateRun(projectId, { ...input, requestId })
    },
    onSuccess: () => {
      pendingReportRequest.clear()
      message.success('报告生成已开始')
      setReportDrawerOpen(false)
      reportForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['testReportGenerateRuns', projectId, sprintId] })
    },
  })
  const downloadReportPdfMutation = useMutation({
    mutationFn: (run: TestReportGenerateRun) => {
      const runId = getRunId(run)
      if (!runId) throw new Error('缺少报告运行 ID，无法导出 PDF')
      return api.downloadTestReportGenerateRunPdf(runId)
    },
    onSuccess: (response, run) => {
      const runId = getRunId(run)
      saveBlob(response.blob, response.filename || `test-report-${runId}.pdf`)
    },
  })

  const reportRuns = listItems(reportRunsQuery.data)
  const latestReportRun = reportRuns[0]
  const latestSuccessfulReport = reportRuns.find(run => getRunStatusMeta(run.status).value === 'success' && Boolean(getRunId(run)))
  const isReportGenerating = createReportRunMutation.isPending || isTestReportRunGenerating(latestReportRun)
  const canViewLatestReport =
    Boolean(latestSuccessfulReport)

  function closeReportDrawer() {
    setReportDrawerOpen(false)
    reportForm.resetFields()
  }

  function handleOpenReportDrawer() {
    if (isReportGenerating) {
      message.warning('测试报告正在生成中，请稍后再试')
      return
    }
    if (currentMetricsQuery.isLoading) {
      message.warning('统计快照加载中，请稍后再试')
      return
    }
    if (currentMetricsQuery.error || !currentMetricsQuery.data) {
      message.warning('请先更新数据后再生成测试报告')
      return
    }
    setReportDrawerOpen(true)
  }

  function handleCreateReportRun(values: TestReportGenerateFormValues) {
    createReportRunMutation.mutate(values)
  }

  function handleViewReport(run: TestReportGenerateRun) {
    const runId = getRunId(run)
    if (!runId) {
      message.warning('缺少报告运行 ID，无法查看报告')
      return
    }
    setReportModalRunId(runId)
  }

  function closeReportModal() {
    setReportModalRunId('')
  }

  function handleDownloadReportPdf(run: TestReportGenerateRun) {
    if (getRunStatusMeta(run.status).value !== 'success' || !getRunReportMarkdown(run)) {
      message.warning('报告未生成完成，暂不能导出 PDF')
      return
    }
    downloadReportPdfMutation.mutate(run)
  }

  return (<ProjectAccessScope projectId={projectId} resourceError={projectScopeError}>{(
    <div className={`workbench-page sprint-overview-page tp-surface overflow-hidden p-[var(--app-page-gutter)] ${sprintOverviewStyles.root} ${sprintOverviewStyles.root}`}>
      {sprintQuery.isLoading ? (
        <div className={`workbench-tabs ${workbenchTabsCompactClass}`}>
          <section className="workbench-panel workbench-panel-flat sprint-overview-panel sprint-overview-panel-unified sprint-overview-state-panel overflow-hidden">
            <Spin />
          </section>
        </div>
      ) : sprintQuery.data ? (
        <section className="tp-board tp-list-panel sprint-overview-frame min-h-0 [&>.workbench-tabs]:p-0">
          <section className="tp-list-toolbar">
            <div className="sprint-overview-toolbar-summary-row flex w-full flex-wrap items-center justify-between gap-3 max-[1200.01px]:items-start">
              <div className="sprint-overview-toolbar-main flex min-w-0 flex-none flex-col items-start gap-2">
                <div className="sprint-overview-hero-title-row flex w-auto items-center justify-start gap-4 max-[1200.01px]:w-full max-narrow:w-full max-narrow:flex-col max-narrow:items-start max-narrow:gap-2.5 [&>.ant-space]:flex [&>.ant-space]:w-auto [&>.ant-space]:justify-start max-[1200.01px]:[&>.ant-space]:w-full">
                  <Space size={8} wrap>
                    <Tooltip title="返回项目总览">
                      <Button
                        type="text"
                        shape="circle"
                        className="action-btn-read"
                        icon={<ArrowLeftOutlined />}
                        aria-label="返回项目总览"
                        onClick={() => goBackOrFallback(navigate, '/projects')}
                      />
                    </Tooltip>
                    <h1 className="tp-list-title">
                      {sprintName}
                    </h1>
                    <div className="sprint-overview-hero-status inline-flex items-center"><Tag color={sprintQuery.data.status === 'completed' ? 'success' : sprintQuery.data.status === 'running' ? 'processing' : 'default'}>{{ planned: '未开始', running: '进行中', completed: '已完成' }[sprintQuery.data.status ?? ''] ?? sprintQuery.data.status ?? '未知状态'}</Tag></div>
                  </Space>
                </div>
              </div>
              <div className="sprint-overview-hero-summary ml-auto flex flex-wrap items-center justify-end gap-2 max-[1200.01px]:justify-start max-[768.01px]:ml-0 max-[768.01px]:w-full">
                <Text type="secondary">统计日期：{currentMetricsQuery.data ? snapshotDate(currentMetricsQuery.data) : '今日暂无快照'}</Text>
                <SummaryMetric label="总用例数" value={latestMetrics.totalCases} />
                <SummaryMetric label="Bug 总数" value={latestMetrics.bug.collected ? latestMetrics.bug.total : '—'} />

                <ProjectActionButton action="execute"
                  className="action-btn-read"
                  operation="refresh"
                  loading={generateMetricsMutation.isPending}
                  onClick={() => generateMetricsMutation.mutate()}
                >
                  更新数据
                </ProjectActionButton>
                <Button onClick={() => setReportHistoryOpen(true)}>报告历史</Button>
                <Tooltip title={canViewLatestReport ? '查看最近一次成功报告' : '暂无可查看的成功报告'}>
                  <Button
                    icon={<FileTextOutlined />}
                    disabled={!canViewLatestReport}
                    onClick={() => {
                      if (latestSuccessfulReport) handleViewReport(latestSuccessfulReport)
                    }}
                  >
                    查看报告
                  </Button>
                </Tooltip>
                <ProjectActionButton action="execute"
                  type="primary"
                  icon={<FileTextOutlined />}
                  loading={isReportGenerating}
                  disabled={isReportGenerating}
                  onClick={handleOpenReportDrawer}
                >
                  {isReportGenerating ? '生成报告中' : '生成测试报告'}
                </ProjectActionButton>
              </div>
            </div>
          </section>

          <div className={`workbench-tabs ${workbenchTabsCompactClass}`}>

            <section className="workbench-panel workbench-panel-flat sprint-overview-panel sprint-overview-panel-unified overflow-hidden">
              <div className="sprint-overview-panel-body flex min-h-0 flex-1 flex-col overflow-auto p-4">
                <div className="sprint-overview-layout grid min-h-0 grid-rows-[auto] content-start gap-4 max-[1200.01px]:flex max-[1200.01px]:flex-col min-[1281px]:min-h-0 min-[1281px]:flex-auto min-[1281px]:grid-rows-[auto_minmax(260px,1fr)_minmax(0,1.18fr)] min-[1281px]:content-stretch">
                  <SprintHealthSummary metrics={latestMetrics} />

                  <div className="sprint-dashboard-main-grid grid grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] gap-4 max-[1280.01px]:grid-cols-1">
                    <TestExecutionOverviewCard metrics={latestMetrics} />
                    <BugRiskOverviewCard bug={latestMetrics.bug} />
                  </div>

                  <div className="sprint-overview-section sprint-dashboard-trend-section flex flex-col gap-2 min-[1281px]:min-h-0">
                    {historyMetricsQuery.isLoading ? (
                      <Card className="sprint-overview-card sprint-overview-card-rich rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-none sprint-overview-history-state grid min-h-[120px] place-items-center">
                        <Spin />
                      </Card>
                    ) : historyMetrics.length === 0 ? (
                      <Card className="sprint-overview-card sprint-overview-card-rich rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-none min-h-0">
                        <Empty description="暂无历史快照" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      </Card>
                    ) : (
                      <Card className="sprint-overview-card sprint-overview-card-rich rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-none sprint-dashboard-trend-card min-h-0">
                        <div className="sprint-dashboard-card-head mb-1.5 flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <Title level={4} className="m-0 text-[15px] font-semibold leading-6">趋势历史</Title>
                        </div>
                          <RangePicker
                            allowClear={false}
                            className="sprint-dashboard-range-picker w-[244px] flex-none"
                            format="YYYY-MM-DD"
                            value={historyDateRange}
                            onChange={(dates) => {
                              if (dates?.[0] && dates[1]) {
                                setHistoryDateRange([dates[0], dates[1]])
                              }
                            }}
                          />
                        </div>
                        <div className="sprint-overview-trend-grid grid min-h-0 flex-auto grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] gap-3 max-[1200.01px]:grid-cols-1">
                          <div className="sprint-dashboard-trend-pane flex min-h-0 min-w-0 flex-col [&+&]:border-l [&+&]:border-[var(--app-frame-divider)] [&+&]:pl-3 max-[1200.01px]:[&+&]:border-l-0 max-[1200.01px]:[&+&]:pl-0">
                          <div className="sprint-overview-chart-card-head mb-1 flex items-start justify-between gap-4">
                            <div>
                              <Text className="sprint-overview-card-label text-[13px] leading-5 text-[var(--app-text-axis)]">用例总数趋势</Text>
                              <Title level={4} className="sprint-overview-card-subtitle mt-1 text-[18px] leading-6">
                                {historyMetrics[historyMetrics.length - 1]?.totalCases ?? 0}
                              </Title>
                            </div>
                            <Tag className="sprint-overview-accent-tag rounded-full border-0 bg-[var(--app-badge-bg)] px-2.5 text-[var(--app-badge-text)] [margin-inline-end:0]">Cases</Tag>
                          </div>
                          <TrendLineChart data={historyMetrics} />
                          </div>
                          <div className="sprint-dashboard-trend-pane flex min-h-0 min-w-0 flex-col [&+&]:border-l [&+&]:border-[var(--app-frame-divider)] [&+&]:pl-3 max-[1200.01px]:[&+&]:border-l-0 max-[1200.01px]:[&+&]:pl-0">
                          <div className="sprint-overview-chart-card-head mb-1 flex items-start justify-between gap-4">
                            <div>
                              <Text className="sprint-overview-card-label text-[13px] leading-5 text-[var(--app-text-axis)]">Bug 解决趋势</Text>
                              <Title level={4} className="sprint-overview-card-subtitle mt-1 text-[18px] leading-6">
                                {historyMetrics[historyMetrics.length - 1]?.bug.collected ? historyMetrics[historyMetrics.length - 1]?.bug.total : '—'}
                              </Title>
                            </div>
                            <Tag className="sprint-overview-accent-tag rounded-full border-0 bg-[var(--app-badge-bg)] px-2.5 text-[var(--app-badge-text)] [margin-inline-end:0]">Bugs</Tag>
                          </div>
                          <TrendBarChart data={historyMetrics} />
                          </div>
                        </div>
                      </Card>
                    )}
                  </div>
                </div>
              </div>
            </section>
          </div>
        </section>
      ) : (
        <div className={`workbench-tabs ${workbenchTabsCompactClass}`}>
          {sprintQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintQuery.error)} /> : null}
          <section className="workbench-panel workbench-panel-flat sprint-overview-panel sprint-overview-panel-unified sprint-overview-state-panel overflow-hidden">
            <Empty description="未找到迭代信息" />
          </section>
        </div>
      )}
      <TestReportGenerateDrawer
        open={reportDrawerOpen}
        projectId={projectId}
        form={reportForm}
        snapshotDate={todayDate}
        loading={createReportRunMutation.isPending}
        error={createReportRunMutation.error}
        onClose={closeReportDrawer}
        onFinish={handleCreateReportRun}
      />
      <TestReportHistoryDrawer key={`${projectId}:${sprintId}`} open={reportHistoryOpen} projectId={projectId} sprintId={sprintId}
        onClose={() => setReportHistoryOpen(false)} onView={run => { setReportHistoryOpen(false); handleViewReport(run) }} />
      <TestReportMarkdownModal
        open={Boolean(reportModalRunId)}
        run={reportRunDetailQuery.data}
        loading={reportRunDetailQuery.isLoading}
        error={reportRunDetailQuery.error ?? downloadReportPdfMutation.error}
        downloading={downloadReportPdfMutation.isPending}
        onClose={closeReportModal}
        onDownloadPdf={handleDownloadReportPdf}
      />
    </div>
  )}</ProjectAccessScope>)
}
