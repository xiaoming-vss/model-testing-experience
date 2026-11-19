import { ArrowLeftOutlined, FileTextOutlined } from '@ant-design/icons'
import { Button, Space, Tag, Tooltip, Typography } from 'antd'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { goBackOrFallback } from '@/shared/utils/backNavigation'
import { SummaryMetric } from './SprintDashboardCards'
import { snapshotDate } from '../utils/sprintMetrics'
import type { SprintDetailPageModel } from '../hooks/useSprintDetailPage'

const { Text } = Typography

export function SprintOverviewToolbar({ page }: { page: SprintDetailPageModel }) {
  const {
    navigate,
    sprintQuery,
    sprintName,
    currentMetricsQuery,
    latestMetrics,
    generateMetricsMutation,
    setReportHistoryOpen,
    canViewLatestReport,
    latestSuccessfulReport,
    handleViewReport,
    isReportGenerating,
    handleOpenReportDrawer,
  } = page

  return (
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
              <div className="sprint-overview-hero-status inline-flex items-center"><Tag color={sprintQuery.data?.status === 'completed' ? 'success' : sprintQuery.data?.status === 'running' ? 'processing' : 'default'}>{({ planned: '未开始', running: '进行中', completed: '已完成' } as Record<string, string>)[sprintQuery.data?.status ?? ''] ?? sprintQuery.data?.status ?? '未知状态'}</Tag></div>
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
  )
}
