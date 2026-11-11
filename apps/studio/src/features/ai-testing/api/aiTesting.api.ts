import { skillsApi } from './skills.api'
import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  RunHistoryResponse,
  ApiCaseGenerateTask,
  ApiCaseGenerateTaskRun,
  CodeRiskTask,
  CodeRiskTaskRun,
  CreateApiCaseGenerateTaskPayload,
  CreateCodeRiskTaskPayload,
  CreateFunctionalCaseGenerateTaskPayload,
  CreateRequirementAnalysisTaskPayload,
  CreateUiCaseGenerateTaskPayload,
  FunctionalCaseGenerateTask,
  FunctionalCaseGenerateTaskRun,
  ImportApiCaseGenerateTaskRunPayload,
  ImportApiCaseGenerateTaskRunResult,
  ImportUiCaseGenerateTaskRunPayload,
  ImportFunctionalCaseGenerateTaskRunPayload,
  ImportFunctionalCaseGenerateTaskRunResult,
  RequirementAnalysisTask,
  RequirementAnalysisTaskRun,
  ReviewApiCaseGenerateTaskRunPayload,
  ReviewFunctionalCaseGenerateTaskRunPayload,
  ReviewFunctionalCaseGenerateTaskRunStagePayload,
  ReviewRequirementAnalysisTaskRunStagePayload,
  ReviseRequirementAnalysisTaskRunStagePayload,
  RetryFunctionalCaseGenerateTaskRunStagePayload,
  RunCodeRiskTaskPayload,
  RunFunctionalCaseGenerateTaskPayload,
  RunRequirementAnalysisTaskPayload,
  RunUiCaseGenerateTaskPayload,
  UpdateApiCaseGenerateTaskPayload,
  UpdateApiCaseGenerateTaskRunResultPayload,
  UpdateFunctionalCaseGenerateTaskPayload,
  UpdateFunctionalCaseGenerateTaskRunResultPayload,
  UpdateFunctionalCaseGenerateTaskRunStageOutputPayload,
  UpdateRequirementAnalysisTaskPayload,
  UpdateRequirementAnalysisTaskRunStageOutputPayload,
  ReviewUiCaseGenerateTaskRunPayload,
  UiCaseGenerateTask,
  UiCaseGenerateTaskRun,
  UiCaseGenerateTaskRunImportResult,
  UpdateUiCaseGenerateTaskPayload,
  UpdateUiCaseGenerateTaskRunResultPayload,
} from '../types'

export const aiTestingApi = {
  ...skillsApi,
  createApiCaseGenerateTask: (projectId: string, body: CreateApiCaseGenerateTaskPayload) =>
    request<ApiCaseGenerateTask>(`/v1/projects/${projectId}/api-case-generate-tasks`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getApiCaseGenerateTask: (taskId: string) =>
    request<ApiCaseGenerateTask>(`/v1/api-case-generate-tasks/${taskId}`),
  updateApiCaseGenerateTask: (taskId: string, body: UpdateApiCaseGenerateTaskPayload) =>
    request<ApiCaseGenerateTask>(`/v1/api-case-generate-tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  runApiCaseGenerateTask: (taskId: string, connectionId: string, checkpointEnabled = false) =>
    request<ApiCaseGenerateTaskRun>(`/v1/api-case-generate-tasks/${taskId}/run`, {
      method: 'POST',
      body: JSON.stringify({ connectionId, ...(checkpointEnabled ? { checkpointEnabled: true, apiWorkflowVersion: 'api_two_stage/1.0' } : {}) }),
    }),
  getApiCaseGenerateTaskRuns: (taskId: string, params: { page?: number; pageSize?: number; pipelineFilter?: string } = {}) =>
    request<RunHistoryResponse<ApiCaseGenerateTaskRun>>(`/v1/api-case-generate-tasks/${taskId}/runs${buildQuery(params)}`),
  getApiCaseGenerateTaskRun: (runId: string) =>
    request<ApiCaseGenerateTaskRun>(`/v1/api-case-generate-task-runs/${runId}`),
  deleteApiCaseGenerateTaskRun: (runId: string) =>
    request<Record<string, never>>(`/v1/api-case-generate-task-runs/${runId}`, { method: 'DELETE' }),
  updateApiCaseGenerateTaskRunResult: (runId: string, body: UpdateApiCaseGenerateTaskRunResultPayload) =>
    request<ApiCaseGenerateTaskRun>(`/v1/api-case-generate-task-runs/${runId}/result`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  reviewApiCaseGenerateTaskRun: (runId: string, body: ReviewApiCaseGenerateTaskRunPayload) =>
    request<ApiCaseGenerateTaskRun>(`/v1/api-case-generate-task-runs/${runId}/review`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  saveApiCaseStageOutput: (runId: string, configJson: Record<string, unknown>) =>
    request<ApiCaseGenerateTaskRun>(`/v1/api-case-generate-task-runs/${runId}/stage-output`, {
      method: 'PATCH', body: JSON.stringify({ stage: 'openapi_extract', configJson }),
    }),
  reviewApiCaseStage: (runId: string, body: { stage: string; action: 'approve' | 'reject'; llmConnectionId?: string; requestId?: string }) =>
    request<ApiCaseGenerateTaskRun>(`/v1/api-case-generate-task-runs/${runId}/stage-review`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  retryApiCaseStage: (runId: string, body: { stage: string; llmConnectionId: string; requestId?: string }) =>
    request<ApiCaseGenerateTaskRun>(`/v1/api-case-generate-task-runs/${runId}/stage-retry`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  reviseApiCaseStage: (runId: string, body: { stage: string; revisionInstruction: string; llmConnectionId: string; requestId?: string }) =>
    request<ApiCaseGenerateTaskRun>(`/v1/api-case-generate-task-runs/${runId}/stage-revise`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  importApiCaseGenerateTaskRun: (runId: string, body: ImportApiCaseGenerateTaskRunPayload) =>
    request<ImportApiCaseGenerateTaskRunResult>(`/v1/api-case-generate-task-runs/${runId}/import`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteApiCaseGenerateTask: (taskId: string) =>
    request<Record<string, never>>(`/v1/api-case-generate-tasks/${taskId}`, {
      method: 'DELETE',
    }),
  createFunctionalCaseGenerateTask: (projectId: string, body: CreateFunctionalCaseGenerateTaskPayload) =>
    request<FunctionalCaseGenerateTask>(`/v1/projects/${projectId}/function-case-generate-tasks`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getFunctionalCaseGenerateTask: (taskId: string) =>
    request<FunctionalCaseGenerateTask>(`/v1/function-case-generate-tasks/${taskId}`),
  updateFunctionalCaseGenerateTask: (taskId: string, body: UpdateFunctionalCaseGenerateTaskPayload) =>
    request<FunctionalCaseGenerateTask>(`/v1/function-case-generate-tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  runFunctionalCaseGenerateTask: (taskId: string, body: RunFunctionalCaseGenerateTaskPayload) =>
    request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-tasks/${taskId}/run`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getFunctionalCaseGenerateTaskRuns: (taskId: string, params: { page?: number; pageSize?: number; pipelineFilter?: string } = {}) =>
    request<RunHistoryResponse<FunctionalCaseGenerateTaskRun>>(`/v1/function-case-generate-tasks/${taskId}/runs${buildQuery(params)}`),
  getFunctionalCaseGenerateTaskRun: (runId: string) =>
    request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-task-runs/${runId}`),
  deleteFunctionalCaseGenerateTaskRun: (runId: string) =>
    request<Record<string, never>>(`/v1/function-case-generate-task-runs/${runId}`, {
      method: 'DELETE',
    }),
  updateFunctionalCaseGenerateTaskRunResult: (
    runId: string,
    body: UpdateFunctionalCaseGenerateTaskRunResultPayload,
  ) =>
    request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-task-runs/${runId}/result`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  updateFunctionalCaseGenerateTaskRunStageOutput: (
    runId: string,
    body: UpdateFunctionalCaseGenerateTaskRunStageOutputPayload,
  ) =>
    request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-task-runs/${runId}/stage-output`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  reviewFunctionalCaseGenerateTaskRunStage: (
    runId: string,
    body: ReviewFunctionalCaseGenerateTaskRunStagePayload,
  ) =>
    request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-task-runs/${runId}/stage-review`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  reviseFunctionalCaseGenerateTaskRunStage: (
    runId: string,
    body: { llmConnectionId?: string; stage: string; revisionInstruction: string; configJson?: Record<string, unknown>; resultYaml?: string; attachmentFileIds?: string[] },
  ) => request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-task-runs/${runId}/stage-revise`, {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  generateFunctionalCaseRelationAnalysis: (runId: string, connectionId?: string) =>
    request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-task-runs/${runId}/relation-analysis`, {
      method: 'POST',
      body: JSON.stringify(connectionId ? { connectionId } : {}),
    }),
  retryFunctionalCaseGenerateTaskRunStage: (
    runId: string,
    body: RetryFunctionalCaseGenerateTaskRunStagePayload,
  ) =>
    request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-task-runs/${runId}/stage-retry`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  reviewFunctionalCaseGenerateTaskRun: (runId: string, body: ReviewFunctionalCaseGenerateTaskRunPayload) =>
    request<FunctionalCaseGenerateTaskRun>(`/v1/function-case-generate-task-runs/${runId}/review`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  importFunctionalCaseGenerateTaskRun: (runId: string, body: ImportFunctionalCaseGenerateTaskRunPayload) =>
    request<ImportFunctionalCaseGenerateTaskRunResult>(`/v1/function-case-generate-task-runs/${runId}/import`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteFunctionalCaseGenerateTask: (taskId: string) =>
    request<Record<string, never>>(`/v1/function-case-generate-tasks/${taskId}`, {
      method: 'DELETE',
    }),
  createUiCaseGenerateTask: (projectId: string, body: CreateUiCaseGenerateTaskPayload) =>
    request<UiCaseGenerateTask>(`/v1/projects/${projectId}/ui-case-generate-tasks`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getUiCaseGenerateTask: (taskId: string) =>
    request<UiCaseGenerateTask>(`/v1/ui-case-generate-tasks/${taskId}`),
  updateUiCaseGenerateTask: (taskId: string, body: UpdateUiCaseGenerateTaskPayload) =>
    request<UiCaseGenerateTask>(`/v1/ui-case-generate-tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteUiCaseGenerateTask: (taskId: string) =>
    request<Record<string, never>>(`/v1/ui-case-generate-tasks/${taskId}`, { method: 'DELETE' }),
  runUiCaseGenerateTask: (taskId: string, body: RunUiCaseGenerateTaskPayload) =>
    request<UiCaseGenerateTaskRun>(`/v1/ui-case-generate-tasks/${taskId}/run`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getUiCaseGenerateTaskRuns: (taskId: string, params: { page?: number; pageSize?: number; pipelineFilter?: string } = {}) =>
    request<RunHistoryResponse<UiCaseGenerateTaskRun>>(`/v1/ui-case-generate-tasks/${taskId}/runs${buildQuery(params)}`),
  getUiCaseGenerateTaskRun: (runId: string) =>
    request<UiCaseGenerateTaskRun>(`/v1/ui-case-generate-task-runs/${runId}`),
  deleteUiCaseGenerateTaskRun: (runId: string) =>
    request<Record<string, never>>(`/v1/ui-case-generate-task-runs/${runId}`, { method: 'DELETE' }),
  updateUiCaseGenerateTaskRunResult: (runId: string, body: UpdateUiCaseGenerateTaskRunResultPayload) =>
    request<UiCaseGenerateTaskRun>(`/v1/ui-case-generate-task-runs/${runId}/result`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  reviewUiCaseGenerateTaskRun: (runId: string, body: ReviewUiCaseGenerateTaskRunPayload) =>
    request<UiCaseGenerateTaskRun>(`/v1/ui-case-generate-task-runs/${runId}/review`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  saveUiGenerationStage: (runId: string, body: Record<string, unknown>) =>
    request<UiCaseGenerateTaskRun>(`/v1/ui-case-generate-task-runs/${runId}/stage-output`, { method: 'PATCH', body: JSON.stringify(body) }),
  reviewUiGenerationStage: (runId: string, body: Record<string, unknown>) =>
    request<UiCaseGenerateTaskRun>(`/v1/ui-case-generate-task-runs/${runId}/review-stage`, { method: 'POST', body: JSON.stringify(body) }),
  reviseUiGenerationStage: (runId: string, body: Record<string, unknown>) =>
    request<UiCaseGenerateTaskRun>(`/v1/ui-case-generate-task-runs/${runId}/revise-stage`, { method: 'POST', body: JSON.stringify(body) }),
  retryUiGenerationStage: (runId: string, body: Record<string, unknown>) =>
    request<UiCaseGenerateTaskRun>(`/v1/ui-case-generate-task-runs/${runId}/retry-stage`, { method: 'POST', body: JSON.stringify(body) }),
  importUiCaseGenerateTaskRun: (runId: string, body: ImportUiCaseGenerateTaskRunPayload) =>
    request<UiCaseGenerateTaskRunImportResult>(`/v1/ui-case-generate-task-runs/${runId}/import`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  createRequirementAnalysisTask: (projectId: string, body: CreateRequirementAnalysisTaskPayload) =>
    request<RequirementAnalysisTask>(`/v1/projects/${projectId}/requirement-analysis-tasks`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getRequirementAnalysisTask: (taskId: string) =>
    request<RequirementAnalysisTask>(`/v1/requirement-analysis-tasks/${taskId}`),
  updateRequirementAnalysisTask: (taskId: string, body: UpdateRequirementAnalysisTaskPayload) =>
    request<RequirementAnalysisTask>(`/v1/requirement-analysis-tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteRequirementAnalysisTask: (taskId: string) =>
    request<Record<string, never>>(`/v1/requirement-analysis-tasks/${taskId}`, {
      method: 'DELETE',
    }),
  runRequirementAnalysisTask: (taskId: string, body: RunRequirementAnalysisTaskPayload) =>
    request<RequirementAnalysisTaskRun>(`/v1/requirement-analysis-tasks/${taskId}/run`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getRequirementAnalysisTaskRuns: (taskId: string, params: { page?: number; pageSize?: number; pipelineFilter?: string } = {}) =>
    request<RunHistoryResponse<RequirementAnalysisTaskRun>>(`/v1/requirement-analysis-tasks/${taskId}/runs${buildQuery(params)}`),
  getRequirementAnalysisRun: (runId: string) =>
    request<RequirementAnalysisTaskRun>(`/v1/requirement-analysis-runs/${runId}`),
  deleteRequirementAnalysisRun: (runId: string) =>
    request<Record<string, never>>(`/v1/requirement-analysis-runs/${runId}`, { method: 'DELETE' }),
  updateRequirementAnalysisRunStageOutput: (
    runId: string,
    body: UpdateRequirementAnalysisTaskRunStageOutputPayload,
  ) =>
    request<RequirementAnalysisTaskRun>(`/v1/requirement-analysis-runs/${runId}/stage-output`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  reviewRequirementAnalysisRunStage: (
    runId: string,
    body: ReviewRequirementAnalysisTaskRunStagePayload,
  ) =>
    request<RequirementAnalysisTaskRun>(`/v1/requirement-analysis-runs/${runId}/stage-review`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  retryRequirementAnalysisRunStage: (runId: string, body: { stage: string; llmConnectionId?: string }) =>
    request<RequirementAnalysisTaskRun>(`/v1/requirement-analysis-runs/${runId}/stage-retry`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  reviseRequirementAnalysisRunStage: (
    runId: string,
    body: ReviseRequirementAnalysisTaskRunStagePayload,
  ) =>
    request<RequirementAnalysisTaskRun>(`/v1/requirement-analysis-runs/${runId}/stage-revise`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getCodeRiskTasks: (projectId: string) =>
    request<ListResponse<CodeRiskTask>>(`/v1/projects/${projectId}/code-risk-analysis-tasks`),
  getCodeRiskLatestRuns: (projectId: string) =>
    request<ListResponse<CodeRiskTaskRun>>(
      `/v1/projects/${projectId}/code-risk-analysis-tasks/latest-runs`,
    ),
  createCodeRiskTask: (projectId: string, body: CreateCodeRiskTaskPayload) =>
    request<CodeRiskTask>(`/v1/projects/${projectId}/code-risk-analysis-tasks`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getCodeRiskTask: (taskId: string) => request<CodeRiskTask>(`/v1/code-risk-analysis-tasks/${taskId}`),
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
