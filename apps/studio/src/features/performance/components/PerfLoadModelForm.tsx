import {
  DashboardOutlined,
  LineChartOutlined,
  RiseOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { Select } from 'antd'
import type { ReactNode } from 'react'
import {
  perfLoadFormError,
  type PerfLoadFormValues,
  type PerfLoadModel,
} from '../utils/perfLoadModel'
import { PerfNumericField } from './PerfNumericField'
import { PerfStagedLoadFields } from './PerfStagedLoadFields'

const LOAD_OPTIONS: { model: PerfLoadModel; name: string; description: string; icon: ReactNode }[] = [
  { model: 'vus', name: '固定并发', description: '固定 VU 数，持续运行', icon: <DashboardOutlined /> },
  { model: 'arrival_rate', name: '固定到达率', description: '按每秒迭代次数到达', icon: <RiseOutlined /> },
  { model: 'request_rate', name: '固定请求速率', description: '按每秒请求数到达', icon: <ThunderboltOutlined /> },
  { model: 'staged_vus', name: '阶段负载', description: '按阶段配置 VUs 曲线', icon: <LineChartOutlined /> },
]

export function PerfLoadModelForm({
  value,
  stepCount,
  disabled = false,
  onChange,
}: {
  value: PerfLoadFormValues
  stepCount: number
  disabled?: boolean
  onChange: (value: PerfLoadFormValues) => void
}) {
  const error = perfLoadFormError(value, stepCount)
  const patch = (next: Partial<PerfLoadFormValues>) => onChange({ ...value, ...next })

  return <section className="px-4 py-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="inline-flex items-center gap-2 text-xs font-semibold text-app-surface-text"><DashboardOutlined />性能参数</span>
      <span className="text-xs text-app-surface-text-muted">每条用例一个 k6 负载模型</span>
    </div>
    <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {LOAD_OPTIONS.map(option => {
        const selected = value.model === option.model
        return <button
          key={option.model}
          type="button"
          aria-pressed={selected}
          disabled={disabled}
          onClick={() => patch({ model: option.model })}
          className={`flex min-h-14 items-start gap-2 rounded-lg border px-2.5 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
            selected
              ? 'border-app-accent-border bg-app-accent-surface'
              : 'border-app-surface-border bg-app-surface hover:bg-app-surface-hover'
          }`}
        >
          <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-md text-[13px] ${
            selected ? 'bg-app-surface text-app-accent' : 'bg-app-surface-hover text-app-surface-text-muted'
          }`}>{option.icon}</span>
          <span className="grid min-w-0 gap-0.5">
            <span className="text-[11px] font-semibold leading-4 text-app-surface-text">{option.name}</span>
            <span className="text-[10px] leading-[14px] text-app-surface-text-muted">{option.description}</span>
          </span>
        </button>
      })}
    </div>

    {value.model === 'vus' ? <div className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
      <PerfNumericField label="VUs" required value={value.vus} disabled={disabled} onChange={vus => patch({ vus })} />
      <PerfNumericField label="持续时间（秒）" required value={value.durationSeconds} disabled={disabled} onChange={durationSeconds => patch({ durationSeconds })} />
      <PerfNumericField label="爬坡时间（秒）" min={0} value={value.rampUpSeconds} disabled={disabled} onChange={rampUpSeconds => patch({ rampUpSeconds })} />
      <PerfNumericField label="下降时间（秒）" min={0} value={value.rampDownSeconds} disabled={disabled} onChange={rampDownSeconds => patch({ rampDownSeconds })} />
    </div> : value.model === 'staged_vus' ? <PerfStagedLoadFields
      value={value}
      disabled={disabled}
      onChange={patch}
    /> : <div className="mt-4 grid grid-cols-2 gap-3 narrow:grid-cols-3 xl:grid-cols-5">
      <PerfNumericField
        label={value.model === 'arrival_rate' ? '到达速率' : '请求速率'}
        required
        value={value.rate}
        disabled={disabled}
        onChange={rate => patch({ rate })}
      />
      <label className="grid gap-1 text-xs text-app-surface-text-muted">
        <span>时间单位</span>
        <Select
          className="w-full"
          value={value.timeUnit}
          disabled={disabled}
          options={[{ value: '1s', label: '每秒' }, { value: '1m', label: '每分钟' }]}
          onChange={timeUnit => patch({ timeUnit })}
        />
      </label>
      <PerfNumericField label="持续时间（秒）" required value={value.durationSeconds} disabled={disabled} onChange={durationSeconds => patch({ durationSeconds })} />
      <PerfNumericField label="预分配 VUs" value={value.preAllocatedVUs} disabled={disabled} onChange={preAllocatedVUs => patch({ preAllocatedVUs })} />
      <PerfNumericField label="最大 VUs" value={value.maxVUs} disabled={disabled} onChange={maxVUs => patch({ maxVUs })} />
    </div>}

    {error ? <div className="mt-2 text-xs text-app-request-error-text">{error}</div> : null}
  </section>
}
