import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'
import styles from '@/shared/styles/run-view.module.css'

const activeToneClass = {
  accent: 'bg-app-accent-selection',
  danger: 'bg-app-danger-surface-soft',
  warn: 'bg-app-status-warning-bg',
}

const idToneClass = {
  accent: 'text-app-accent',
  danger: 'text-app-request-error-text',
  warn: 'text-app-status-warning-text',
}

export function ArtifactListRow({ id, title, meta, active, activeTone = 'accent', idTone = 'accent', trailing, children, onClick, className }: {
  id?: ReactNode
  title: ReactNode
  meta?: ReactNode
  active?: boolean
  activeTone?: 'accent' | 'danger' | 'warn'
  idTone?: 'accent' | 'danger' | 'warn'
  trailing?: ReactNode
  children?: ReactNode
  onClick: () => void
  className?: string
}) {
  return <button
    type="button"
    className={cx(
      'flex w-full items-start gap-[7px] rounded-[6px] border-0 p-2 text-left',
      active ? activeToneClass[activeTone] : 'bg-transparent hover:bg-app-surface',
      styles.row,
      className,
    )}
    onClick={onClick}
  >
    {id !== undefined && id !== null ? <span className={cx('flex-none pt-px font-mono text-[9.5px]', idToneClass[idTone])}>{id}</span> : null}
    <span className="flex min-w-0 flex-1 flex-col items-start gap-1">
      <span className="line-clamp-2 text-[11.5px] leading-normal text-app-surface-text [overflow-wrap:anywhere]">{title}</span>
      {meta ? <span className="text-[9.5px] leading-tight text-app-surface-text-muted">{meta}</span> : null}
      {children}
    </span>
    {trailing ? <span className="flex-none">{trailing}</span> : null}
  </button>
}
