import { InputNumber } from 'antd'

export function PerfNumericField({
  label,
  value,
  min = 1,
  required = false,
  disabled = false,
  className = '',
  onChange,
}: {
  label: string
  value: number
  min?: number
  required?: boolean
  disabled?: boolean
  className?: string
  onChange: (value: number) => void
}) {
  return <label className={`grid gap-1 text-xs text-app-surface-text-muted ${className}`}>
    <span>{label}{required ? <span className="text-app-request-error-text"> *</span> : null}</span>
    <InputNumber
      className="w-full"
      min={min}
      precision={0}
      value={value}
      disabled={disabled}
      onChange={next => onChange(typeof next === 'number' ? next : value)}
    />
  </label>
}
