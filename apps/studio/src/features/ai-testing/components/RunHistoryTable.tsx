import { Button, Dropdown, Empty, Popover, Table, Tooltip, Typography } from 'antd'
import { MoreOutlined, WarningOutlined } from '@ant-design/icons'
import type { MenuProps, TableProps } from 'antd'
import type { ReactNode } from 'react'
import { formatTime } from '@/utils/format'

export type RunMenuAction = { key: string; label: string; disabled?: boolean; danger?: boolean }

type RunHistoryTableProps<T> = {
  rows: T[]
  getRunId: (row: T) => string | undefined
  selectedRunId: string | undefined
  /** 选中行的详情由单独的查询异步刷新，优先使用其最新数据。 */
  resolveRow: (row: T) => T
  onSelect: (runId: string | undefined) => void
  renderStatus: (row: T, active: boolean) => ReactNode
  renderArtifacts?: (row: T) => ReactNode
  getReviewedAt?: (row: T) => string | null | undefined
  getReviewComment?: (row: T) => string | undefined
  getImportedAt?: (row: T) => string | null | undefined
  renderPrimary?: (row: T, index: number) => ReactNode
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
  reviewedAt: 186,
  importedAt: 140,
  actions: 210,
} as const

type RunColumn<T> = NonNullable<TableProps<T>['columns']>[number]

export function RunHistoryTable<T>({
  rows,
  getRunId,
  selectedRunId,
  resolveRow,
  onSelect,
  renderStatus,
  renderArtifacts,
  getReviewedAt,
  getReviewComment,
  getImportedAt,
  renderPrimary,
  renderActions,
}: RunHistoryTableProps<T>) {
  const isActive = (row: T) => Boolean(getRunId(row)) && getRunId(row) === selectedRunId
  const columns: Array<RunColumn<T> & { minWidth: number }> = [
    {
      title: '运行',
      key: 'runId',
      minWidth: columnMinWidths.runId,
      render: (_, row, index) => renderPrimary?.(row, index) ?? <RunIdCell index={index} runId={getRunId(row)} />,
    },
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
    ...(getReviewedAt
      ? [{
          title: '审核时间',
          key: 'reviewedAt',
          minWidth: columnMinWidths.reviewedAt,
          render: (_: unknown, row: T) => {
            const data = resolveRow(row)
            const comment = getReviewComment?.(data)
            return (
              <span className="ai-task-run-table-time">
                <span>{formatTime(getReviewedAt(data) ?? undefined)}</span>
                {comment ? <RunReviewNoteButton comment={comment} /> : null}
              </span>
            )
          },
        }]
      : []),
    ...(getImportedAt
      ? [{
          title: '导入时间',
          key: 'importedAt',
          minWidth: columnMinWidths.importedAt,
          render: (_: unknown, row: T) => (
            <span className="ai-task-run-table-time">{formatTime(getImportedAt(resolveRow(row)) ?? undefined)}</span>
          ),
        }]
      : []),
    ...(renderActions
      ? [{
          title: '操作',
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
    <Table<T>
      className="ai-task-run-table"
      size="small"
      columns={sizedColumns}
      dataSource={rows}
      rowKey={(row, index) => getRunId(row) ?? String(index ?? 0)}
      pagination={false}
      tableLayout="fixed"
      scroll={{ x: minWidthTotal }}
      rowClassName={(row) => (isActive(row) ? 'ai-task-run-table-row-active' : '')}
      onRow={(row) => ({ onClick: () => onSelect(getRunId(row)) })}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运行记录" /> }}
    />
  )
}

export function RunIdCell({ index, runId }: { index: number; runId?: string }) {
  return (
    <span className="ai-task-run-table-id" onClick={(event) => event.stopPropagation()}>
      <span className="ai-task-run-table-index">#{index + 1}</span>
      <Tooltip title={runId || '未命名记录'}>
        <Typography.Text
          className="ai-task-run-table-id-text"
          copyable={runId ? { text: runId, tooltips: ['复制运行 ID', '已复制'] } : false}
        >
          {runId ? runId.slice(0, 8) : '未命名'}
        </Typography.Text>
      </Tooltip>
    </span>
  )
}

/** 操作列容器：内联按钮 + 「更多」下拉（下拉里的操作多为状态变更，需权限与防重复提交）。 */
export function RunRowActions({
  inline,
  children,
  menuItems,
  onMenuAction,
}: {
  inline?: ReactNode
  children?: ReactNode
  menuItems: RunMenuAction[]
  onMenuAction: (key: string) => void
}) {
  const menu: MenuProps = { items: menuItems, onClick: ({ key }) => onMenuAction(key) }
  return (
    <div className="ai-task-run-table-actions">
      {inline}
      {children}
      {menuItems.length > 0 ? (
        <Dropdown trigger={['click']} destroyPopupOnHide menu={menu}>
          <Button
            size="small"
            className="ai-task-run-table-more"
            aria-label="更多操作"
            icon={<MoreOutlined />}
            onClick={(event) => event.stopPropagation()}
          />
        </Dropdown>
      ) : null}
    </div>
  )
}

export function RunReviewNoteButton({ comment }: { comment: string }) {
  return (
    <Popover trigger="click" placement="bottomRight" content={<div className="ai-task-run-review-comment">{comment}</div>}>
      <button type="button" className="ai-task-run-review-note-btn" onClick={(event) => event.stopPropagation()}>
        审核备注
      </button>
    </Popover>
  )
}

export function RunMigrationWarningIcon() {
  return (
    <Tooltip title="历史导入目标数据不完整：部分历史功能套件目标未能完整恢复；这不影响查看、审核或继续处理当前运行。">
      <span
        role="img"
        aria-label="历史导入目标数据不完整"
        className="ai-task-run-table-migration"
        onClick={(event) => event.stopPropagation()}
      >
        <WarningOutlined />
      </span>
    </Tooltip>
  )
}
