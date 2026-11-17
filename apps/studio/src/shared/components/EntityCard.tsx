import { useId, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import { isInteractiveCardTarget } from '@/shared/utils/cardNavigation'
import { cx } from '@/shared/utils/cx'
import '@/shared/styles/entity-card.css'

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
    <article className={cx('entity-card', className)} aria-labelledby={resolvedTitleId} onClick={onOpen ? handleCardClick : undefined}>
      <div className="entity-card-main">
        <div className="entity-card-title-row">
          <TitleTag className="entity-card-title" id={resolvedTitleId}>{title}</TitleTag>
          {status}
        </div>
        {children}
        {meta && meta.length > 0 ? (
          <dl className="entity-card-meta">
            {meta.map((item, index) => (
              <div key={index}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
      <footer className="entity-card-foot">
        <div className={cx('entity-card-note', footerNoteClassName)}>{footerNote}</div>
        <div
          className={cx('entity-card-actions', actionsClassName)}
          onClick={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
        >
          {actions}
        </div>
      </footer>
    </article>
  )
}
