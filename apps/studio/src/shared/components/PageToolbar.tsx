import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'

export type PageToolbarProps = {
  /** 页面标题块；由调用方决定标题层级、计数和描述。 */
  title: ReactNode
  actions?: ReactNode
  className?: string
  ariaLabel?: string
}

/** 列表页顶部工具栏：左侧标题块 + 右侧操作，表面与断点由共享 utility 提供。 */
export function PageToolbar({ title, actions, className, ariaLabel }: PageToolbarProps) {
  return (
    <section className={cx('tp-page-toolbar flex min-w-0 flex-none basis-[56px] flex-wrap items-center justify-between gap-4 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-4 max-[900.01px]:min-h-[56px] max-[900.01px]:basis-auto max-[900.01px]:py-2.5', className)} aria-label={ariaLabel}>
      <div className="tp-page-toolbar-main flex min-w-0 flex-[1_1_320px] flex-wrap items-center gap-2">{title}</div>
      {actions ? <div className="tp-page-toolbar-actions ml-auto flex flex-wrap items-center gap-2">{actions}</div> : null}
    </section>
  )
}
