import { Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import type { Requirement } from '@/features/requirements/types'
import { formatTime, pickCreatedAt } from '@/utils/format'

const { Text } = Typography

export function requirementMetadataColumns<T extends Requirement>(): NonNullable<TableProps<T>['columns']> {
  return [
    { title: '代码绑定', key: 'codeBindings', width: 240, render: (_, requirement) => {
      const bindings = requirement.codeBindings
      if (!bindings) return <Text type="secondary">—</Text>
      if (!bindings.length) return <Text type="secondary">未绑定</Text>
      const labels = bindings.map(binding => `${binding.repository}${binding.branch ? ` · ${binding.branch}` : ''}`)
      return <Tooltip title={<>{labels.map((label, index) => <div key={index}>{label}</div>)}</>}>
        <div className="requirements-list-wrap" tabIndex={0}>{labels[0]}{labels.length > 1 ? `（共 ${labels.length} 项）` : ''}</div>
      </Tooltip>
    } },
    { title: '创建时间', key: 'createdAt', width: 170, render: (_, requirement) => {
      const time = formatTime(pickCreatedAt(requirement))
      return <Tooltip title={time}><Text type="secondary">{time.replace(/:\d{2}$/, '')}</Text></Tooltip>
    } },
  ]
}
