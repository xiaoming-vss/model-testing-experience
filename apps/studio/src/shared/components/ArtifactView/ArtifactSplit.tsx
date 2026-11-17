import { Empty } from 'antd'
import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'

export function ArtifactSplit({ listLabel, detailLabel, list, detail, className, listMaxHeight = '200' }: {
  listLabel: string
  detailLabel: string
  list: ReactNode
  detail: ReactNode
  className?: string
  listMaxHeight?: '190' | '200'
}) {
  return <div className={cx('flex min-h-0 flex-1 gap-3 max-narrow:flex-col', className)}>
    <aside aria-label={listLabel} className={cx('min-h-0 w-[330px] flex-none overflow-auto rounded-[9px] border border-app-surface-border bg-app-surface-hover p-1.5 max-narrow:w-full', listMaxHeight === '190' ? 'max-narrow:max-h-[190px]' : 'max-narrow:max-h-[200px]')}>
      {list}
    </aside>
    <section aria-label={detailLabel} className="min-h-0 min-w-0 flex-1 overflow-auto rounded-[9px] border border-app-surface-border bg-app-surface p-[18px] max-narrow:min-h-[320px]">
      {detail}
    </section>
  </div>
}

export function ArtifactEmpty({ description, className }: { description: ReactNode; className?: string }) {
  return <div className={cx('grid min-h-0 flex-1 place-items-center', className)}>
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} />
  </div>
}
