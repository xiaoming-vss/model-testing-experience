import { ListSurface } from '@/shared/components/ListSurface'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Progress, Segmented, Select, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { ListPagination } from '@/shared/components/ListPagination'
import { useActiveProject } from '@/domain/projects/hooks/useActiveProject'
import { ProjectAccessScope } from '@/domain/projects/components/ProjectAccessScope'
import { api, listItems, listTotal } from '@/services/api'
import { formatTime, getErrorMessage } from '@/utils/format'
import { runDetailToolbarClass, runIdLineClass } from '@/shared/utils/surfaceClasses'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import type { PerfRunStatus, PerfRunSummary, PerfSuiteRunSummary } from '../types'
import {
  PERF_OUTCOME_LABELS,
  PERF_STATUS_LABELS,
  formatPerfDuration,
  isPerfRunActive,
  perfOutcomeColor,
  perfStatusColor,
} from '../utils/perf'

const { Text } = Typography

type RunKind = 'suite' | 'case'

export function PerformanceRunsPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { activeProjectId } = useActiveProject()
  const runKind: RunKind = searchParams.get('kind') === 'case' ? 'case' : 'suite'
  const caseFilter = searchParams.get('caseId') ?? ''
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [suiteFilter, setSuiteFilter] = useState(searchParams.get('suiteId') ?? 'all')
  const [statusFilter, setStatusFilter] = useState<'all' | PerfRunStatus>('all')

  const suitesQuery = useQuery({
    queryKey: ['perfSuites', activeProjectId],
    queryFn: () => api.listPerfSuites(activeProjectId!),
    enabled: Boolean(activeProjectId) && runKind === 'suite',
  })
  const suiteRunsQuery = useQuery({
    queryKey: ['perfSuiteRuns', activeProjectId, suiteFilter, statusFilter, page, pageSize],
    queryFn: () => api.listPerfSuiteRuns(activeProjectId!, {
      suiteId: suiteFilter === 'all' ? undefined : suiteFilter,
      status: statusFilter === 'all' ? undefined : statusFilter,
      page,
      pageSize,
    }),
    enabled: Boolean(activeProjectId) && runKind === 'suite',
    refetchInterval: (query) => query.state.data?.items?.some((run) => isPerfRunActive(run.status)) ? 3000 : false,
  })
  const caseRunsQuery = useQuery({
    queryKey: ['perfRuns', activeProjectId, caseFilter, statusFilter, page, pageSize],
    queryFn: () => api.listPerfRuns(activeProjectId!, {
      caseId: caseFilter || undefined,
      status: statusFilter === 'all' ? undefined : statusFilter,
      triggerType: 'manual',
      page,
      pageSize,
    }),
    enabled: Boolean(activeProjectId) && runKind === 'case',
    refetchInterval: (query) => query.state.data?.items?.some((run) => isPerfRunActive(run.status)) ? 3000 : false,
  })
  const activeQuery = runKind === 'case' ? caseRunsQuery : suiteRunsQuery
  const suiteRuns = listItems(suiteRunsQuery.data)
  const caseRuns = listItems(caseRunsQuery.data)
  const total = runKind === 'case' ? listTotal(caseRunsQuery.data) : listTotal(suiteRunsQuery.data)

  useEffect(() => {
    setPage(1)
  }, [suiteFilter, statusFilter, runKind, caseFilter])

  useEffect(() => {
    const suiteId = searchParams.get('suiteId')
    if (suiteId) setSuiteFilter(suiteId)
  }, [searchParams])

  function switchKind(next: RunKind) {
    if (next === runKind) return
    setSearchParams(next === 'case' ? { kind: 'case' } : {})
  }

  function clearCaseFilter() {
    const next = new URLSearchParams(searchParams)
    next.delete('caseId')
    setSearchParams(next)
  }

  function progress(run: PerfSuiteRunSummary) {
    const settled = run.completedCount + run.failedCount + run.skippedCount
    if (!run.totalCount) return 0
    return Math.round((settled / run.totalCount) * 100)
  }

  const suiteColumns: TableProps<PerfSuiteRunSummary>['columns'] = [
    {
      title: '测试集 / 运行',
      dataIndex: 'suiteName',
      width: 280,
      render: (_, run) => <div className="min-w-0">
        <div className="truncate font-medium text-app-surface-text" title={run.suiteName}>{run.suiteName}</div>
        <div className={runIdLineClass} title={run.suiteRunId}>{run.suiteRunId}</div>
      </div>,
    },
    { title: '环境', dataIndex: 'environmentName', width: 140, ellipsis: true },
    {
      title: '进度',
      width: 190,
      render: (_, run) => <div className="flex min-w-[150px] items-center gap-2">
        <Progress percent={progress(run)} size="small" showInfo={false} className="mb-0 flex-1" />
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

  const caseColumns: TableProps<PerfRunSummary>['columns'] = [
    {
      title: '用例 / 运行',
      dataIndex: 'caseName',
      width: 300,
      render: (_, run) => <div className="min-w-0">
        <div className="truncate font-medium text-app-surface-text" title={run.caseName}>{run.caseName}</div>
        <div className={runIdLineClass} title={run.runId}>{run.runId}</div>
      </div>,
    },
    { title: '环境', dataIndex: 'environmentName', width: 160, ellipsis: true },
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
    {
      title: '',
      width: 72,
      render: (_, run) => <Button size="small" onClick={(event) => { event.stopPropagation(); navigate(`/performance/case-runs/${run.runId}`) }}>查看</Button>,
    },
  ]

  return <ProjectAccessScope projectId={activeProjectId ?? ''}>
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface api-test-page tp-surface">
      <div className="api-automation-content">
        <ListSurface
          className="workbench-panel workbench-panel-flat workbench-board-panel"
          toolbar={
            <div className={runDetailToolbarClass}>
              <div className="flex min-w-0 flex-wrap items-center gap-2.5">
                <Button type="text" icon={<ArrowLeftOutlined />} aria-label="返回性能测试" onClick={() => navigate('/testing?tab=perf')} />
                <h1 className="tp-list-title">运行记录</h1>
                <Segmented
                  size="small"
                  value={runKind}
                  options={[
                    { value: 'suite', label: '测试集运行' },
                    { value: 'case', label: '单用例运行' },
                  ]}
                  onChange={(value) => switchKind(value as RunKind)}
                />
                {runKind === 'suite' ? <Select
                  className="min-w-[190px]"
                  value={suiteFilter}
                  options={[
                    { value: 'all', label: '全部测试集' },
                    ...listItems(suitesQuery.data).map((suite) => ({ value: suite.suiteId, label: suite.name })),
                  ]}
                  onChange={setSuiteFilter}
                  loading={suitesQuery.isLoading}
                /> : caseFilter ? <Tag closable onClose={(event) => { event.preventDefault(); clearCaseFilter() }}>仅看当前用例</Tag> : null}
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
                <Button icon={<ReloadOutlined />} loading={activeQuery.isFetching} onClick={() => activeQuery.refetch()}>
                  刷新
                </Button>
              </Space>
            </div>
          }
          notices={activeQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(activeQuery.error)} className="m-4" /> : null}
          footer={
            <ListPagination
              loading={activeQuery.isFetching}
              current={page}
              pageSize={pageSize}
              total={total}
              onChange={(nextPage, nextPageSize) => {
                setPage(nextPage)
                setPageSize(nextPageSize)
              }}
            />
          }
        >
          {runKind === 'case' ? <Table<PerfRunSummary>
            className="tp-list-table"
            rowKey="runId"
            size="middle"
            columns={caseColumns}
            dataSource={caseRuns}
            loading={caseRunsQuery.isLoading}
            onRow={(run) => ({ onClick: () => navigate(`/performance/case-runs/${run.runId}`), className: 'cursor-pointer' })}
            pagination={false}
            locale={{ emptyText: <div className="py-12 text-center text-xs text-app-surface-text-muted">没有符合条件的单用例运行记录。在用例行发起运行后在这里查看。</div> }}
          /> : <Table<PerfSuiteRunSummary>
            className="tp-list-table"
            rowKey="suiteRunId"
            size="middle"
            columns={suiteColumns}
            dataSource={suiteRuns}
            loading={suiteRunsQuery.isLoading}
            onRow={(run) => ({ onClick: () => navigate(`/performance/runs/${run.suiteRunId}`), className: 'cursor-pointer' })}
            pagination={false}
            locale={{ emptyText: <div className="py-12 text-center text-xs text-app-surface-text-muted">没有符合条件的运行记录。调整筛选条件或先运行一个测试集。</div> }}
          />}
        </ListSurface>
      </div>
    </div>
  </ProjectAccessScope>
}
