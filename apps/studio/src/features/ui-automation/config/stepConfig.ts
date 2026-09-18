export const uiTestKeywordOptions = [
  { label: 'open · 打开页面', value: 'open' },
  { label: 'reload · 刷新页面', value: 'reload' },
  { label: 'click · 点击元素', value: 'click' },
  { label: 'dblclick · 双击元素', value: 'dblclick' },
  { label: 'input · 输入内容', value: 'input' },
  { label: 'clear · 清空输入框', value: 'clear' },
  { label: 'press · 按键', value: 'press' },
  { label: 'wait_text · 等待文本出现', value: 'wait_text' },
  { label: 'assert_text · 断言元素文本', value: 'assert_text' },
  { label: 'assert_visible · 断言元素可见', value: 'assert_visible' },
  { label: 'assert_url · 断言当前 URL', value: 'assert_url' },
  { label: 'screenshot · 截图', value: 'screenshot' },
  { label: 'sleep · 固定等待', value: 'sleep' },
]

export const uiTestLocatorTypeOptions = [
  { label: 'css', value: 'css' },
  { label: 'xpath', value: 'xpath' },
  { label: 'text', value: 'text' },
  { label: 'placeholder', value: 'placeholder' },
  { label: 'label', value: 'label' },
  { label: 'test_id', value: 'test_id' },
  { label: 'testid', value: 'testid' },
  { label: 'role', value: 'role' },
]

export const uiTestComparatorOptions = [
  { label: 'contains', value: 'contains' },
  { label: 'eq', value: 'eq' },
]

const uiTestKeywords = new Set(uiTestKeywordOptions.map((item) => item.value))
const uiTestLocatorTypes = new Set(uiTestLocatorTypeOptions.map((item) => item.value))
const uiTestComparators = new Set(uiTestComparatorOptions.map((item) => item.value))

const uiStepOperationKeywords = new Set([
  'open',
  'input',
  'press',
  'wait_text',
  'assert_text',
  'assert_visible',
  'assert_url',
  'sleep',
])

const uiStepLocatorRequiredKeywords = new Set([
  'click',
  'dblclick',
  'input',
  'clear',
  'wait_text',
  'assert_text',
  'assert_visible',
])

const uiStepComparatorKeywords = new Set(['assert_text', 'assert_url'])

type UiStepFieldMeta = {
  locatorHint?: string
  operationLabel?: string
  operationPlaceholder?: string
  operationHint?: string
}

const uiStepFieldMetaMap: Record<string, UiStepFieldMeta> = {
  open: {
    operationLabel: '页面 URL',
    operationPlaceholder: '例如：https://test.example.com/login',
    operationHint: 'open 步骤必须填写完整 URL。',
  },
  input: {
    locatorHint: 'input 必须定位可编辑元素，并会自动清空后再输入。',
    operationLabel: '输入值',
    operationPlaceholder: '例如：tester',
    operationHint: 'input 使用操作值作为输入内容。',
  },
  clear: {
    locatorHint: 'clear 仅适用于可填写文本的 input、textarea 或 contenteditable 元素。',
  },
  press: {
    operationLabel: '按键名',
    operationPlaceholder: '例如：Enter、Control+A',
    operationHint: '填写按键或组合键，例如 Enter、Escape、Tab、Control+A。',
  },
  wait_text: {
    locatorHint: 'wait_text 必须定位目标元素。',
    operationLabel: '等待文本',
    operationPlaceholder: '例如：登录成功',
    operationHint: '填写需要等待出现的文本。',
  },
  assert_text: {
    locatorHint: 'assert_text 需要定位到目标元素。',
    operationLabel: '期望文本',
    operationPlaceholder: '例如：登录成功',
    operationHint: '操作值即断言的期望文本，并且必须选择比较器。',
  },
  assert_visible: {
    locatorHint: 'assert_visible 需要定位到目标元素。',
    operationLabel: '超时时间(ms)',
    operationPlaceholder: '例如：3000',
    operationHint: '填写等待元素可见的超时时间，单位为毫秒。',
  },
  assert_url: {
    operationLabel: '期望 URL',
    operationPlaceholder: '例如：https://test.example.com/dashboard',
    operationHint: '操作值即期望 URL，并且必须选择比较器。',
  },
  sleep: {
    operationLabel: '等待时长(ms)',
    operationPlaceholder: '例如：1000',
    operationHint: 'sleep 使用操作值传毫秒数。',
  },
}

export type UiTestRunView = 'steps' | 'snapshot'
export type UiSuiteRunReportView = 'items' | 'snapshot'

export const uiTestRunViewOptions: Array<{ label: string; value: UiTestRunView }> = [
  { label: '步骤结果', value: 'steps' },
  { label: '运行快照', value: 'snapshot' },
]

export const uiSuiteRunReportViewOptions: Array<{ label: string; value: UiSuiteRunReportView }> = [
  { label: '用例明细', value: 'items' },
  { label: '运行快照', value: 'snapshot' },
]

export function getUiStepFieldMeta(keyword?: string) {
  return (keyword ? uiStepFieldMetaMap[keyword] : undefined) ?? {}
}

export function isValidUiStepKeyword(keyword?: string) {
  return Boolean(keyword && uiTestKeywords.has(keyword))
}

export function isValidUiStepLocatorType(locatorType?: string) {
  return Boolean(locatorType && uiTestLocatorTypes.has(locatorType))
}

export function isValidUiStepComparator(comparator?: string) {
  return Boolean(comparator && uiTestComparators.has(comparator))
}

export function requiresUiStepLocator(keyword?: string) {
  return Boolean(keyword && uiStepLocatorRequiredKeywords.has(keyword))
}

export function usesUiStepComparator(keyword?: string) {
  return Boolean(keyword && uiStepComparatorKeywords.has(keyword))
}

export function usesUiStepOperation(keyword?: string) {
  return Boolean(keyword && uiStepOperationKeywords.has(keyword))
}
