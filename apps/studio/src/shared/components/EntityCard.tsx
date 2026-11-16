import { useId, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import { isInteractiveCardTarget } from '@/shared/utils/cardNavigation'
import '@/shared/styles/entity-card.css'

export type EntityCardMetaItem = {
  label: ReactNode
  value: ReactNode
}

export type EntityCardProps = {
  title: ReactNode
  /** 需要与页面其他 aria-labelledby 对齐时传入；默认生成稳定 id。 */
  titleId?: string
  status?: ReactNode
  meta?: readonly EntityCardMetaItem[]
  footerNote?: ReactNode
  actions?: ReactNode
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
  titleId,
  status,
  meta,
  footerNote,
  actions,
  onOpen,
  children,
}: EntityCardProps) {
  const generatedTitleId = useId()
  const resolvedTitleId = titleId ?? `entity-card-title-${generatedTitleId}`

  function handleCardClick(event: ReactMouseEvent<HTMLElement>) {
    if (!onOpen || isInteractiveCardTarget(event.target)) return
    onOpen()
  }

  return (
    <article className="entity-card" aria-labelledby={resolvedTitleId} onClick={onOpen ? handleCardClick : undefined}>
      <div className="entity-card-main">
        <div className="entity-card-title-row">
          <h2 className="entity-card-title" id={resolvedTitleId}>{title}</h2>
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
        <span className="entity-card-note">{footerNote}</span>
        <div
          className="entity-card-actions"
          onClick={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
        >
          {actions}
        </div>
      </footer>
    </article>
  )
}
