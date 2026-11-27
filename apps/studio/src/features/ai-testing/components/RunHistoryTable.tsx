import { Empty, Table, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import type { ReactNode } from 'react'
import { ListPagination } from '@/shared/components/ListPagination'
import { tableFooterClass } from '@/shared/utils/surfaceClasses'
import { formatTime } from '@/utils/format'

type RunHistoryTableProps<T> = {
  className?: string
  pagination?: { current: number; pageSize: number; total: number; loading: boolean; onChange: (page: number, pageSize: number) => void }
  rows: T[]
  getRunId: (row: T) => string | undefined
  selectedRunId: string | undefined
  onSelect: (runId: string | undefined) => void
  renderStatus: (row: T, active: boolean) => ReactNode
  renderArtifacts?: (row: T) => ReactNode
  getCreatedAt?: (row: T) => string | null | undefined
  renderActions?: (row: T, active: boolean) => ReactNode
}

/**
 * 各列的最小宽度（px）。表格按这些最小宽度的比例分配可用宽度：宽屏下多出来的空间
 * 由所有列平分，而不是堆在末列形成大片空白，窄屏下则回落到最小宽度并横向滚动。
 */
const columnMinWidths = {
  runId: 140,
  pipeline: 220,
  artifacts: 230,
  createdAt: 186,
  actions: 210,
} as const

type RunColumn<T> = NonNullable<TableProps<T>['columns']>[number]

export function RunHistoryTable<T>({
  rows,
  className,
  pagination,
  getRunId,
  selectedRunId,
  onSelect,
  renderStatus,
  renderArtifacts,
  getCreatedAt,
  renderActions,
}: RunHistoryTableProps<T>) {
  const isActive = (row: T) => Boolean(getRunId(row)) && getRunId(row) === selectedRunId
  const columns: Array<RunColumn<T> & { minWidth: number }> = [
    {
      title: '运行',
      key: 'runId',
      minWidth: columnMinWidths.runId,
      render: (_, row, index) => <RunIdCell index={index + (pagination ? (pagination.current - 1) * pagination.pageSize : 0)} runId={getRunId(row)} />,
    },
    ...(getCreatedAt
      ? [{
          title: '创建时间',
          key: 'createdAt',
          minWidth: columnMinWidths.createdAt,
          render: (_: unknown, row: T) => <span className="ai-task-run-table-time inline-flex items-center gap-2 whitespace-nowrap text-[12px] text-[var(--ai-text-secondary)]">{formatTime(getCreatedAt(row) ?? undefined)}</span>,
        }]
      : []),
    {
      title: '状态',
      key: 'pipeline',
      minWidth: columnMinWidths.pipeline,
      render: (_, row) => renderStatus(row, isActive(row)),
    },
    ...(renderArtifacts
      ? [{
          title: '产物',
          key: 'artifacts',
          minWidth: columnMinWidths.artifacts,
          render: (_: unknown, row: T) => renderArtifacts(row),
        }]
      : []),
    ...(renderActions
      ? [{
          title: <span className="tp-actions-col-title inline-block text-center" style={{ width: 92 }}>操作</span>,
          key: 'actions',
          minWidth: columnMinWidths.actions,
          align: 'right' as const,
          render: (_: unknown, row: T) => renderActions(row, isActive(row)),
        }]
      : []),
  ]
  const minWidthTotal = columns.reduce((total, column) => total + column.minWidth, 0)
  const sizedColumns: TableProps<T>['columns'] = columns.map(({ minWidth, ...column }) => ({
    ...column,
    width: `${((minWidth / minWidthTotal) * 100).toFixed(2)}%`,
  }))

  return (
    <>
    <Table<T>
      className={`ai-task-run-list${className ? ` ${className}` : ''}`}
      size="small"
      columns={sizedColumns}
      dataSource={rows}
      rowKey={(row, index) => getRunId(row) ?? String(index ?? 0)}
      pagination={false}
      tableLayout="fixed"
      scroll={{ x: minWidthTotal }}
      sticky
      rowClassName={(row) => (isActive(row) ? 'ai-task-run-table-row-active' : '')}
      onRow={(row) => ({ onClick: () => onSelect(getRunId(row)) })}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运行记录" /> }}
    />
    {pagination ? <div className={`table-footer ${tableFooterClass}`}><ListPagination {...pagination} /></div> : null}
    </>
  )
}

function RunIdCell({ index, runId }: { index: number; runId?: string }) {
  return (
    <span className="ai-task-run-table-id inline-flex min-w-0 items-center gap-2" onClick={(event) => event.stopPropagation()}>
      <span className="ai-task-run-table-index flex-none text-[12px] font-semibold text-[var(--ai-text-muted)]">#{index + 1}</span>
      <Tooltip title={runId || '未命名记录'}>
        <Typography.Text
          className="ai-task-run-table-id-text font-mono text-[12px] text-[var(--ai-text)]"
          copyable={runId ? { text: runId, tooltips: ['复制运行 ID', '已复制'] } : false}
        >
          {runId ? runId.slice(0, 8) : '未命名'}
        </Typography.Text>
      </Tooltip>
    </span>
  )
}

/** 操作列容器；操作按钮由调用方直接提供。 */
export function RunRowActions({
  inline,
  children,
}: {
  inline?: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="ai-task-run-table-actions inline-flex flex-wrap items-center justify-end gap-1.5">
      {inline}
      {children}
    </div>
  )
}
