import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Select, Space, Table, Tag, Typography } from 'antd'
import { ListPagination } from '@/shared/components/ListPagination'
import type { TableProps } from 'antd'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { api, listItems, listTotal } from '@/services/api'
import { formatTime, getErrorMessage } from '@/utils/format'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import type { PerfRunStatus, PerfRunSummary } from '../types'
import {
  PERF_OUTCOME_LABELS,
  PERF_STATUS_LABELS,
  formatPerfDuration,
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
  const [caseFilter, setCaseFilter] = useState(searchParams.get('caseId') ?? 'all')
  const [statusFilter, setStatusFilter] = useState<'all' | PerfRunStatus>('all')

  const casesQuery = useQuery({
    queryKey: ['perfCases', activeProjectId],
    queryFn: () => api.listPerfCases(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const runsQuery = useQuery({
    queryKey: ['perfRuns', activeProjectId, caseFilter, statusFilter, page, pageSize],
    queryFn: () => api.listPerfRuns(activeProjectId!, {
      caseId: caseFilter === 'all' ? undefined : caseFilter,
      status: statusFilter === 'all' ? undefined : statusFilter,
      page,
      pageSize,
    }),
    enabled: Boolean(activeProjectId),
  })
  const runs = listItems(runsQuery.data)
  const total = listTotal(runsQuery.data)

  useEffect(() => {
    setPage(1)
  }, [caseFilter, statusFilter])

  useEffect(() => {
    const caseId = searchParams.get('caseId')
    if (caseId) setCaseFilter(caseId)
  }, [searchParams])

  const columns: TableProps<PerfRunSummary>['columns'] = [
    {
      title: '用例 / 运行',
      dataIndex: 'caseName',
      width: 260,
      render: (_, run) => <div className="min-w-0">
        <div className="truncate font-medium text-app-surface-text" title={run.caseName}>{run.caseName}</div>
        <div className="truncate font-mono text-[11px] text-app-surface-text-muted" title={run.runId}>{run.runId}</div>
      </div>,
    },
    { title: '环境', dataIndex: 'environmentName', width: 140, ellipsis: true },
    { title: '监控接入', dataIndex: 'monitoringConnectionName', width: 160, ellipsis: true },
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
      render: (outcome: PerfRunSummary['outcome']) => outcome
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
    { title: 'k6', dataIndex: 'k6Version', width: 90, render: (value: string) => value || '-' },
  ]

  return <ProjectAccessScope projectId={activeProjectId ?? ''}>
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface api-test-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board tp-list-panel">
          <div className="tp-list-toolbar flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 flex-wrap items-center gap-2.5">
              <Button type="text" icon={<ArrowLeftOutlined />} aria-label="返回性能用例" onClick={() => navigate('/testing?tab=perf')} />
              <h1 className="tp-list-title">运行记录</h1>
              <Select
                className="min-w-[180px]"
                value={caseFilter}
                options={[
                  { value: 'all', label: '全部用例' },
                  ...listItems(casesQuery.data).map((perfCase) => ({ value: perfCase.caseId, label: perfCase.name })),
                ]}
                onChange={setCaseFilter}
                loading={casesQuery.isLoading}
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
              <Text type="secondary">共 {total} 条运行</Text>
              <Button icon={<ReloadOutlined />} loading={runsQuery.isFetching} onClick={() => runsQuery.refetch()}>
                刷新
              </Button>
            </Space>
          </div>
          {runsQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(runsQuery.error)} className="m-4" /> : null}
          <Card styles={{ body: { padding: 0 } }} className="m-4 overflow-hidden">
            <Table<PerfRunSummary>
              rowKey="runId"
              size="middle"
              columns={columns}
              dataSource={runs}
              loading={runsQuery.isLoading}
              onRow={(run) => ({ onClick: () => navigate(`/performance/runs/${run.runId}`), className: 'cursor-pointer' })}
              pagination={false}
            />
            <div className="table-footer">
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
