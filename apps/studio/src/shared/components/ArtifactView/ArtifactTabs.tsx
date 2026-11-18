import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'
import styles from '@/shared/styles/run-view.module.css'

export type ArtifactTabTone = 'neutral' | 'ok' | 'warn' | 'danger'

export type ArtifactTabItem<T extends string = string> = {
  key: T
  label: ReactNode
  count?: ReactNode
  tone?: ArtifactTabTone
  dot?: ArtifactTabTone
}

const dotTone: Record<ArtifactTabTone, string> = {
  neutral: 'bg-app-surface-text-muted',
  ok: 'bg-app-status-approved-text',
  warn: 'bg-app-status-warning-text',
  danger: 'bg-app-request-error-text',
}

const countTone: Record<ArtifactTabTone, string> = {
  neutral: 'bg-app-surface-hover text-app-surface-text-muted',
  ok: 'bg-app-surface-hover text-app-surface-text-muted',
  warn: 'bg-app-status-warning-bg text-app-status-warning-text',
  danger: 'bg-app-danger-surface-soft text-app-request-error-text',
}

export function ArtifactTabs<T extends string>({ ariaLabel, tabs, active, onChange }: {
  ariaLabel: string
  tabs: readonly ArtifactTabItem<T>[]
  active: T
  onChange: (key: T) => void
}) {
  return <div className="flex flex-none items-stretch gap-0.5 border-b border-app-surface-border px-1.5" role="tablist" aria-label={ariaLabel}>
    {tabs.map((tab) => {
      const isActive = tab.key === active
      return <button
        key={tab.key}
        type="button"
        role="tab"
        aria-selected={isActive}
        className={cx(
          'relative inline-flex h-[38px] items-center gap-1.5 border-0 bg-transparent px-2.5 text-xs text-app-surface-text-muted hover:text-app-surface-text',
          isActive && 'text-app-surface-text',
          isActive && styles.tabActive,
        )}
        onClick={() => onChange(tab.key)}
      >
        {tab.label}
        {tab.dot ? <span className={cx('size-[7px] rounded-full', dotTone[tab.dot])} aria-hidden="true" /> : null}
        {tab.count !== undefined && tab.count !== null
          ? <span className={cx('inline-grid h-[18px] min-w-[18px] place-items-center rounded-full px-[5px] text-[9.5px] [font-weight:650]', countTone[tab.tone ?? 'neutral'])}>{tab.count}</span>
          : null}
      </button>
    })}
  </div>
}
