import type {
  ApiAssertRule,
  ApiEnvironment,
  ApiEnvironmentVar,
  ApiCollection,
  ApiExtractRule,
  Project,
  Requirement,
  RequirementUpdatePayload,
  Sprint,
  SprintCreatePayload,
  SprintUpdatePayload,
  CreateUiTestCasePayload,
  UiTestCase,
  UiTestSuite,
} from '../services/api'
import type { CollectionFormValues } from '@/features/api-automation/components/CollectionDrawer'
import type { SprintFormValues } from '@/features/projects/components/SprintDrawer'
import type { UiTestSuiteFormValues } from '@/features/ui-automation/components/UiTestSuiteDrawer'
import {
  normalizeText,
  setBooleanIfChanged,
  setDefinedValueIfChanged,
  setNormalizedTextIfChanged,
  setValueIfChanged,
} from '@/shared/utils/payload'
import { pickEndTime, pickStartTime } from './format'

function toRfc3339(value: SprintFormValues['startTime']) {
  if (!value) return ''
  if (typeof value === 'string') {
    const parsed = new Date(value)
    return Number.isNaN(parsed.getTime()) ? '' : parsed.toISOString()
  }
  if (value instanceof Date) return value.toISOString()
  if (typeof value.toDate === 'function') return value.toDate().toISOString()
  if (typeof value.toISOString === 'function') return value.toISOString()
  return ''
}

export function buildSprintCreatePayload(values: SprintFormValues): SprintCreatePayload {
  const startTime = toRfc3339(values.startTime)
  const endTime = toRfc3339(values.endTime)

  return {
    name: values.name,
    description: values.description,
    startTime,
    endTime,
  }
}

export function buildProjectUpdatePayload(project: Project, values: Pick<Project, 'name' | 'description'>) {
  const payload: Partial<Pick<Project, 'name' | 'description'>> = {}

  setValueIfChanged(payload, 'name', project.name, values.name)
  setNormalizedTextIfChanged(payload, 'description', project.description, values.description)

  return payload
}

export function buildSprintUpdatePayload(sprint: Sprint, values: SprintFormValues): SprintUpdatePayload {
  const payload: SprintUpdatePayload = {}
  const nextStartTime = toRfc3339(values.startTime)
  const nextEndTime = toRfc3339(values.endTime)
  const currentStartTime = pickStartTime(sprint) ?? ''
  const currentEndTime = pickEndTime(sprint) ?? ''

  setValueIfChanged(payload, 'name', sprint.name, values.name)
  setNormalizedTextIfChanged(payload, 'description', sprint.description, values.description)
  if (nextStartTime && nextStartTime !== currentStartTime) payload.startTime = nextStartTime
  setValueIfChanged(payload, 'endTime', currentEndTime, nextEndTime)

  return payload
}

export function buildRequirementMetadataUpdatePayload(
  requirement: Requirement,
  values: Partial<Pick<Requirement, 'name'>>,
): RequirementUpdatePayload {
  const payload: RequirementUpdatePayload = {}

  if (values.name !== undefined) {
    setValueIfChanged(payload, 'name', requirement.name, values.name)
  }

  return payload
}

export function buildApiCollectionUpdatePayload(collection: ApiCollection, values: CollectionFormValues) {
  const payload: Partial<Pick<ApiCollection, 'name' | 'description'>> = {}

  setValueIfChanged(payload, 'name', collection.name, values.name)
  setNormalizedTextIfChanged(payload, 'description', collection.description, values.summary)

  return payload
}

export function buildUiTestSuiteUpdatePayload(suite: UiTestSuite, values: UiTestSuiteFormValues) {
  const payload: Partial<
    Pick<
      UiTestSuite,
      | 'name'
      | 'description'
      | 'headless'
      | 'slowMoMs'
      | 'viewportWidth'
      | 'viewportHeight'
      | 'defaultStepTimeoutMs'
      | 'screenshotPolicy'
    >
  > = {}

  setValueIfChanged(payload, 'name', suite.name, values.name)
  setNormalizedTextIfChanged(payload, 'description', suite.description, values.description)
  setDefinedValueIfChanged(payload, 'headless', suite.headless, values.headless)
  setDefinedValueIfChanged(payload, 'slowMoMs', suite.slowMoMs ?? undefined, values.slowMoMs)
  setDefinedValueIfChanged(payload, 'viewportWidth', suite.viewportWidth ?? undefined, values.viewportWidth)
  setDefinedValueIfChanged(payload, 'viewportHeight', suite.viewportHeight ?? undefined, values.viewportHeight)
  setDefinedValueIfChanged(
    payload,
    'defaultStepTimeoutMs',
    suite.defaultStepTimeoutMs ?? undefined,
    values.defaultStepTimeoutMs,
  )
  setDefinedValueIfChanged(payload, 'screenshotPolicy', suite.screenshotPolicy ?? undefined, values.screenshotPolicy)

  return payload
}

export function buildUiTestCaseUpdatePayload(
  uiTestCase: UiTestCase,
  values: CreateUiTestCasePayload,
) {
  const payload: Partial<CreateUiTestCasePayload> = {}

  setValueIfChanged(payload, 'name', uiTestCase.name, values.name)
  setBooleanIfChanged(payload, 'enabled', uiTestCase.enabled, values.enabled)
  if ((uiTestCase.orderNo ?? undefined) !== (values.orderNo ?? undefined)) payload.orderNo = values.orderNo
  if (normalizeStepsJson(uiTestCase.stepsJson) !== normalizeStepsJson(values.stepsJson)) payload.stepsJson = values.stepsJson ?? '[]'

  return payload
}

function normalizeStepsJson(value: UiTestCase['stepsJson']) {
  if (!value) return ''

  try {
    const parsed = typeof value === 'string' ? JSON.parse(value) as unknown : value
    return JSON.stringify(parsed)
  } catch {
    return typeof value === 'string' ? normalizeText(value) : ''
  }
}

export function buildApiEnvironmentUpdatePayload(
  environment: ApiEnvironment,
  values: Pick<ApiEnvironment, 'name' | 'baseUrl' | 'description' | 'isDefault'>,
) {
  const payload: Partial<Pick<ApiEnvironment, 'name' | 'baseUrl' | 'description' | 'isDefault'>> = {}

  setValueIfChanged(payload, 'name', environment.name, values.name)
  setValueIfChanged(payload, 'baseUrl', environment.baseUrl, values.baseUrl)
  setNormalizedTextIfChanged(payload, 'description', environment.description, values.description)
  setBooleanIfChanged(payload, 'isDefault', environment.isDefault, values.isDefault)

  return payload
}

export function buildApiEnvironmentVarUpdatePayload(
  environmentVar: ApiEnvironmentVar,
  values: Pick<ApiEnvironmentVar, 'varKey' | 'value' | 'description' | 'isSecret'>,
) {
  const payload: Partial<Pick<ApiEnvironmentVar, 'varKey' | 'value' | 'description' | 'isSecret'>> = {}

  setValueIfChanged(payload, 'varKey', environmentVar.varKey, values.varKey)
  setValueIfChanged(payload, 'value', environmentVar.value, values.value)
  setNormalizedTextIfChanged(payload, 'description', environmentVar.description, values.description)
  setBooleanIfChanged(payload, 'isSecret', environmentVar.isSecret, values.isSecret)

  return payload
}

export function buildApiAssertRuleUpdatePayload(
  assertRule: ApiAssertRule,
  values: Pick<ApiAssertRule, 'name' | 'enabled' | 'orderNo' | 'assertSource' | 'targetExpr' | 'comparator' | 'expectedValue'>,
) {
  const payload: Partial<
    Pick<ApiAssertRule, 'name' | 'enabled' | 'orderNo' | 'assertSource' | 'targetExpr' | 'comparator' | 'expectedValue'>
  > = {}

  setValueIfChanged(payload, 'name', assertRule.name, values.name)
  setBooleanIfChanged(payload, 'enabled', assertRule.enabled, values.enabled)
  if ((assertRule.orderNo ?? undefined) !== (values.orderNo ?? undefined)) payload.orderNo = values.orderNo
  setValueIfChanged(payload, 'assertSource', assertRule.assertSource, values.assertSource)
  setNormalizedTextIfChanged(payload, 'targetExpr', assertRule.targetExpr, values.targetExpr)
  setValueIfChanged(payload, 'comparator', assertRule.comparator, values.comparator)
  setNormalizedTextIfChanged(payload, 'expectedValue', assertRule.expectedValue, values.expectedValue)

  return payload
}

export function buildApiExtractRuleUpdatePayload(
  extractRule: ApiExtractRule,
  values: Pick<ApiExtractRule, 'name' | 'enabled' | 'orderNo' | 'source' | 'sourceExpr' | 'varKey' | 'defaultValue'>,
) {
  const payload: Partial<
    Pick<ApiExtractRule, 'name' | 'enabled' | 'orderNo' | 'source' | 'sourceExpr' | 'varKey' | 'defaultValue'>
  > = {}

  setValueIfChanged(payload, 'name', extractRule.name, values.name)
  setBooleanIfChanged(payload, 'enabled', extractRule.enabled, values.enabled)
  if ((extractRule.orderNo ?? undefined) !== (values.orderNo ?? undefined)) payload.orderNo = values.orderNo
  setValueIfChanged(payload, 'source', extractRule.source, values.source)
  setNormalizedTextIfChanged(payload, 'sourceExpr', extractRule.sourceExpr, values.sourceExpr)
  setValueIfChanged(payload, 'varKey', extractRule.varKey, values.varKey)
  setNormalizedTextIfChanged(payload, 'defaultValue', extractRule.defaultValue, values.defaultValue)

  return payload
}
