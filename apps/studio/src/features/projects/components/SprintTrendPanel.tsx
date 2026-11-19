import { Card, DatePicker, Empty, Spin, Tag, Typography } from 'antd'
import { TrendBarChart, TrendLineChart } from './SprintTrendCharts'
import { sprintCardHeadClass, sprintCardLabelClass, sprintCardTitleClass } from '../utils/sprintSurfaceClasses'
import type { SprintDetailPageModel } from '../hooks/useSprintDetailPage'

const { Text, Title } = Typography
const { RangePicker } = DatePicker

export function SprintTrendPanel({ page }: { page: SprintDetailPageModel }) {
  const {
    historyMetricsQuery,
    historyMetrics,
    historyDateRange,
    setHistoryDateRange,
  } = page

  return (
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
          <div className={sprintCardHeadClass}>
            <div>
              <Title level={4} className={sprintCardTitleClass}>趋势历史</Title>
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
                  <Text className={sprintCardLabelClass}>用例总数趋势</Text>
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
                  <Text className={sprintCardLabelClass}>Bug 解决趋势</Text>
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
  )
}
