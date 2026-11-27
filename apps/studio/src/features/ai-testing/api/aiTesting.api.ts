import { skillsApi } from './skills.api'
import { buildQuery, request } from '@/shared/api/request'
import type {
  AiTaskListResponse,
  CodeRiskTask,
  CodeRiskTaskRun,
  CreateCodeRiskTaskPayload,
  RunCodeRiskTaskPayload,
  RunHistoryResponse,
} from '../types'

export const aiTestingApi = {
  ...skillsApi,
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
