import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'

export const runCardChipClass =
  'whitespace-nowrap rounded-[4px] bg-[var(--srf-chip)] px-1.5 py-px font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-[11px] font-medium leading-4 text-[var(--srf-chip-text)]'

export type RunCardProps = {
  title: ReactNode
  /** 标题右侧的状态/操作；调用方负责内部布局。 */
  side?: ReactNode
  /** 标题后的等宽小标签。 */
  chip?: ReactNode
  /** 标题前的状态点；默认关闭。 */
  dot?: boolean
  children: ReactNode
  className?: string
  ariaLabel?: string
}

/**
 * 运行详情右栏的卡片骨架：标题行 + 内容。
 * 原 ui-detail-inspector.module.css 的 .ui-wb-card* 规则已迁入 utility；
 * className 仍保留给页面测试与兼容选择器。
 */
export function RunCard({ title, side, chip, dot, children, className, ariaLabel }: RunCardProps) {
  return (
    <section className={cx('flex min-w-0 flex-col gap-3 overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-3', className)} aria-label={ariaLabel}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex min-w-0 items-center gap-2 text-[13px] font-bold text-[var(--srf-text)]">
          {dot ? <span className="h-2 w-2 flex-none rounded-full bg-[var(--srf-result-passed)]" aria-hidden="true" /> : null}
          {title}
          {chip ? <span className={runCardChipClass}>{chip}</span> : null}
        </div>
        {side ? <div className="inline-flex items-center gap-1.5 text-[11px] text-[var(--srf-text-muted)]">{side}</div> : null}
      </header>
      {children}
    </section>
  )
}
