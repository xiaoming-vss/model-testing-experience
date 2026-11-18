import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Progress, Select, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { ListPagination } from '@/shared/components/ListPagination'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { api, listItems, listTotal } from '@/services/api'
import { formatTime, getErrorMessage } from '@/utils/format'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { tableFooterClass } from '@/shared/utils/surfaceClasses'
import type { PerfRunStatus, PerfSuiteRunSummary } from '../types'
import {
  PERF_OUTCOME_LABELS,
  PERF_STATUS_LABELS,
  formatPerfDuration,
  isPerfRunActive,
  perfOutcomeColor,
  perfStatusColor,
} from '../utils/perf'

const { Text } = Typography

export function PerformanceRunsPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { activeProjectId } = useActiveProject()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [suiteFilter, setSuiteFilter] = useState(searchParams.get('suiteId') ?? 'all')
  const [statusFilter, setStatusFilter] = useState<'all' | PerfRunStatus>('all')

  const suitesQuery = useQuery({
    queryKey: ['perfSuites', activeProjectId],
    queryFn: () => api.listPerfSuites(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const runsQuery = useQuery({
    queryKey: ['perfSuiteRuns', activeProjectId, suiteFilter, statusFilter, page, pageSize],
    queryFn: () => api.listPerfSuiteRuns(activeProjectId!, {
      suiteId: suiteFilter === 'all' ? undefined : suiteFilter,
      status: statusFilter === 'all' ? undefined : statusFilter,
      page,
      pageSize,
    }),
    enabled: Boolean(activeProjectId),
    refetchInterval: (query) => query.state.data?.items?.some((run) => isPerfRunActive(run.status)) ? 3000 : false,
  })
  const runs = listItems(runsQuery.data)
  const total = listTotal(runsQuery.data)

  useEffect(() => {
    setPage(1)
  }, [suiteFilter, statusFilter])

  useEffect(() => {
    const suiteId = searchParams.get('suiteId')
    if (suiteId) setSuiteFilter(suiteId)
  }, [searchParams])

  function progress(run: PerfSuiteRunSummary) {
    const settled = run.completedCount + run.failedCount + run.skippedCount
    if (!run.totalCount) return 0
    return Math.round((settled / run.totalCount) * 100)
  }

  const columns: TableProps<PerfSuiteRunSummary>['columns'] = [
    {
      title: '测试集 / 运行',
      dataIndex: 'suiteName',
      width: 280,
      render: (_, run) => <div className="min-w-0">
        <div className="truncate font-medium text-app-surface-text" title={run.suiteName}>{run.suiteName}</div>
        <div className="truncate font-mono text-[11px] text-app-surface-text-muted" title={run.suiteRunId}>{run.suiteRunId}</div>
      </div>,
    },
    { title: '环境', dataIndex: 'environmentName', width: 140, ellipsis: true },
    {
      title: '进度',
      width: 190,
      render: (_, run) => <div className="flex min-w-[150px] items-center gap-2">
        <Progress percent={progress(run)} size="small" showInfo={false} className="!mb-0 flex-1" />
        <span className="shrink-0 text-[11px] text-app-surface-text-muted">{run.completedCount + run.failedCount + run.skippedCount}/{run.totalCount}</span>
      </div>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (status: PerfRunStatus) => <Tag color={perfStatusColor(status)}>{PERF_STATUS_LABELS[status]}</Tag>,
    },
    {
      title: '结果',
      dataIndex: 'outcome',
      width: 120,
      render: (outcome: PerfSuiteRunSummary['outcome']) => outcome
        ? <Tag color={perfOutcomeColor(outcome)}>{PERF_OUTCOME_LABELS[outcome]}</Tag>
        : <Text type="secondary">未判定</Text>,
    },
    {
      title: '开始时间',
      dataIndex: 'startedAt',
      width: 170,
      render: (_, run) => formatTime(run.startedAt ?? run.createdAt),
    },
    {
      title: '耗时',
      dataIndex: 'durationMs',
      width: 100,
      render: (durationMs: number) => formatPerfDuration(durationMs),
    },
    {
      title: '',
      width: 72,
      render: (_, run) => <Button size="small" onClick={(event) => { event.stopPropagation(); navigate(`/performance/runs/${run.suiteRunId}`) }}>查看</Button>,
    },
  ]

  return <ProjectAccessScope projectId={activeProjectId ?? ''}>
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface api-test-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-panel-flat workbench-board-panel tp-board tp-list-panel">
          <div className="tp-list-toolbar flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 flex-wrap items-center gap-2.5">
              <Button type="text" icon={<ArrowLeftOutlined />} aria-label="返回性能测试" onClick={() => navigate('/testing?tab=perf')} />
              <h1 className="tp-list-title">运行记录</h1>
              <Select
                className="min-w-[190px]"
                value={suiteFilter}
                options={[
                  { value: 'all', label: '全部测试集' },
                  ...listItems(suitesQuery.data).map((suite) => ({ value: suite.suiteId, label: suite.name })),
                ]}
                onChange={setSuiteFilter}
                loading={suitesQuery.isLoading}
              />
              <Select
                className="min-w-[130px]"
                value={statusFilter}
                options={[
                  { value: 'all', label: '全部状态' },
                  ...Object.entries(PERF_STATUS_LABELS).map(([value, label]) => ({ value, label })),
                ]}
                onChange={setStatusFilter}
              />
            </div>
            <Space size={8}>
              <Text type="secondary">共 {total} 条运行 · 结果统一未判定</Text>
              <Button icon={<ReloadOutlined />} loading={runsQuery.isFetching} onClick={() => runsQuery.refetch()}>
                刷新
              </Button>
            </Space>
          </div>
          {runsQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(runsQuery.error)} className="m-4" /> : null}
          <Card styles={{ body: { padding: 0 } }} className="m-4 overflow-hidden">
            <Table<PerfSuiteRunSummary>
              rowKey="suiteRunId"
              size="middle"
              columns={columns}
              dataSource={runs}
              loading={runsQuery.isLoading}
              onRow={(run) => ({ onClick: () => navigate(`/performance/runs/${run.suiteRunId}`), className: 'cursor-pointer' })}
              pagination={false}
              locale={{ emptyText: <div className="py-12 text-center text-xs text-app-surface-text-muted">没有符合条件的运行记录。调整筛选条件或先运行一个测试集。</div> }}
            />
            <div className={`table-footer ${tableFooterClass}`}>
              <ListPagination
                loading={runsQuery.isFetching}
                current={page}
                pageSize={pageSize}
                total={total}
                onChange={(nextPage, nextPageSize) => {
                  setPage(nextPage)
                  setPageSize(nextPageSize)
                }}
              />
            </div>
          </Card>
        </section>
      </div>
    </div>
  </ProjectAccessScope>
}
