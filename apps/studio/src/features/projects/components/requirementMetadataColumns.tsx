import type { TableProps } from 'antd'
import type { Requirement } from '@/features/requirements/types'
import { RequirementCodeSummary, RequirementCreatedTime } from './RequirementMetadata'

export function requirementMetadataColumns<T extends Requirement>(): NonNullable<TableProps<T>['columns']> {
  return [
    { title: '代码绑定', key: 'codeBindings', width: 240, render: (_, requirement) => <RequirementCodeSummary requirement={requirement} /> },
    { title: '创建时间', key: 'createdAt', width: 170, render: (_, requirement) => <RequirementCreatedTime requirement={requirement} /> },
  ]
}
