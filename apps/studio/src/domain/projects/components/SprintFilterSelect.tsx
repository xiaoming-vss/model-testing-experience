import { Select } from 'antd'

type SprintFilterSelectProps = {
  value: string
  options: Array<{ label: string; value: string }>
  loading?: boolean
  onChange: (value: string) => void
  ariaLabel?: string
  className?: string
}

/** 列表页共用的迭代筛选控件；范围由页面自己持有，不再跟随顶部全局选择。 */
export function SprintFilterSelect({
  value,
  options,
  loading = false,
  onChange,
  ariaLabel = '筛选迭代',
  className = '',
}: SprintFilterSelectProps) {
  return (
    <div className={`api-filter-field ${className}`.trim()}>
      <span className="whitespace-nowrap text-xs font-semibold leading-[18px] text-[var(--srf-text-muted)]">迭代</span>
      <Select
        className="api-filter-select business-filter-select"
        aria-label={ariaLabel}
        value={value || undefined}
        options={options}
        loading={loading}
        disabled={options.length === 0}
        placeholder={loading ? '加载中' : '暂无迭代'}
        onChange={onChange}
      />
    </div>
  )
}
