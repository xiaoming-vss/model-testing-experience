import { Typography } from 'antd'

export const { Text, Title } = Typography

export type UiTemplateFieldKey = 'locatorValue' | 'operationValue'

export type CaseImportMode = 'upload' | 'editor'

export const UI_TEMPLATE_FIELD_LABELS: Record<UiTemplateFieldKey, string> = {
  locatorValue: '定位值',
  operationValue: '操作值',
}

export function isYamlFileName(fileName: string) {
  return /\.(yaml|yml)$/i.test(fileName.trim())
}
