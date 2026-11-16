import {
  getTestOrderEntryStatusMeta,
  TEST_ORDER_RESULT_ORDER,
  type TestOrderStatusFilter,
} from '../utils/testOrderStatus'

type Props = {
  counts: Record<string, number>
  value: TestOrderStatusFilter
  onChange: (status: TestOrderStatusFilter) => void
}

/**
 * 工作台工具栏里的状态进度条筛选。
 * 色条按各状态数量分配宽度；选中后只保留该状态，其他颜色变暗。
 * 视觉高度 8px，按钮热区 18px，避免细条难以点击；再次点击已选段恢复全部。
 */
export function TestOrderProgressFilter({ counts, value, onChange }: Props) {
  const total = TEST_ORDER_RESULT_ORDER.reduce((sum, status) => sum + (counts[status] ?? 0), 0)
  const activeStatus = value === 'all' ? null : value

  return <div className="test-order-progress-filter">
    <div
      className="test-order-progress-track"
      role="group"
      aria-label="按执行状态筛选"
      title="点击色块按执行状态筛选"
    >
      {TEST_ORDER_RESULT_ORDER.map((status) => {
        const count = counts[status] ?? 0
        if (!count) return null
        const meta = getTestOrderEntryStatusMeta(status)
        const active = activeStatus === status
        const dim = Boolean(activeStatus) && !active
        const percent = total ? Math.round((count / total) * 100) : 0
        return <button
          key={status}
          type="button"
          className={`test-order-progress-seg is-${status}${active ? ' is-active' : ''}${dim ? ' is-dim' : ''}`}
          style={{ flexGrow: count }}
          aria-label={`${meta.label} ${count}`}
          aria-pressed={active}
          title={`${meta.label} ${count}（${percent}%）${active ? '，再次点击清除' : ''}`}
          onClick={() => onChange(active ? 'all' : status)}
        />
      })}
    </div>
  </div>
}
