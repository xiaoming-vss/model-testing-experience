import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'
import styles from '@/shared/styles/run-view.module.css'

function ArtifactCountBadge({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx('inline-grid h-[17px] min-w-[17px] place-items-center rounded-full bg-app-surface-hover px-[5px] text-[9.5px] font-medium text-app-surface-text-muted', className)}>{children}</span>
}

export function ArtifactSectionHead({ title, count, action, as: Heading = 'h4', spacing = 'default', className }: {
  title: ReactNode
  count?: ReactNode
  action?: ReactNode
  as?: 'h3' | 'h4'
  spacing?: 'default' | 'tight'
  className?: string
}) {
  return <Heading className={cx('flex items-center gap-1.5 text-[11px] [font-weight:650] text-app-surface-text', spacing === 'tight' ? 'mb-1' : 'mb-[7px]', className)}>
    {title}
    {count !== undefined && count !== null ? <ArtifactCountBadge>{count}</ArtifactCountBadge> : null}
    {action ? <span className="ml-auto">{action}</span> : null}
  </Heading>
}

const badgeToneClass = {
  accent: 'bg-app-accent-surface text-app-accent',
  muted: 'bg-app-surface-hover text-app-surface-text-muted',
  danger: 'bg-app-danger-surface-soft text-app-request-error-text',
  warn: 'bg-app-status-warning-bg text-app-status-warning-text',
}

export function ArtifactKicker({ badge, badgeTone = 'accent', children, className }: {
  badge: ReactNode
  badgeTone?: 'accent' | 'muted' | 'danger' | 'warn'
  children?: ReactNode
  className?: string
}) {
  return <div className={cx('flex flex-wrap items-center gap-1.5 text-[10px] text-app-surface-text-muted', styles.kicker, className)}>
    <span className={cx('rounded-[4px] px-1.5 py-px text-[9.5px] [font-weight:650]', badgeToneClass[badgeTone])}>{badge}</span>
    {children}
  </div>
}

export function ArtifactDetailTitle({ children, count, className }: { children: ReactNode; count?: ReactNode; className?: string }) {
  return <h2 className={cx('mt-2.5 flex items-baseline gap-2 text-base leading-normal text-app-surface-text [overflow-wrap:anywhere]', className)}>
    {children}
    {count !== undefined && count !== null ? <ArtifactCountBadge>{count}</ArtifactCountBadge> : null}
  </h2>
}

export function ArtifactField({ label, value, labelWidth = 'sm', tone = 'default', className }: {
  label: ReactNode
  value: ReactNode
  labelWidth?: 'sm' | 'md'
  tone?: 'default' | 'question'
  className?: string
}) {
  const question = tone === 'question'
  return <div className={cx(
    'flex items-start gap-2.5',
    question && 'rounded-[7px] border border-app-status-warning-border bg-app-status-warning-bg px-[10px] py-[9px]',
    className,
  )}>
    <span className={cx(
      'flex-none text-[10px] leading-[1.7] text-app-surface-text-muted',
      labelWidth === 'md' ? 'min-w-[70px]' : 'min-w-11',
      question && 'text-app-status-warning-text',
    )}>{label}</span>
    <p className={cx('m-0 text-[11.5px] leading-[1.7] text-app-surface-text [overflow-wrap:anywhere]', question && 'font-semibold')}>{value || '未记录'}</p>
  </div>
}

export function ArtifactRefChips({ title, values, resolve, className }: {
  title: ReactNode
  values: string[]
  resolve?: (id: string) => string | undefined
  className?: string
}) {
  if (!values.length) return null
  return <section className={className}>
    <ArtifactSectionHead title={title} count={values.length} />
    <div className="flex flex-wrap gap-[5px]">
      {values.map((id) => {
        const label = resolve?.(id)
        return <span key={id} className="max-w-full rounded-[5px] border border-app-surface-border bg-app-surface-hover px-1.5 py-[3px] text-[10.5px] leading-[1.4] text-app-surface-text [overflow-wrap:anywhere]">{label ? `${id} ${label}` : id}</span>
      })}
    </div>
  </section>
}

export function ArtifactEvidence({ title = '材料依据', count, emptyText = '暂无材料依据', children, className }: {
  title?: ReactNode
  count: number
  emptyText?: ReactNode
  children?: ReactNode
  className?: string
}) {
  return <section className={cx('flex flex-col gap-1.5', className)} aria-label={typeof title === 'string' ? title : undefined}>
    <ArtifactSectionHead title={title} count={count} />
    {count
      ? <div className="flex flex-col gap-1.5">{children}</div>
      : <p className="m-0 text-[10.5px] text-app-surface-text-muted">{emptyText}</p>}
  </section>
}

export function ArtifactEvidenceItem({ source, locator, children, className }: {
  source: ReactNode
  locator?: ReactNode
  children: ReactNode
  className?: string
}) {
  return <article className={cx('rounded-[6px] border border-app-surface-border border-l-2 border-l-app-accent bg-app-surface-hover px-[9px] py-2', className)}>
    <div className="mb-1 flex flex-wrap items-center gap-[5px] text-[10px] text-app-surface-text-muted">
      <strong className="font-semibold text-app-surface-text">{source}</strong>
      {locator ? <span>{locator}</span> : null}
    </div>
    {children}
  </article>
}

export function ArtifactEvidenceMissing({ children }: { children: ReactNode }) {
  return <div className="rounded-[6px] border border-dashed border-app-surface-border px-[9px] py-2 text-[10.5px] text-app-surface-text-muted">{children}</div>
}
