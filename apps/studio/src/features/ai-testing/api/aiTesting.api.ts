import { skillsApi } from './skills.api'
import { buildQuery, request } from '@/shared/api/request'
import type {
  AiTaskListResponse,
  RunHistoryResponse,
  ApiCaseGenerateTask,
  CodeRiskTask,
  CodeRiskTaskRun,
  CreateCodeRiskTaskPayload,
  FunctionalCaseGenerateTask,
  FunctionalCaseGenerateTaskRun,
  RequirementAnalysisTask,
  RunCodeRiskTaskPayload,
  UiCaseGenerateTask,
} from '../types'

export const aiTestingApi = {
  ...skillsApi,
  getApiCaseGenerateTask: (taskId: string) =>
    request<ApiCaseGenerateTask>(`/v1/api-case-generate-tasks/${taskId}`),
  getFunctionalCaseGenerateTask: (taskId: string) =>
    request<FunctionalCaseGenerateTask>(`/v1/function-case-generate-tasks/${taskId}`),
  getFunctionalCaseGenerateTaskRun: (runId: string) =>
    request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-task-runs/${runId}`),
  generateFunctionalCaseRelationAnalysis: (runId: string, connectionId?: string) =>
    request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-task-runs/${runId}/relation-analysis`, {
      method: 'POST',
      body: JSON.stringify(connectionId ? { connectionId } : {}),
    }),
  getUiCaseGenerateTask: (taskId: string) =>
    request<UiCaseGenerateTask>(`/v1/ui-case-generate-tasks/${taskId}`),
  getRequirementAnalysisTask: (taskId: string) =>
    request<RequirementAnalysisTask>(`/v1/requirement-analysis-tasks/${taskId}`),
  getCodeRiskTasks: (
    projectId: string,
    params: {
      page?: number
      pageSize?: number
      sprintId?: string
      requirementId?: string
      keyword?: string
      status?: string
    } = {},
  ) =>
    request<AiTaskListResponse<CodeRiskTask>>(
      `/v1/projects/${projectId}/code-risk-analysis-tasks${buildQuery(params)}`,
    ),
  createCodeRiskTask: (projectId: string, body: CreateCodeRiskTaskPayload) =>
    request<CodeRiskTask>(`/v1/projects/${projectId}/code-risk-analysis-tasks`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  runCodeRiskTask: (taskId: string, body: RunCodeRiskTaskPayload) =>
    request<CodeRiskTaskRun>(`/v1/code-risk-analysis-tasks/${taskId}/run`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getCodeRiskTaskRuns: (taskId: string, params: { page?: number; pageSize?: number; pipelineFilter?: string } = {}) =>
    request<RunHistoryResponse<CodeRiskTaskRun>>(`/v1/code-risk-analysis-tasks/${taskId}/runs${buildQuery(params)}`),
  getCodeRiskRun: (runId: string) => request<CodeRiskTaskRun>(`/v1/code-risk-analysis-runs/${runId}`),
  deleteCodeRiskRun: (runId: string) =>
    request<Record<string, never>>(`/v1/code-risk-analysis-runs/${runId}`, { method: 'DELETE' }),
}
