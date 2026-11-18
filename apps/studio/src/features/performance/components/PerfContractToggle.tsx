import { Segmented } from 'antd'

export type PerfContractView = 'visual' | 'yaml'

const CONTRACT_VIEW_OPTIONS: { value: PerfContractView; label: string }[] = [
  { value: 'visual', label: '可视化' },
  { value: 'yaml', label: 'YAML' },
]

export function PerfContractToggle({
  value,
  onChange,
}: {
  value: PerfContractView
  onChange: (value: PerfContractView) => void
}) {
  return <Segmented
    size="small"
    aria-label="用例编辑视图"
    value={value}
    options={CONTRACT_VIEW_OPTIONS}
    onChange={next => onChange(next as PerfContractView)}
  />
}
