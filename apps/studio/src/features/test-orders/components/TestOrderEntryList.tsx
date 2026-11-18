import { CloseOutlined } from '@ant-design/icons'
import {
  Button,
  Checkbox,
  Empty,
  Popconfirm,
  Table,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ListPagination } from '@/shared/components/ListPagination'
import { tableFooterClass } from '@/shared/utils/surfaceClasses'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { priorityTone } from '@/shared/utils/priorityTone'
import { message } from '@/shared/utils/feedback'
import { formatTime } from '@/utils/format'
import type { TestOrderEntrySummary } from '../types'
import {
  getTestOrderEntryStatusMeta,
  getTestOrderEntryStatusTone,
} from '../utils/testOrderStatus'
import { VisualizationBatchButton } from './visualization/VisualizationBatchButton'
import '@/shared/styles/surface-tokens.css'
import '@/shared/styles/list-table.css'

const { Text } = Typography

const NARROW_COLUMN_KEYS = new Set(['caseModule', 'casePriority', 'assignee', 'stepCount', 'executedAt'])

/** 窄屏保留“名称 + 执行状态”，隐藏次要列，避免关键状态被横向滚动推到屏幕外。 */
function useNarrowList(ref: { current: HTMLElement | null }) {
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && Boolean(window.matchMedia?.('(max-width: 1100px)').matches),
  )
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const update = () => setNarrow(element.clientWidth > 0 && element.clientWidth < 1100)
    update()
    if (typeof ResizeObserver === 'function') {
      const observer = new ResizeObserver(update)
      observer.observe(element)
      return () => observer.disconnect()
    }
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [ref])
  return narrow
}

type Props = {
  toolbar?: ReactNode
  orderId?: string
  projectId?: string
  entries: TestOrderEntrySummary[]
  entryTotal: number
  currentPage: number
  pageSize: number
  checkedEntryIds: string[]
  loading: boolean
  fetching: boolean
  placeholder: boolean
  canExecute: boolean
  canWrite: boolean
  batchPending: boolean
  hasFilters: boolean
  assigneeName: (userId?: string) => string
  onSelectEntry: (id: string) => void
  onToggleEntry: (id: string | undefined, checked: boolean) => void
  onToggleAll: (checked: boolean) => void
  onClearChecked: () => void
  onRemoveEntry: (id: string) => void
  onBatchPass: () => void
  onAssign: () => void
  onPageChange: (page: number, pageSize: number) => void
  onAddCases: () => void
  onClearFilters: () => void
}

/**
 * 列表优先的测试单执行页：进入测试单先看到全宽条目表，点击一行才进入详情。
 * 筛选、批量操作和分页都留在列表里，详情返回时列表保持挂载与滚动位置。
 */
export function TestOrderEntryList({
  toolbar,
  orderId,
  projectId,
  entries,
  entryTotal,
  currentPage,
  pageSize,
  checkedEntryIds,
  loading,
  fetching,
  placeholder,
  canExecute,
  canWrite,
  batchPending,
  hasFilters,
  assigneeName,
  onSelectEntry,
  onToggleEntry,
  onToggleAll,
  onClearChecked,
  onRemoveEntry,
  onBatchPass,
  onAssign,
  onPageChange,
  onAddCases,
  onClearFilters,
}: Props) {
  const listRef = useRef<HTMLElement>(null)
  const narrow = useNarrowList(listRef)
  const checkedCount = checkedEntryIds.length
  const pageEntryIds = entries.flatMap((entry) => entry.entryId ? [entry.entryId] : [])
  const allChecked = pageEntryIds.length > 0 && pageEntryIds.every((id) => checkedEntryIds.includes(id))
  const someChecked = pageEntryIds.some((id) => checkedEntryIds.includes(id))

  // 整单是否为空不能拿 order.entriesTotal 和当前列表条数对比：
  // 筛选后列表为空但整单有条目，此时应该引导清除筛选，而不是加入用例。
  const emptyText = loading ? null : !hasFilters ? (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description="当前测试单还没有执行条目"
    >
      <ProjectActionButton
        action="write"
        projectId={projectId}
        type="primary"
        className="action-btn-create"
        operation="create"
        disabled={!orderId}
        onClick={onAddCases}
      >
        加入用例
      </ProjectActionButton>
    </Empty>
  ) : (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description="没有符合筛选条件的执行条目"
    >
      <Button onClick={onClearFilters}>清除筛选</Button>
    </Empty>
  )

  const columns: TableProps<TestOrderEntrySummary>['columns'] = [
    {
      title: (
        <Checkbox
          aria-label="全选本页"
          checked={allChecked}
          indeterminate={someChecked && !allChecked}
          disabled={!entries.length || placeholder}
          onChange={(event) => onToggleAll(event.target.checked)}
        />
      ),
      key: 'selection',
      width: 44,
      className: 'test-order-entry-selection-cell',
      render: (_, entry) => (
        <span className="test-order-entry-selection inline-flex items-center" onClick={(event) => event.stopPropagation()}>
          <Checkbox
            aria-label={`选择第 ${entry.orderNo ?? ''} 条执行条目`}
            checked={checkedEntryIds.includes(entry.entryId ?? '')}
            disabled={placeholder}
            onChange={(event) => onToggleEntry(entry.entryId, event.target.checked)}
          />
        </span>
      ),
    },
    {
      title: '用例 ID',
      dataIndex: 'caseId',
      key: 'caseId',
      width: 136,
      render: (caseId: string | undefined) => caseId ? (
        <button
          type="button"
          className="test-order-entry-id inline-block box-border w-24 max-w-full cursor-copy overflow-hidden text-ellipsis whitespace-nowrap rounded-[4px] border-0 bg-[var(--srf-chip)] px-1.5 py-0.5 text-left align-middle font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-[11px] leading-4 text-[var(--srf-text-muted)] hover:text-[var(--srf-accent)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--srf-accent)]"
          title={`${caseId}（点击复制）`}
          aria-label={`复制用例 ID ${caseId}`}
          onClick={async (event) => {
            // ID 是行内的复制入口，不能同时把整行点进详情。
            event.stopPropagation()
            try {
              await navigator.clipboard.writeText(caseId)
              message.success('用例 ID 已复制')
            } catch {
              message.error('复制失败，请重试')
            }
          }}
        >
          {caseId}
        </button>
      ) : <span className="test-order-entry-muted text-[var(--srf-text-muted)]">—</span>,
    },
    {
      title: '用例名称',
      key: 'caseTitle',
      render: (_, entry) => {
        const title = entry.caseTitle || '未命名用例'
        return (
          <div className="tp-list-name test-order-entry-name-cell flex min-w-0 items-center gap-2" title={title}>
            <Text className="test-order-entry-name min-w-0 flex-1" ellipsis>{title}</Text>
          </div>
        )
      },
    },
    {
      title: '所属模块',
      dataIndex: 'caseModule',
      key: 'caseModule',
      width: 130,
      render: (module: string | undefined) => module
        ? <span className="test-order-entry-module inline-block max-w-full overflow-hidden text-ellipsis whitespace-nowrap rounded-[5px] bg-[var(--srf-chip)] px-[7px] py-0.5 text-[11px] text-[var(--srf-chip-text)]" title={module}>{module}</span>
        : <span className="test-order-entry-muted text-[var(--srf-text-muted)]">—</span>,
    },
    {
      title: '优先级',
      dataIndex: 'casePriority',
      key: 'casePriority',
      width: 82,
      render: (priority: string | undefined) => priority
        ? <span className={`tp-tone-tag tone-${priorityTone(priority)}`}>{priority}</span>
        : <span className="test-order-entry-muted text-[var(--srf-text-muted)]">—</span>,
    },
    {
      title: '执行状态',
      dataIndex: 'status',
      key: 'status',
      width: 108,
      render: (status: string | undefined) => {
        const meta = getTestOrderEntryStatusMeta(status)
        return (
          <span className={`tp-tone-tag test-order-entry-status tone-${getTestOrderEntryStatusTone(status)}`}>
            <i className="test-order-entry-status-dot h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
            {meta.label}
          </span>
        )
      },
    },
    {
      title: '执行人',
      dataIndex: 'assigneeUserId',
      key: 'assignee',
      width: 116,
      render: (userId: string | undefined) => {
        const name = assigneeName(userId)
        return name
          ? <span className="test-order-entry-person text-[var(--srf-text-secondary)]">{name}</span>
          : <span className="test-order-entry-unassigned text-[var(--srf-text-secondary)]">未分配</span>
      },
    },
    {
      title: '步骤',
      dataIndex: 'stepCount',
      key: 'stepCount',
      width: 66,
      render: (stepCount: number | undefined) => stepCount ? `${stepCount} 步` : '—',
    },
    {
      title: '最近执行',
      dataIndex: 'executedAt',
      key: 'executedAt',
      width: 146,
      render: (executedAt: string | undefined) => (
        <span className="test-order-entry-time whitespace-nowrap text-[11.5px] tabular-nums text-[var(--srf-text-secondary)]">{formatTime(executedAt) || '—'}</span>
      ),
    },
    {
      title: '',
      key: 'actions',
      width: 56,
      className: 'test-order-entry-actions-cell text-right',
      render: (_, entry) => canWrite ? (
        <span className="test-order-entry-actions flex w-full items-center justify-end" onClick={(event) => event.stopPropagation()}>
          <Popconfirm
            title="确认移除该执行条目？"
            description="移除后条目及其结果不再保留，用例本身不受影响。"
            okText="确认移除"
            okButtonProps={{ danger: true }}
            onConfirm={() => entry.entryId && onRemoveEntry(entry.entryId)}
          >
            <ProjectActionButton
              action="write"
              projectId={projectId}
              type="text"
              shape="circle"
              danger
              className="action-btn-delete"
              operation="delete"
              iconOnly
              icon={<CloseOutlined />}
              aria-label={`移除第 ${entry.orderNo ?? ''} 条执行条目`}
            />
          </Popconfirm>
        </span>
      ) : null,
    },
  ]

  return <section ref={listRef} className="workbench-panel workbench-panel-flat tp-board tp-list-panel test-order-entry-list-panel">
    {toolbar}

    <div className="tp-list-body">
      <div className="tp-list-scroll test-order-entry-scroll">
        <Table<TestOrderEntrySummary>
          className="functional-suite-list-table tp-list-table test-order-entry-table [&_.ant-table-tbody>tr]:cursor-pointer"
          columns={narrow
            ? columns.filter((column) => !NARROW_COLUMN_KEYS.has(String(column.key)))
            : columns}
          dataSource={entries}
          rowKey={(entry) => entry.entryId ?? entry.caseId ?? String(entry.orderNo ?? '')}
          pagination={false}
          loading={loading}
          tableLayout="fixed"
          scroll={{ x: narrow ? 560 : 1160 }}
          locale={{ emptyText }}
          onRow={(entry) => ({
            onClick: (event) => {
              if ((event.target as HTMLElement).closest('.test-order-entry-selection, .test-order-entry-actions')) return
              if (entry.entryId) onSelectEntry(entry.entryId)
            },
          })}
        />
      </div>

      {checkedCount > 0 ? <div className="test-order-entry-batch flex flex-none flex-wrap items-center gap-2.5 border-t border-[var(--srf-accent-border)] bg-[var(--srf-accent-soft)] px-4 py-2 text-[12px] text-[var(--srf-accent-strong)]" role="region" aria-label="已选条目的批量操作">
        <span className="test-order-entry-batch-count font-semibold tabular-nums">已选 {checkedCount} 条</span>
        <span className="test-order-entry-batch-note text-[11px] text-[var(--srf-text-secondary)]">支持跨页选择</span>
        <div className="test-order-entry-batch-actions flex flex-wrap items-center gap-2 ml-auto max-[1100.01px]:ml-0 max-[1100.01px]:w-full">
          {canExecute && orderId ? <VisualizationBatchButton
            key={orderId}
            orderId={orderId}
            projectId={projectId}
            entryIds={checkedEntryIds}
            onSelect={(id) => onSelectEntry(id)}
            compact
          /> : null}
          <ProjectActionButton
            action="manage"
            projectId={projectId}
            className="action-btn-update"
            operation="edit"
            size="small"
            aria-label={`分配执行人（${checkedCount}）`}
            onClick={onAssign}
          >
            分配
          </ProjectActionButton>
          {canExecute ? <Popconfirm
            title={`确认将选中的 ${checkedCount} 条标记为通过？`}
            okText="确认标记"
            onConfirm={onBatchPass}
          >
            <Button
              className="action-btn-save"
              type="primary"
              size="small"
              aria-label={`批量标记通过（${checkedCount}）`}
              loading={batchPending}
            >
              标记通过
            </Button>
          </Popconfirm> : null}
          <Button type="text" size="small" onClick={onClearChecked}>清空</Button>
        </div>
      </div> : null}

      <div className={`table-footer test-order-entry-footer ${tableFooterClass}`}>
        <ListPagination
          current={currentPage}
          pageSize={pageSize}
          total={entryTotal}
          loading={fetching}
          onChange={onPageChange}
        />
      </div>
    </div>
  </section>
}
