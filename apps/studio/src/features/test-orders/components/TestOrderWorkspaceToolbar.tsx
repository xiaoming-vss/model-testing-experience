import { FilterOutlined, RightOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Checkbox, Input, Popover, Tooltip } from 'antd'
import { ActionButton } from '@/shared/components/ActionButton'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import type { TestOrder } from '../types'
import {
  getTestOrderStatusMeta,
  getTestOrderStatusTone,
  type TestOrderStatusFilter,
} from '../utils/testOrderStatus'
import { TestOrderProgressFilter } from './TestOrderProgressFilter'

type Props = {
  order?: TestOrder
  statusCounts?: Record<string, number>
  statusFilter: TestOrderStatusFilter
  onStatusFilterChange: (status: TestOrderStatusFilter) => void
  keyword: string
  onKeywordChange: (value: string) => void
  onlyMine: boolean
  onOnlyMineChange: (onlyMine: boolean) => void
  hasFilters: boolean
  onClearFilters: () => void
  onRefresh: () => void
  refreshing: boolean
  graphActive: boolean
  onToggleGraph: () => void
  onBack: () => void
  onAddCases: () => void
}

/**
 * 测试单执行工作台的单行工具栏。
 * 订单上下文、执行进度筛选和列表操作都放在同一行；搜索与“只看我负责的”收进筛选弹层。
 * 列表卡片、详情卡片和图谱容器各自把它作为第一行渲染，因此不再保留独立的顶部订单卡片。
 */
export function TestOrderWorkspaceToolbar({
  order,
  statusCounts,
  statusFilter,
  onStatusFilterChange,
  keyword,
  onKeywordChange,
  onlyMine,
  onOnlyMineChange,
  hasFilters,
  onClearFilters,
  onRefresh,
  refreshing,
  graphActive,
  onToggleGraph,
  onBack,
  onAddCases,
}: Props) {
  const orderStatusMeta = order ? getTestOrderStatusMeta(order.status) : null
  const activeFilterCount = Number(Boolean(keyword.trim())) + Number(onlyMine)

  const filterContent = <div className="test-order-workspace-filter-popover flex w-[300px] max-w-[76vw] flex-col gap-3">
    <Input
      allowClear
      prefix={<SearchOutlined aria-hidden="true" />}
      placeholder="搜索用例 ID 或关键字"
      aria-label="搜索执行条目"
      value={keyword}
      onChange={(event) => onKeywordChange(event.target.value)}
    />
    <Checkbox
      checked={onlyMine}
      onChange={(event) => onOnlyMineChange(event.target.checked)}
    >
      只看我负责的
    </Checkbox>
    <div className="test-order-workspace-filter-footer flex items-center justify-between gap-2.5 border-t border-[var(--srf-divider)] pt-2.5 text-[11px] text-[var(--srf-text-muted)]">
      <span>与执行状态筛选叠加</span>
      <Button type="link" size="small" onClick={onClearFilters} disabled={!hasFilters}>
        清除全部筛选
      </Button>
    </div>
  </div>

  return <div className="tp-list-toolbar test-order-workspace-toolbar justify-start rounded-none border-0 border-b border-b-[var(--srf-card-border)]">
    <nav className="test-order-workspace-breadcrumb flex min-w-0 flex-[0_1_auto] items-center gap-[7px]" aria-label="面包屑">
      <button
        type="button"
        className="test-order-workspace-crumb-link inline-flex h-6 cursor-pointer items-center whitespace-nowrap rounded-[5px] border-0 bg-transparent px-[5px] text-[13px] leading-none text-[var(--srf-accent)] first:-ml-[5px] hover:bg-[var(--srf-accent-soft)] hover:text-[var(--srf-accent-strong)] hover:underline hover:underline-offset-[3px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--srf-accent)]"
        title="返回测试单列表"
        onClick={onBack}
      >
        测试单
      </button>
      <span className="test-order-workspace-crumb-sep inline-flex flex-none items-center text-[10px] text-[var(--srf-text-muted)]" aria-hidden="true"><RightOutlined /></span>
      <h1 className="test-order-workspace-crumb-current m-0 max-w-[360px] overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold leading-5 text-[var(--srf-text)] max-[1100px]:max-w-[220px]" title={order?.name ?? '测试单'}>
        {order?.name ?? '测试单'}
      </h1>
    </nav>

    {order?.testedVersion ? (
      <span className="test-order-workspace-chip tp-tone-tag flex-none">
        被测版本 {order.testedVersion}
      </span>
    ) : null}
    {orderStatusMeta ? (
      <span className={`test-order-workspace-chip tp-tone-tag flex-none tone-${getTestOrderStatusTone(order?.status)}`}>
        {orderStatusMeta.label}
      </span>
    ) : null}

    <TestOrderProgressFilter
      counts={statusCounts ?? {}}
      value={statusFilter}
      onChange={onStatusFilterChange}
    />

    <span className="test-order-workspace-toolbar-spacer min-w-0 flex-auto" />

    <ActionButton
      operation="refresh"
      title="刷新执行条目"
      aria-label="刷新执行条目"
      loading={refreshing}
      onClick={onRefresh}
    />

    <Popover
      trigger="click"
      placement="bottomRight"
      content={filterContent}
      getPopupContainer={(trigger) =>
        (trigger.closest('.test-order-workspace-page') as HTMLElement | null) ?? document.body}
    >
      <Button
        className={`test-order-workspace-filter-btn flex-none${activeFilterCount ? ' is-active border-[var(--srf-accent-border)] bg-[var(--srf-accent-soft)] text-[var(--srf-accent-strong)]' : ''}`}
        icon={<FilterOutlined aria-hidden="true" />}
        aria-label={activeFilterCount
          ? `筛选执行用例，已启用 ${activeFilterCount} 项`
          : '筛选执行用例'}
      >
        筛选
        {activeFilterCount ? (
          <span className="test-order-workspace-filter-count inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--srf-count-badge)] px-1 text-[10px] leading-4 text-[var(--srf-accent-strong)] tabular-nums">{activeFilterCount}</span>
        ) : null}
      </Button>
    </Popover>

    <Tooltip title={graphActive ? '再次点击返回用例列表' : '切换到用例图谱'}>
      <Button
        type={graphActive ? 'primary' : 'default'}
        aria-pressed={graphActive}
        disabled={!order?.orderId}
        onClick={onToggleGraph}
      >
        用例图谱
      </Button>
    </Tooltip>

    <ProjectActionButton
      action="write"
      projectId={order?.projectId}
      className="action-btn-create"
      operation="create"
      disabled={!order?.orderId}
      onClick={onAddCases}
    >
      加入用例
    </ProjectActionButton>
  </div>
}
