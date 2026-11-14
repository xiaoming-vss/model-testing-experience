import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  CreateRepositoryProfileTaskPayload,
  RepositoryProfileTask,
  RepositoryProfileTaskRun,
  RepositoryProfileVersion,
  RunHistoryResponse,
  RunRepositoryProfileTaskPayload,
} from '../types'

/** Manual repository profile runs are requirement-scoped; they never enter the generation chain. */
export const repositoryProfileApi = {
  getRepositoryProfileTasks: (
    projectId: string,
    params: { page?: number; pageSize?: number; requirementId?: string; keyword?: string } = {},
  ) =>
    request<ListResponse<RepositoryProfileTask>>(
      `/v1/projects/${projectId}/repository-profile-tasks${buildQuery(params)}`,
    ),
  createRepositoryProfileTask: (
    projectId: string,
    body: CreateRepositoryProfileTaskPayload,
  ) =>
    request<RepositoryProfileTask>(`/v1/projects/${projectId}/repository-profile-tasks`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  runRepositoryProfileTask: (taskId: string, body: RunRepositoryProfileTaskPayload) =>
    request<RepositoryProfileTaskRun>(`/v1/repository-profile-tasks/${taskId}/run`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getRepositoryProfileTaskRuns: (
    taskId: string,
    params: { page?: number; pageSize?: number } = {},
  ) =>
    request<RunHistoryResponse<RepositoryProfileTaskRun>>(
      `/v1/repository-profile-tasks/${taskId}/runs${buildQuery(params)}`,
    ),
  getRepositoryProfileRun: (runId: string) =>
    request<RepositoryProfileTaskRun>(`/v1/repository-profile-runs/${runId}`),
  getRepositoryProfileVersions: (taskId: string) =>
    request<ListResponse<RepositoryProfileVersion>>(
      `/v1/repository-profile-tasks/${taskId}/versions`,
    ),
}
