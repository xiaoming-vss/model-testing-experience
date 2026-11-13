import { adminApi } from '@/features/admin/api/admin.api'
import { authApi } from '@/features/auth/api/auth.api'
import { aiTestingApi } from '@/features/ai-testing/api/aiTesting.api'
import { apiAutomationApi } from '@/features/api-automation/api/apiAutomation.api'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import { bugsApi } from '@/features/bugs/api/bugs.api'
import { functionTestingApi } from '@/features/test-cases/api/functionTesting.api'
import { testOrdersApi } from '@/features/test-orders/api/testOrders.api'
import { projectsApi } from '@/features/projects/api/projects.api'
import { requirementsApi } from '@/features/requirements/api/requirements.api'
import { uiAutomationApi } from '@/features/ui-automation/api/uiAutomation.api'

export type { User } from '@/features/auth/types'
export type {
  AiSkillLibraryItem,
  CodeRiskTaskRun,
  UploadAiSkillPayload,
} from '@/features/ai-testing/types'
export type {
  ApiAssertComparator,
  ApiAssertRule,
  ApiAssertSource,
  ApiCase,
  ApiCaseRunResult,
  ApiCollection,
  ApiCollectionRunItem,
  ApiCollectionRunReport,
  ApiCollectionRunSummary,
  ApiEnvironment,
  ApiEnvironmentVar,
  ApiExtractRule,
  ApiExtractRuleSource,
  CreateApiAssertRulePayload,
  CreateApiCasePayload,
  CreateApiEnvironmentPayload,
  CreateApiEnvironmentVarPayload,
  CreateApiExtractRulePayload,
  UpdateApiCasePayload,
} from '@/features/api-automation/types'
export type {
  Project,
  Sprint,
  SprintCreatePayload,
  SprintDailyMetricsSnapshot,
  SprintDailyMetricsTestStats,
  SprintUpdatePayload,
  TestReportGenerateRun,
} from '@/features/projects/types'
export type {
  Requirement,
  RequirementCreatePayload,
  RequirementDocumentType,
  RequirementUpdatePayload,
} from '@/features/requirements/types'
export type {
  GitlabGroup,
  GitlabRepository,
  ResourceBinding,
  ZentaoBindingTargetType,
  ZentaoBinding,
  ZentaoRemoteOption,
} from '@/features/base-services/types'
export type {
  FunctionCaseLibraryItem,
  FunctionTestCase,
  FunctionTestSuite,
} from '@/features/test-cases/types'
export type {
  CreateUiTestCasePayload,
  UiMissingVariable,
  UiTestCase,
  UiScreenshotPolicy,
  UiTestCaseDebugRunPayload,
  UiTestCaseRun,
  UiTestCaseRunStepResult,
  UiStepSaveRule,
  RunUiTestSuitePayload,
  UiTestSuite,
  UiTestSuiteRunItem,
  UiTestSuiteRunReport,
  UiTestSuiteRunSummary,
} from '@/features/ui-automation/types'
export type {
  TestOrder,
} from '@/features/test-orders/types'

export type { ListResponse } from '@/shared/api/request'
export { ApiError, listItems, listTotal } from '@/shared/api/request'

export const api = {
  ...adminApi,
  ...authApi,
  ...aiTestingApi,
  ...baseServicesApi,
  ...projectsApi,
  ...requirementsApi,
  ...apiAutomationApi,
  ...functionTestingApi,
  ...testOrdersApi,
  ...bugsApi,
  ...uiAutomationApi,
}
