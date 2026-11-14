import type { TestOrderEntrySummary } from '../types'
import { ActionButton } from '@/shared/components/ActionButton'
import { ListPagination } from '@/shared/components/ListPagination'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { priorityTone } from '@/shared/utils/priorityTone'
import {
  CheckOutlined,
  CloseOutlined,
  DownOutlined,
  FilterOutlined,
  SearchOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Button, Checkbox, Empty, Input, Popconfirm, Popover } from 'antd'
import { useState } from 'react'
import {
  TEST_ORDER_RESULT_ORDER,
  getTestOrderEntryStatusMeta,
  groupTestOrderEntriesByStatus,
  type TestOrderResultStatus,
} from '../utils/testOrderStatus'
import { VisualizationBatchButton } from './visualization/VisualizationBatchButton'

export type TestOrderStatusFilter = 'all' | TestOrderResultStatus

type Props = {
  orderId?: string
  projectId?: string
  entries: TestOrderEntrySummary[]
  statusCounts?: Record<string, number>
  matchedTotal: number
  mineCount: number
  orderTotal: number
  progressPercent: number
  entryTotal: number
  currentPage: number
  pageSize: number
  keyword: string
  statusFilter: TestOrderStatusFilter
  onlyMine: boolean
  checkedEntryIds: string[]
  selectedEntryId: string | null
  collapsedGroups: TestOrderResultStatus[]
  loading: boolean
  fetching: boolean
  placeholder: boolean
  canExecute: boolean
  canWrite: boolean
  batchPending: boolean
  assigneeName: (userId?: string) => string
  onKeywordChange: (value: string) => void
  onStatusFilterChange: (status: TestOrderStatusFilter) => void
  onOnlyMineChange: (onlyMine: boolean) => void
  onToggleGroup: (status: TestOrderResultStatus) => void
  onRefresh: () => void
  onSelectEntry: (id: string | null) => void
  onToggleEntry: (id: string | undefined, checked: boolean) => void
  onToggleAll: (checked: boolean) => void
  onClearChecked: () => void
  onRemoveEntry: (id: string) => void
  onBatchPass: () => void
  onAssign: () => void
  onPageChange: (page: number, pageSize: number) => void
}

/**
 * 执行工作台左侧清单：结果分布只做概览，筛选收进浮层，清单按执行结论分组。
 * 分组计数是当前页的；顶部结果条与筛选浮层使用接口返回的筛选范围总数。
 */
export function TestOrderEntrySidebar({
  orderId, projectId, entries, statusCounts, matchedTotal, mineCount, orderTotal,
  progressPercent, entryTotal, currentPage, pageSize, keyword, statusFilter, onlyMine,
  checkedEntryIds, selectedEntryId, collapsedGroups, loading, fetching, placeholder,
  canExecute, canWrite, batchPending, assigneeName, onKeywordChange, onStatusFilterChange,
  onOnlyMineChange, onToggleGroup, onRefresh, onSelectEntry, onToggleEntry, onToggleAll,
  onClearChecked, onRemoveEntry, onBatchPass, onAssign, onPageChange,
}: Props) {
  const [filterOpen, setFilterOpen] = useState(false)
  const counts = statusCounts ?? {}
  const barTotal = TEST_ORDER_RESULT_ORDER.reduce((sum, status) => sum + (counts[status] ?? 0), 0)
  const groups = groupTestOrderEntriesByStatus(entries).filter((group) => group.entries.length > 0)
  const filterActive = statusFilter !== 'all' || onlyMine
  const activeStatusMeta = statusFilter === 'all' ? null : getTestOrderEntryStatusMeta(statusFilter)
  const pageEntryIds = entries.flatMap((entry) => entry.entryId ? [entry.entryId] : [])
  const allChecked = pageEntryIds.length > 0 && pageEntryIds.every((id) => checkedEntryIds.includes(id))
  const someChecked = pageEntryIds.some((id) => checkedEntryIds.includes(id))
  const checkedCount = checkedEntryIds.length
  const barSummary = TEST_ORDER_RESULT_ORDER
    .filter((status) => (counts[status] ?? 0) > 0)
    .map((status) => `${getTestOrderEntryStatusMeta(status).label} ${counts[status]} 条`)
    .join('，')

  const filterOptions: Array<{ value: TestOrderStatusFilter; label: string; count: number }> = [
    { value: 'all', label: '全部', count: matchedTotal },
    ...TEST_ORDER_RESULT_ORDER.map((status) => ({
      value: status,
      label: getTestOrderEntryStatusMeta(status).label,
      count: counts[status] ?? 0,
    })),
  ]

  function chooseStatus(value: TestOrderStatusFilter) {
    onStatusFilterChange(value === statusFilter && value !== 'all' ? 'all' : value)
    setFilterOpen(false)
  }

  // Popover 内容挂在 body 上，带 tp-surface 让 --srf-* 变量在浮层内可用。
  const filterMenu = <div className="tp-surface test-order-filter-menu" role="menu" aria-label="筛选执行条目">
    <div className="test-order-filter-menu-title">执行结论</div>
    {filterOptions.map((option) => {
      const active = statusFilter === option.value
      return <button key={option.value} type="button" role="menuitemradio" aria-checked={active}
        aria-label={`${option.label} ${option.count}`}
        className={`test-order-filter-option${active ? ' is-active' : ''}`}
        onClick={() => chooseStatus(option.value)}>
        <span className="test-order-filter-option-label">
          {option.value !== 'all' ? <span className={`test-order-filter-dot is-${option.value}`} aria-hidden="true" /> : null}
          {option.label}
        </span>
        <span className="test-order-filter-option-count">{option.count}</span>
        {active ? <CheckOutlined className="test-order-filter-check" aria-hidden="true" /> : null}
      </button>
    })}
    <div className="test-order-filter-sep" />
    <button type="button" role="menuitemcheckbox" aria-checked={onlyMine}
      aria-label={`只看我负责的 ${mineCount}`}
      className={`test-order-filter-option${onlyMine ? ' is-active' : ''}`}
      onClick={() => { onOnlyMineChange(!onlyMine); setFilterOpen(false) }}>
      <span className="test-order-filter-option-label"><UserOutlined aria-hidden="true" />只看我负责的</span>
      <span className="test-order-filter-option-count">{mineCount}</span>
      {onlyMine ? <CheckOutlined className="test-order-filter-check" aria-hidden="true" /> : null}
    </button>
  </div>

  return <section className="workbench-panel test-order-side-panel">
    <header className="test-order-side-head">
      <span className="test-order-side-title">执行用例清单 <span className="test-order-side-count">{orderTotal}</span></span>
      <span className="test-order-side-meta">
        <span className="test-order-side-percent" title={`已执行 ${progressPercent}%`}>{progressPercent}%</span>
        <ActionButton operation="refresh" title="刷新执行条目" aria-label="刷新执行条目" loading={fetching} onClick={onRefresh} />
      </span>
    </header>

    <div className="test-order-result-strip">
      <div className="test-order-result-bar" role="img"
        aria-label={barSummary ? `执行结果分布：${barSummary}` : '执行结果分布：暂无执行条目'}>
        {TEST_ORDER_RESULT_ORDER.map((status) => {
          const count = counts[status] ?? 0
          if (!count) return null
          return <span key={status} className={`test-order-result-seg is-${status}`}
            style={{ width: `${(count / barTotal) * 100}%` }}
            data-tip={`${getTestOrderEntryStatusMeta(status).label} ${count} 条`} aria-hidden="true" />
        })}
      </div>
    </div>

    <div className="test-order-filter-row">
      <Input allowClear prefix={<SearchOutlined />} placeholder="搜索用例 ID 或关键字"
        aria-label="搜索执行条目" value={keyword} onChange={(event) => onKeywordChange(event.target.value)} />
      <Popover open={filterOpen} onOpenChange={setFilterOpen} trigger="click" placement="bottomRight" content={filterMenu}>
        <Button className={`test-order-filter-button${filterActive ? ' is-active' : ''}`}
          icon={<FilterOutlined />} aria-label="筛选执行条目" aria-haspopup="menu" aria-expanded={filterOpen}>
          筛选{filterActive ? <span className="test-order-filter-active-dot" aria-hidden="true" /> : null}
        </Button>
      </Popover>
    </div>

    {filterActive ? <div className="test-order-active-filters">
      {statusFilter !== 'all' ? <span className="test-order-active-filter">
        {activeStatusMeta?.label}
        <button type="button" aria-label="清除状态筛选" onClick={() => onStatusFilterChange('all')}><CloseOutlined /></button>
      </span> : null}
      {onlyMine ? <span className="test-order-active-filter">
        只看我负责的
        <button type="button" aria-label="清除负责人筛选" onClick={() => onOnlyMineChange(false)}><CloseOutlined /></button>
      </span> : null}
      <button type="button" className="test-order-clear-filters"
        onClick={() => { onStatusFilterChange('all'); onOnlyMineChange(false) }}>清除筛选</button>
    </div> : null}

    <div className="test-order-list-head">
      <Checkbox checked={allChecked} indeterminate={someChecked && !allChecked}
        disabled={!entries.length || placeholder} onChange={(event) => onToggleAll(event.target.checked)}>
        全选本页
      </Checkbox>
      <ListPagination current={currentPage} pageSize={pageSize} total={entryTotal}
        loading={fetching} compact onChange={onPageChange} />
    </div>

    <div className="test-order-side-scroll">
      {loading ? <Empty description="执行条目加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
        : !entries.length ? <Empty description="没有符合筛选条件的条目" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          : <div className="api-case-nav-list test-order-group-list">
            {groups.map((group) => {
              const meta = getTestOrderEntryStatusMeta(group.status)
              const collapsed = collapsedGroups.includes(group.status)
              return <section key={group.status} className={`test-order-group${collapsed ? ' is-collapsed' : ''}`}>
                <button type="button" className="test-order-group-head" aria-expanded={!collapsed}
                  aria-label={`${meta.label} ${group.entries.length}`}
                  onClick={() => onToggleGroup(group.status)}>
                  <DownOutlined className="test-order-group-chevron" aria-hidden="true" />
                  <span className={`test-order-group-dot is-${group.status}`} aria-hidden="true" />
                  <span>{meta.label}</span>
                  <span className="test-order-group-count">{group.entries.length}</span>
                  <span className="test-order-group-line" aria-hidden="true" />
                </button>
                {collapsed ? null : <div className="test-order-group-rows">
                  {group.entries.map((entry) => <EntryRow key={entry.entryId ?? entry.orderNo}
                    entry={entry} active={entry.entryId === selectedEntryId}
                    checked={checkedEntryIds.includes(entry.entryId ?? '')} disabled={placeholder}
                    canRemove={canWrite} assigneeName={assigneeName}
                    onSelect={onSelectEntry} onToggle={onToggleEntry} onRemove={onRemoveEntry} />)}
                </div>}
              </section>
            })}
          </div>}
    </div>

    {checkedCount > 0 ? <div className="test-order-selection-bar" role="region" aria-label="已选条目的批量操作">
      <div className="test-order-selection-info">
        <span className="test-order-selection-count" title="支持跨页选择">已选 {checkedCount} 条</span>
        <button type="button" className="test-order-selection-clear" onClick={onClearChecked}>清空</button>
      </div>
      <div className="test-order-selection-actions">
        {canExecute && orderId ? <VisualizationBatchButton key={orderId} orderId={orderId} projectId={projectId}
          entryIds={checkedEntryIds} onSelect={(id) => onSelectEntry(id)} compact /> : null}
        <ProjectActionButton action="manage" className="action-btn-update" operation="edit" size="small"
          aria-label={`分配执行人（${checkedCount}）`} onClick={onAssign}>
          分配
        </ProjectActionButton>
        {canExecute ? <Popconfirm title={`确认将选中的 ${checkedCount} 条标记为通过？`} okText="确认标记"
          disabled={checkedCount === 0} onConfirm={onBatchPass}>
          <Button className="action-btn-save" type="primary" size="small" icon={<CheckOutlined />}
            aria-label={`批量标记通过（${checkedCount}）`} loading={batchPending} disabled={checkedCount === 0}>
            标记通过
          </Button>
        </Popconfirm> : null}
      </div>
    </div> : null}
  </section>
}

function EntryRow({ entry, active, checked, disabled, canRemove, assigneeName, onSelect, onToggle, onRemove }: {
  entry: TestOrderEntrySummary
  active: boolean
  checked: boolean
  disabled: boolean
  canRemove: boolean
  assigneeName: (userId?: string) => string
  onSelect: (id: string | null) => void
  onToggle: (id: string | undefined, checked: boolean) => void
  onRemove: (id: string) => void
}) {
  const stepCount = entry.stepCount ?? 0
  const title = entry.caseTitle || entry.caseId
  const assignee = entry.assigneeUserId ? assigneeName(entry.assigneeUserId) : '未分配'
  const metaText = [
    entry.casePriority ? `优先级 ${entry.casePriority}` : '',
    entry.caseModule ?? '',
    `${stepCount} 步`,
    assignee,
  ].filter(Boolean).join(' · ')
  return <div className={`test-order-nav-row${active ? ' active' : ''}`}>
    <Checkbox aria-label={`选择第 ${entry.orderNo ?? ''} 条执行条目`} checked={checked} disabled={disabled}
      onChange={(event) => onToggle(entry.entryId, event.target.checked)} />
    <button type="button" className="test-order-nav-item test-order-nav-item--grouped" disabled={disabled}
      aria-current={active} aria-label={`${title}，${metaText}`} title={`${title} · ${metaText}`}
      onClick={() => onSelect(entry.entryId ?? null)}>
      {entry.casePriority ? <span className={`test-order-nav-prio tp-tone-tag tone-${priorityTone(entry.casePriority)}`}>
        {entry.casePriority}
      </span> : null}
      <span className="test-order-nav-title">{title}</span>
    </button>
    {canRemove ? <Popconfirm title="确认移除该执行条目？" description="移除后条目及其结果不再保留，用例本身不受影响。"
      okText="确认移除" okButtonProps={{ danger: true }}
      onConfirm={() => entry.entryId && onRemove(entry.entryId)}>
      <button type="button" className="test-order-nav-remove" aria-label={`移除第 ${entry.orderNo ?? ''} 条执行条目`}>✕</button>
    </Popconfirm> : null}
  </div>
}

// 分组计数为当前页；顶部结果条与筛选浮层使用接口返回的筛选范围总数。
