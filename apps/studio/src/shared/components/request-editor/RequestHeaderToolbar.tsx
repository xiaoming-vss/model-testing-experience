import type { ReactNode } from 'react'

export type HeaderPreset = { label: string; key: string; value: string }


export function RequestHeaderToolbar({ presets, onAdd, disabled, actions }: {
  presets: readonly HeaderPreset[]
  onAdd: (preset: HeaderPreset) => void
  disabled?: boolean
  actions?: ReactNode
}) {
  return <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--srf-card-border)] bg-[var(--srf-hover)] px-4 py-2">
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-[11px] font-medium leading-4 text-[var(--srf-text-muted)]">快捷注入:</span>
      {presets.map(preset => <button key={preset.label} type="button" disabled={disabled}
        className="inline-flex cursor-pointer items-center rounded-[4px] border border-[var(--srf-card-border)] bg-[var(--srf-card)] px-2 py-0.5 text-[11px] leading-4 text-[var(--srf-chip-text)] transition-colors hover:border-[var(--srf-accent-border)] hover:bg-[var(--srf-accent-soft)] hover:text-[var(--srf-accent-strong)] disabled:cursor-not-allowed disabled:opacity-45"
        onClick={() => onAdd(preset)}><span className="mr-1 font-bold text-[var(--srf-accent)]">+</span>{preset.label}</button>)}
    </div>
    {actions}
  </div>
}
