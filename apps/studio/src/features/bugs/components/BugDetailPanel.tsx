import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'

/** Bug 详情页统一卡片表面：外边距、圆角、描边与内边距。 */
export function BugDetailPanel({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx('bug-detail-panel mb-5 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-5', className)}>{children}</section>
}
