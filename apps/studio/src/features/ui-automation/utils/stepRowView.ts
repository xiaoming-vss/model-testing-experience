import {
  getUiStepFieldMeta,
  requiresUiStepLocator,
  usesUiStepComparator,
  usesUiStepOperation
} from '@/features/ui-automation/config/stepConfig'
import type { UiTestStepFormValue } from '@/features/ui-automation/utils/uiTestCaseEditor'

/*
 * 步骤行的展示推导：这一行要显示哪些字段、字段标题怎么写、折叠时那行摘要怎么拼。
 * 这些判断原来长在 UiStepEditor 的 map 回调里（每行一份局部常量），抽出来是为了让组件
 * 那一层只负责渲染，同时把「什么时候该亮出定位值 / 操作值」这类规则变成可单测的纯函数。
 */

export type UiStepRowView = {
  keyword: string
  requiresLocator: boolean
  usesComparator: boolean
  usesOperation: boolean
  showLocatorFields: boolean
  showOperationField: boolean
  showLocatorTypeField: boolean
  pairLocatorAndOperation: boolean
  operationFieldLabel: string
  operationFieldPlaceholder: string
  locatorFieldHint: string
  operationFieldHint: string
  locatorValueFieldClass: string
  operationValueFieldClass: string
  /** 折叠状态下的一行摘要。 */
  summary: string
}

export function buildUiStepRowView(step?: UiTestStepFormValue): UiStepRowView {
  const keyword = step?.keyword?.trim() ?? ''
  const meta = getUiStepFieldMeta(keyword)
  const requiresLocator = requiresUiStepLocator(keyword)
  const usesComparator = usesUiStepComparator(keyword)
  const usesOperation = usesUiStepOperation(keyword)
  const showLocatorFields = requiresLocator || Boolean(step?.locatorType?.trim() || step?.locatorValue?.trim())
  const showOperationField = usesOperation || Boolean(step?.operationValue?.trim())
  const showLocatorTypeField = requiresLocator || Boolean(step?.locatorType?.trim())
  const pairLocatorAndOperation = showLocatorFields && showOperationField

  return {
    keyword,
    requiresLocator,
    usesComparator,
    usesOperation,
    showLocatorFields,
    showOperationField,
    showLocatorTypeField,
    pairLocatorAndOperation,
    operationFieldLabel: meta.operationLabel ? `操作值（${meta.operationLabel}）` : '操作值',
    operationFieldPlaceholder: meta.operationPlaceholder || '例如：tester',
    locatorFieldHint: meta.locatorHint || (requiresLocator ? '当前关键字通常需要定位器。' : ''),
    operationFieldHint: meta.operationHint || '',
    locatorValueFieldClass: pairLocatorAndOperation ? 'ui-test-case-step-field-half' : 'ui-test-case-step-field-wide',
    operationValueFieldClass: pairLocatorAndOperation
      ? 'ui-test-case-step-field-half'
      : usesComparator
        ? 'ui-test-case-step-field-half'
        : 'ui-test-case-step-field-wide',
    summary: [
      keyword || '未设置关键字',
      requiresLocator ? step?.locatorType?.trim() || '待设定位' : step?.locatorType?.trim() || '无需定位',
      usesComparator ? step?.comparator?.trim() || '待设比较' : '',
      step?.enabled === false ? '已禁用' : '已启用',
    ]
      .filter(Boolean)
      .join(' · '),
  }
}
