import type { CreateUiTestCasePayload, UiTestCase } from '@/services/api'
import { moveArrayItem } from '@/shared/utils/array'
import { formatOptionalValue, prettyPrintValue } from '@/shared/utils/value'
import { normalizeUiTestCaseId, pickCreatedAt } from '@/utils/format'
import { requiresUiStepLocator, usesUiStepComparator, usesUiStepOperation } from '../config/stepConfig'

export const DRAFT_CASE_ID = '__draft_ui_test_case__'
export const EMPTY_UI_TEST_CASES: UiTestCase[] = []

export type UiTestStepFormValue = {
  orderNo?: number
  stepName?: string
  keyword?: string
  locatorType?: string
  locatorValue?: string
  operationValue?: string
  expectValue?: string
  comparator?: string
  timeoutMs?: number
  continueOnFailure?: boolean
  enabled?: boolean
  description?: string
}

export type UiTestCaseFormValues = {
  name: string
  enabled?: boolean
  steps?: UiTestStepFormValue[]
}

export function createDefaultUiTestCaseFormValues(): UiTestCaseFormValues {
  return {
    name: '',
    enabled: true,
    steps: [],
  }
}

function normalizeStepValue(step: Partial<UiTestStepFormValue>, index: number): UiTestStepFormValue {
  const orderNo = typeof step.orderNo === 'number' && Number.isFinite(step.orderNo) ? step.orderNo : index + 1
  const keyword = step.keyword ?? ''
  const legacyOperationValue = ['wait_text', 'assert_text', 'assert_url'].includes(keyword)
    ? step.expectValue
    : keyword === 'assert_visible' && typeof step.timeoutMs === 'number'
      ? String(step.timeoutMs)
      : undefined
  const operationValue = step.operationValue?.trim() ? step.operationValue : legacyOperationValue ?? step.operationValue ?? ''

  return {
    orderNo,
    stepName: step.stepName ?? '',
    keyword,
    locatorType: step.locatorType ?? '',
    locatorValue: step.locatorValue ?? '',
    operationValue,
    expectValue: step.expectValue ?? '',
    comparator: step.comparator ?? '',
    timeoutMs: typeof step.timeoutMs === 'number' && Number.isFinite(step.timeoutMs) ? step.timeoutMs : undefined,
    continueOnFailure: Boolean(step.continueOnFailure),
    enabled: step.enabled ?? true,
    description: step.description ?? '',
  }
}

export function parseStepsJson(value?: UiTestCase['stepsJson']) {
  if (!value) return []

  try {
    const parsed = typeof value === 'string' ? JSON.parse(value) as unknown : value
    if (!Array.isArray(parsed)) return []

    return parsed
      .map((item, index) => normalizeStepValue((item ?? {}) as Partial<UiTestStepFormValue>, index))
      .sort((left, right) => (left.orderNo ?? Number.MAX_SAFE_INTEGER) - (right.orderNo ?? Number.MAX_SAFE_INTEGER))
  } catch {
    return []
  }
}

function hasMeaningfulStepContent(step: UiTestStepFormValue) {
  return Boolean(
    step.stepName?.trim() ||
      step.keyword?.trim() ||
      step.locatorType?.trim() ||
      step.locatorValue?.trim() ||
      step.operationValue?.trim() ||
      step.comparator?.trim() ||
      step.expectValue?.trim() ||
      step.timeoutMs,
  )
}

export function serializeSteps(steps?: UiTestStepFormValue[]) {
  const normalizedSteps = (steps ?? [])
    .map((step, index) => normalizeStepValue(step ?? {}, index))
    .filter(hasMeaningfulStepContent)
    .map((step, index) => ({
      orderNo: index + 1,
      ...(step.stepName?.trim() ? { stepName: step.stepName.trim() } : {}),
      ...(step.keyword?.trim() ? { keyword: step.keyword.trim() } : {}),
      ...(requiresUiStepLocator(step.keyword?.trim()) && step.locatorType?.trim() ? { locatorType: step.locatorType.trim() } : {}),
      ...(requiresUiStepLocator(step.keyword?.trim()) && step.locatorValue?.trim() ? { locatorValue: step.locatorValue.trim() } : {}),
      ...(usesUiStepOperation(step.keyword?.trim()) && step.operationValue?.trim() ? { operationValue: step.operationValue.trim() } : {}),
      ...(usesUiStepComparator(step.keyword?.trim()) && step.comparator?.trim() ? { comparator: step.comparator.trim() } : {}),
      continueOnFailure: Boolean(step.continueOnFailure),
      enabled: step.enabled ?? true,
    }))

  return JSON.stringify(normalizedSteps)
}

export function serializeUiTestCaseValues(values: UiTestCaseFormValues): CreateUiTestCasePayload {
  return {
    name: values.name,
    enabled: values.enabled,
    stepsJson: serializeSteps(values.steps),
  }
}

export function buildUiTestCaseFormValues(uiTestCase: UiTestCase): UiTestCaseFormValues {
  return {
    ...createDefaultUiTestCaseFormValues(),
    name: uiTestCase.name ?? '',
    enabled: uiTestCase.enabled ?? true,
    steps: parseStepsJson(uiTestCase.stepsJson),
  }
}

function getUiTestCaseOrderNo(uiTestCase: UiTestCase) {
  return uiTestCase.orderNo ?? Number.MAX_SAFE_INTEGER
}

function getUiTestCaseCreatedTime(uiTestCase: UiTestCase) {
  const createdAt = pickCreatedAt(uiTestCase)
  const timestamp = createdAt ? new Date(createdAt).getTime() : 0
  return Number.isNaN(timestamp) ? 0 : timestamp
}

export function sortUiTestCases(uiTestCases: UiTestCase[]) {
  return [...uiTestCases].sort(
    (left, right) =>
      getUiTestCaseOrderNo(left) - getUiTestCaseOrderNo(right) ||
      getUiTestCaseCreatedTime(left) - getUiTestCaseCreatedTime(right) ||
      normalizeUiTestCaseId(left).localeCompare(normalizeUiTestCaseId(right)),
  )
}

export function getUiTestCaseStepCount(uiTestCase: UiTestCase) {
  return parseStepsJson(uiTestCase.stepsJson).length
}

export function moveExpandedStepIndex(index: number, fromIndex: number, toIndex: number) {
  if (index === fromIndex) return toIndex

  if (fromIndex < toIndex && index > fromIndex && index <= toIndex) {
    return index - 1
  }

  if (fromIndex > toIndex && index >= toIndex && index < fromIndex) {
    return index + 1
  }

  return index
}

export { formatOptionalValue, moveArrayItem, prettyPrintValue }

export function formatViewportText(width?: number, height?: number) {
  if (!width || !height) return '-'
  return `${width} x ${height}`
}

export function formatOptionalMs(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? `${value} ms` : '-'
}
