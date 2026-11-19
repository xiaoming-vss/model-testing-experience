import {
  AppstoreOutlined,
  CodeOutlined,
  DesktopOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import { Card, Empty, Tooltip, Typography } from 'antd'
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'
import type { CSSProperties, ReactNode } from 'react'
import { SprintChartTooltip } from './SprintChartPrimitives'
import { sprintChartTheme } from '../utils/sprintChartTheme'
import { sprintCardHeadClass, sprintCardLabelClass, sprintCardTitleClass } from '../utils/sprintSurfaceClasses'
import { percentValue, type NormalizedDailyMetrics } from '../utils/sprintMetrics'

const { Text, Title } = Typography

export function SummaryMetric({ label, value, icon }: { label: string; value: number | string; icon?: ReactNode }) {
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

export function SprintHealthSummary({ metrics }: { metrics: NormalizedDailyMetrics }) {
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
            <Title level={4} className={sprintCardTitleClass}>迭代健康摘要</Title>
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

export function TestExecutionOverviewCard({ metrics }: { metrics: NormalizedDailyMetrics }) {
  const rows = [
    { key: 'functional' as const, title: '功能测试', stats: metrics.functional },
    { key: 'api' as const, title: 'API 测试', stats: metrics.api },
    { key: 'ui' as const, title: 'UI 测试', stats: metrics.ui },
  ]

  return (
    <Card className="sprint-overview-card sprint-overview-card-rich rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-none sprint-dashboard-panel min-h-0 max-[768.01px]:overflow-x-auto">
      <div className={sprintCardHeadClass}>
        <Title level={4} className={sprintCardTitleClass}>测试执行概览</Title>
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

export function BugRiskOverviewCard({ bug }: { bug: NormalizedDailyMetrics['bug'] }) {
  if (!bug.collected) return (
    <Card className="sprint-overview-card sprint-overview-card-rich rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-none sprint-dashboard-panel min-h-0">
      <div className={sprintCardHeadClass}><Title level={4} className={sprintCardTitleClass}>缺陷风险画像</Title></div>
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
      <div className={sprintCardHeadClass}>
        <Title level={4} className={sprintCardTitleClass}>缺陷风险画像</Title>
      </div>
      <div className="sprint-dashboard-risk-layout grid flex-auto grid-cols-[minmax(240px,1fr)_minmax(0,1fr)] items-stretch gap-4 max-[600.01px]:grid-cols-1">
        <div className="sprint-dashboard-risk-summary flex min-w-0 flex-col">
          <Text className={sprintCardLabelClass}>Bug 总数</Text>
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
          <Text className={sprintCardLabelClass}>严重程度分布</Text>
          {severityData.map((item) => (
            <SeverityLine key={item.name} label={item.name} value={item.value} total={bug.total} color={item.color} />
          ))}
        </div>
      </div>
    </Card>
  )
}
