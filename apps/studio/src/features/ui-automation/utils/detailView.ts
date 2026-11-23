import { Typography } from 'antd'

export { isYamlFileName } from '@/shared/utils/caseImport'

export const { Text } = Typography

export type UiTemplateFieldKey = 'locatorValue' | 'operationValue'

export const UI_TEMPLATE_FIELD_LABELS: Record<UiTemplateFieldKey, string> = {
  locatorValue: '定位值',
  operationValue: '操作值',
}
