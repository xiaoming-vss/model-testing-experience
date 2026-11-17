import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'

export type ListSurfaceProps = {
  children: ReactNode
  toolbar?: ReactNode
  notices?: ReactNode
  footer?: ReactNode
  className?: string
  bodyClassName?: string
  scrollClassName?: string
  scrollAriaBusy?: boolean
  ariaLabel?: string
}

/**
 * 列表页唯一板面：工具栏 + 提示 + 可滚动内容 + 固定分页。
 * 页面只传内容和兼容类，不再各自拼 tp-board / tp-list-panel / tp-list-body。
 */
export function ListSurface({
  children,
  toolbar,
  notices,
  footer,
  className,
  bodyClassName,
  scrollClassName,
  scrollAriaBusy,
  ariaLabel,
}: ListSurfaceProps) {
  return (
    <section className={cx('tp-board tp-list-panel', className)} aria-label={ariaLabel}>
      {toolbar}
      {notices}
      <div className={cx('tp-list-body', bodyClassName)}>
        <div className={cx('tp-list-scroll', scrollClassName)} aria-busy={scrollAriaBusy}>
          {children}
        </div>
        {footer ? <div className="table-footer">{footer}</div> : null}
      </div>
    </section>
  )
}
