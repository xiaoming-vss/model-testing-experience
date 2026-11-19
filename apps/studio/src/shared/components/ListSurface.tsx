import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'
import { tableFooterClass } from '@/shared/utils/surfaceClasses'

export type ListSurfaceProps = {
  children: ReactNode
  toolbar?: ReactNode
  notices?: ReactNode
  footer?: ReactNode
  className?: string
  bodyClassName?: string
  scrollClassName?: string
  /** 页面兼容页脚类，叠加在共享 table-footer 之后。 */
  footerClassName?: string
  scrollAriaBusy?: boolean
  ariaLabel?: string
  /** 外部标题 id；与 ariaLabel 二选一。 */
  ariaLabelledBy?: string
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
  footerClassName,
  scrollAriaBusy,
  ariaLabel,
  ariaLabelledBy,
}: ListSurfaceProps) {
  return (
    <section className={cx('tp-board tp-list-panel', className)} aria-label={ariaLabel} aria-labelledby={ariaLabelledBy}>
      {toolbar}
      {notices}
      <div className={cx('tp-list-body', bodyClassName)}>
        <div className={cx('tp-list-scroll', scrollClassName)} aria-busy={scrollAriaBusy}>
          {children}
        </div>
        {footer ? <div className={cx('table-footer', tableFooterClass, footerClassName)}>{footer}</div> : null}
      </div>
    </section>
  )
}
