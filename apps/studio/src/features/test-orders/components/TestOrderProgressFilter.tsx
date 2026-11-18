import type { CSSProperties } from 'react'
import {
  getTestOrderEntryStatusMeta,
  TEST_ORDER_RESULT_ORDER,
  type TestOrderStatusFilter,
} from '../utils/testOrderStatus'

const SEGMENT_COLORS = {
  passed: 'var(--srf-result-passed)',
  failed: 'var(--srf-result-failed)',
  blocked: 'var(--srf-result-blocked)',
  skipped: 'var(--srf-result-skipped)',
  pending: 'var(--srf-track-pending)',
} as const

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

  return <div className="test-order-progress-filter flex min-w-[170px] max-w-[560px] flex-[1_1_320px] items-center max-[1100.01px]:max-w-none max-[1100.01px]:flex-[1_1_100%]">
    <div
      className="test-order-progress-track relative flex h-[18px] min-w-[140px] flex-auto items-center gap-0.5 before:pointer-events-none before:absolute before:inset-x-0 before:top-[5px] before:h-2 before:rounded-full before:bg-[var(--srf-track)] before:content-['']"
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
          className={`test-order-progress-seg is-${status} relative z-[1] h-[18px] min-w-2 flex-shrink basis-0 cursor-pointer border-0 bg-transparent p-0 transition-[opacity,filter] duration-150 before:absolute before:inset-x-0 before:top-[5px] before:h-2 before:rounded-full before:bg-[var(--seg-color)] before:content-[''] before:transition-[filter,box-shadow] before:duration-150 hover:brightness-112 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--srf-accent)]${active ? ' is-active z-[2] before:shadow-[0_0_0_1px_var(--app-list-toolbar-bg,var(--srf-card)),0_0_0_3px_color-mix(in_srgb,var(--seg-color)_65%,var(--srf-text-secondary)_35%)] before:brightness-108 before:saturate-115' : ''}${dim ? ' is-dim opacity-[0.36] saturate-[0.45]' : ''}`}
          style={{ flexGrow: count, '--seg-color': SEGMENT_COLORS[status] } as CSSProperties}
          aria-label={`${meta.label} ${count}`}
          aria-pressed={active}
          title={`${meta.label} ${count}（${percent}%）${active ? '，再次点击清除' : ''}`}
          onClick={() => onChange(active ? 'all' : status)}
        />
      })}
    </div>
  </div>
}
