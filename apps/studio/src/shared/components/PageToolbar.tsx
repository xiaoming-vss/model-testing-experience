import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'

export type PageToolbarProps = {
  /** 页面标题块；由调用方决定标题层级、计数和描述。 */
  title: ReactNode
  actions?: ReactNode
  className?: string
  ariaLabel?: string
}

/** 列表页顶部工具栏：左侧标题块 + 右侧操作，表面与断点由共享 CSS 提供。 */
export function PageToolbar({ title, actions, className, ariaLabel }: PageToolbarProps) {
  return (
    <section className={cx('tp-page-toolbar', className)} aria-label={ariaLabel}>
      <div className="tp-page-toolbar-main">{title}</div>
      {actions ? <div className="tp-page-toolbar-actions">{actions}</div> : null}
    </section>
  )
}
