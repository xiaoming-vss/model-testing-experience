import { Tag } from 'antd'
import type {
  ApiAssertRule,
  ApiEnvironment,
  ApiEnvironmentVar,
  ApiExtractRule,
  FunctionTestCase,
  FunctionTestSuite,
  Project,
  Requirement,
  Sprint,
  UiTestCase,
  UiTestSuite,
  User,
} from '../services/api'

export function normalizeUserName(user?: User | null) {
  return user?.name ?? user?.nickname ?? '未命名用户'
}

export function normalizeProjectId(project: Project) {
  return project.projectId ?? project.project_id ?? ''
}

export function normalizeSprintId(sprint: Sprint) {
  return sprint.sprintId ?? sprint.sprint_id ?? ''
}

export function normalizeRequirementId(requirement: Requirement) {
  return requirement.requirementId ?? requirement.requirement_id ?? ''
}

export function normalizeEnvironmentId(environment: ApiEnvironment) {
  return environment.environmentId ?? ''
}

export function normalizeEnvironmentVarId(environmentVar: ApiEnvironmentVar) {
  return environmentVar.envVarId ?? ''
}

export function normalizeUiTestSuiteId(suite: UiTestSuite) {
  return suite.suiteId ?? ''
}

export function normalizeFunctionTestSuiteId(suite: FunctionTestSuite) {
  return suite.suiteId ?? ''
}

export function normalizeFunctionTestCaseId(testCase: FunctionTestCase) {
  return testCase.caseId ?? ''
}

export function normalizeUiTestCaseId(uiTestCase: UiTestCase) {
  return uiTestCase.caseId ?? ''
}

export function normalizeAssertRuleId(assertRule: ApiAssertRule) {
  return assertRule.assertRuleId ?? assertRule.assert_rule_id ?? ''
}

export function normalizeExtractRuleId(extractRule: ApiExtractRule) {
  return extractRule.extractRuleId ?? extractRule.extract_rule_id ?? ''
}

export function pickStartTime(sprint?: Sprint) {
  return sprint?.startTime ?? sprint?.start_time
}

export function pickEndTime(sprint?: Sprint) {
  return sprint?.endTime ?? sprint?.end_time
}

export function pickCreatedAt(entity?: { createdAt?: string; created_at?: string }) {
  return entity?.createdAt ?? entity?.created_at
}

export function pickUpdatedAt(entity?: { updatedAt?: string; updated_at?: string }) {
  return entity?.updatedAt ?? entity?.updated_at
}

export function formatTime(value?: string) {
  if (!value) return '-'
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
  const isIsoDateTime = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(value)
  const normalizedValue = !hasTimezone && isIsoDateTime ? `${value.replace(' ', 'T')}Z` : value
  const date = new Date(normalizedValue)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}

export function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : '操作失败'
}

export function statusTag(value?: string) {
  const colorMap: Record<string, string> = {
    planned: 'default',
    running: 'processing',
    completed: 'success',
    draft: 'default',
    in_progress: 'processing',
  }
  return <Tag color={value ? colorMap[value] : 'default'}>{value ?? '-'}</Tag>
}
