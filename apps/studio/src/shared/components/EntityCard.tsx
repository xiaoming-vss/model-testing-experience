import { useId, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import { isInteractiveCardTarget } from '@/shared/utils/cardNavigation'
import { cx } from '@/shared/utils/cx'
import styles from '@/shared/styles/entity-card.module.css'

export type EntityCardMetaItem = {
  label: ReactNode
  value: ReactNode
}

export type EntityCardProps = {
  title: ReactNode
  /** 页面沿用的兼容类或状态修饰类；卡片表面仍由 entity-card 提供。 */
  className?: string
  /** 标题层级跟随所在页面的标题结构；默认 h2。 */
  titleAs?: 'h2' | 'h3'
  /** 需要与页面其他 aria-labelledby 对齐时传入；默认生成稳定 id。 */
  titleId?: string
  status?: ReactNode
  meta?: readonly EntityCardMetaItem[]
  footerNote?: ReactNode
  footerNoteClassName?: string
  actions?: ReactNode
  actionsClassName?: string
  /** 整块卡片点击进入详情；标题链接的键盘路径由调用方提供。 */
  onOpen?: () => void
  children: ReactNode
}

/**
 * 列表页的实体卡片骨架：标题行（可带状态）+ 主体 + 两列 meta + footer 操作。
 * 尺寸与需求 / 迭代卡片一致；页面只负责主体内容与操作，不再各写一套卡片表面。
 */
export function EntityCard({
  title,
  className,
  titleAs = 'h2',
  titleId,
  status,
  meta,
  footerNote,
  footerNoteClassName,
  actions,
  actionsClassName,
  onOpen,
  children,
}: EntityCardProps) {
  const generatedTitleId = useId()
  const resolvedTitleId = titleId ?? `entity-card-title-${generatedTitleId}`
  const TitleTag = titleAs

  function handleCardClick(event: ReactMouseEvent<HTMLElement>) {
    if (!onOpen || isInteractiveCardTarget(event.target)) return
    onOpen()
  }

  return (
    <article className={cx('entity-card flex min-h-[218px] min-w-0 cursor-pointer flex-col rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] text-[var(--srf-text)] shadow-none transition-[border-color,box-shadow,transform] duration-[180ms] ease-[ease] hover:-translate-y-0.5 hover:border-[var(--app-glass-action-border-hover)] hover:shadow-[0_12px_28px_var(--app-service-card-shadow-hover)]', className)} aria-labelledby={resolvedTitleId} onClick={onOpen ? handleCardClick : undefined}>
      <div className="entity-card-main flex-1 px-4 pb-3 pt-[15px]">
        <div className="entity-card-title-row mb-1.5 flex min-w-0 items-center gap-2.5">
          <TitleTag className={`entity-card-title ${styles.title} m-0 min-w-0 flex-1 text-[14.5px] font-[650] leading-[22px] text-[var(--srf-text)] [&_a]:block [&_a]:overflow-hidden [&_a]:text-ellipsis [&_a]:whitespace-nowrap [&_a:hover]:underline [&_a:hover]:underline-offset-4 [&_a:focus-visible]:rounded-[2px] [&_a:focus-visible]:outline-2 [&_a:focus-visible]:outline-offset-2 [&_a:focus-visible]:outline-[var(--srf-accent)]`} id={resolvedTitleId}>{title}</TitleTag>
          {status}
        </div>
        {children}
        {meta && meta.length > 0 ? (
          <dl className="entity-card-meta m-0 grid grid-cols-2 gap-2.5 rounded-[8px] bg-[var(--srf-hover)] px-3 py-2.5 [&>div]:flex [&>div]:min-w-0 [&>div]:flex-col [&>div]:gap-0.5 [&_dt]:text-[9.5px] [&_dt]:font-normal [&_dt]:leading-[14px] [&_dt]:text-[var(--srf-text-secondary)] [&_dd]:m-0 [&_dd]:min-w-0 [&_dd]:overflow-hidden [&_dd]:text-ellipsis [&_dd]:whitespace-nowrap [&_dd]:text-[11.5px] [&_dd]:font-semibold [&_dd]:leading-[17px] [&_dd]:text-[var(--srf-text)] [&_dd]:[font-variant-numeric:tabular-nums]">
            {meta.map((item, index) => (
              <div key={index}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
      <footer className="entity-card-foot mt-auto flex min-h-[43px] items-center justify-between gap-2 px-4 pb-2.5 pt-[9px]">
        <div className={cx('entity-card-note min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[10.5px] leading-[18px] text-[var(--srf-text-secondary)]', footerNoteClassName)}>{footerNote}</div>
        <div
          className={cx('entity-card-actions flex flex-none items-center gap-0', actionsClassName)}
          onClick={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
        >
          {actions}
        </div>
      </footer>
    </article>
  )
}
