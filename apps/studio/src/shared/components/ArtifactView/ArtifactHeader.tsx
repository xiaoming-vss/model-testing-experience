import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'

const valueTone: Record<'default' | 'ok' | 'warn' | 'danger', string> = {
  default: 'text-app-surface-text',
  ok: 'text-app-status-approved-text',
  warn: 'text-app-status-warning-text',
  danger: 'text-app-request-error-text',
}

const dotTone: Record<'ok' | 'warn' | 'danger' | 'muted' | 'accent', string> = {
  ok: 'bg-app-status-approved-text',
  warn: 'bg-app-status-warning-text',
  danger: 'bg-app-request-error-text',
  muted: 'bg-app-surface-text-muted',
  accent: 'bg-app-accent',
}

export function ArtifactHeader({ children, hint, className, hintClassName }: {
  children: ReactNode
  hint?: ReactNode
  className?: string
  hintClassName?: string
}) {
  return <header className={cx('flex flex-none flex-wrap items-center gap-[18px] rounded-[10px] border border-app-surface-border bg-app-surface-hover px-[14px] py-2.5', className)}>
    {children}
    {hint ? <span className={cx('ml-auto text-[10.5px] text-app-surface-text-muted', hintClassName)}>{hint}</span> : null}
  </header>
}

export function ArtifactStat({ label, value, tone = 'default', trailing }: {
  label: ReactNode
  value: ReactNode
  tone?: 'default' | 'ok' | 'warn' | 'danger'
  trailing?: ReactNode
}) {
  return <div className="flex items-baseline gap-[7px] text-[10.5px] text-app-surface-text-muted">
    <span>{label}</span>
    <strong className={cx('text-xl leading-none [font-weight:720]', valueTone[tone])}>{value}</strong>
    {trailing ? <span className="[&_.ant-tag]:m-0 [&_.ant-tag]:text-[10px]">{trailing}</span> : null}
  </div>
}

export function ArtifactDivider() {
  return <span className="h-6 w-px bg-app-surface-border" aria-hidden="true" />
}

export type ArtifactBreakdownItem = {
  label: ReactNode
  value?: ReactNode
  dot?: 'ok' | 'warn' | 'danger' | 'muted' | 'accent'
}

export function ArtifactBreakdown({ items }: { items: ArtifactBreakdownItem[] }) {
  return <div className="flex flex-wrap items-center gap-[14px] text-[10.5px] text-app-surface-text-muted">
    {items.map((item, index) => <span key={index} className="inline-flex items-center gap-[5px]">
      {item.dot ? <i className={cx('size-1.5 rounded-full', dotTone[item.dot])} aria-hidden="true" /> : null}
      <span>{item.label}{item.value !== undefined ? <> {item.value}</> : null}</span>
    </span>)}
  </div>
}
