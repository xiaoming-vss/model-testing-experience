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
  return project.projectId ?? ''
}

export function normalizeSprintId(sprint: Sprint) {
  return sprint.sprintId ?? ''
}

export function normalizeRequirementId(requirement: Requirement) {
  return requirement.requirementId ?? ''
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
  return assertRule.assertRuleId ?? ''
}

export function normalizeExtractRuleId(extractRule: ApiExtractRule) {
  return extractRule.extractRuleId ?? ''
}

export function pickStartTime(sprint?: Sprint) {
  return sprint?.startTime
}

export function pickEndTime(sprint?: Sprint) {
  return sprint?.endTime
}

/** Bug 记录仍可能只带 snake_case 时间，属已登记的兼容字段，不能收窄。 */
export function pickCreatedAt(entity?: { createdAt?: string; created_at?: string }) {
  return entity?.createdAt ?? entity?.created_at
}

export function pickUpdatedAt(entity?: { updatedAt?: string; updated_at?: string }) {
  return entity?.updatedAt ?? entity?.updated_at
}

const displayTimeZone = 'Asia/Shanghai'
const timeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: displayTimeZone, hour12: false,
  year: 'numeric', month: 'numeric', day: 'numeric',
  hour: 'numeric', minute: 'numeric', second: 'numeric',
})

export function parseUtcAssumedTime(value: string) {
  const isTimezoneLessIso = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(value)
  return new Date(isTimezoneLessIso ? `${value.replace(' ', 'T')}Z` : value)
}

export function formatTime(value?: string) {
  if (!value) return '-'
  const date = parseUtcAssumedTime(value)
  return Number.isNaN(date.getTime())
    ? value
    : timeFormatter.format(date)
}

export function formatCompactTime(value?: string | null) {
  if (!value) return ''
  const parsed = parseUtcAssumedTime(value)
  if (Number.isNaN(parsed.getTime())) return ''
  return parsed.toLocaleString('zh-CN', {
    timeZone: displayTimeZone,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : '操作失败'
}
