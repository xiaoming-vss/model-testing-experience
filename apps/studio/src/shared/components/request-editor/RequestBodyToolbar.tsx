import { CompressOutlined, FormatPainterOutlined } from '@ant-design/icons'
import type { ReactNode } from 'react'

type Option<T extends string> = { label: string; value: T }

type Props<T extends string> = {
  options: readonly Option<T>[]
  value: T
  onChange: (value: T) => void
  disabled?: boolean
  json: boolean
  onFormat: () => void
  onCompress: () => void
  variableControl?: ReactNode
  validity?: ReactNode
}

const actionClass = 'inline-flex cursor-pointer items-center gap-1 rounded-[4px] border-0 bg-[var(--srf-chip)] px-2 py-1 text-[12px] leading-4 text-[var(--srf-text)] transition-colors hover:bg-[var(--srf-accent-soft)] disabled:cursor-not-allowed disabled:opacity-45'

export function RequestBodyToolbar<T extends string>({ options, value, onChange, disabled, json, onFormat, onCompress, variableControl, validity }: Props<T>) {
  return <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--srf-card-border)] bg-[var(--srf-hover)] px-4 py-1">
    <div className="flex flex-wrap items-center gap-1" role="tablist" data-tab-motion-scoped aria-label="请求体类型">
      {options.map(option => <button key={option.value} type="button" role="tab" aria-selected={option.value === value}
        disabled={disabled} className={`cursor-pointer rounded-[4px] border-0 px-2 py-1 text-[12px] leading-4 transition-colors hover:text-[var(--srf-text)] disabled:cursor-not-allowed disabled:opacity-45${option.value === value ? ' bg-[var(--srf-card)] font-semibold text-[var(--srf-accent)]' : ' bg-transparent text-[var(--srf-text-secondary)]'}`}
        onClick={() => onChange(option.value)}>{option.label}</button>)}
    </div>
    <div className="flex flex-wrap items-center gap-1">
      <button type="button" className={actionClass} disabled={disabled || !json} onClick={onFormat}><FormatPainterOutlined aria-hidden="true" />格式化代码</button>
      <button type="button" className={actionClass} disabled={disabled || !json} onClick={onCompress}><CompressOutlined aria-hidden="true" />压缩</button>
      {variableControl}
      {validity}
    </div>
  </div>
}

export const requestBodyVariableClass = 'inline-flex cursor-pointer items-center gap-1 rounded-[4px] border-0 bg-transparent px-2 py-1 text-[12px] leading-4 text-[var(--srf-accent)] transition-colors hover:bg-[var(--srf-accent-soft)] disabled:cursor-not-allowed disabled:opacity-45'
