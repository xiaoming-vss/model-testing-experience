import { Empty } from 'antd'
import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'

export type ListEmptyStateProps = {
  description: ReactNode
  image?: ReactNode
  children?: ReactNode
  className?: string
}

/** 列表页空态／加载态的统一占位：220px 高、居中，动作作为 Empty children。 */
export function ListEmptyState({ description, image, children, className }: ListEmptyStateProps) {
  return (
    <div className={cx('grid min-h-[220px] place-items-center', className)}>
      <Empty image={image} description={description}>{children}</Empty>
    </div>
  )
}
