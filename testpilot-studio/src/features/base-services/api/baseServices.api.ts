import { request, type ListResponse } from '@/shared/api/request'
import type {
  CreateLlmConnectionPayload,
  CreateGitlabConnectionPayload,
  CreateGitlabGroupBindingPayload,
  CreateGitlabRequirementBindingPayload,
  CreateZentaoBindingPayload,
  CreateZentaoConnectionPayload,
  GitlabBranch,
  GitlabConnection,
  GitlabGroup,
  GitlabRepository,
  GitlabResourceListResponse,
  LlmConnection,
  ReauthGitlabConnectionPayload,
  ResourceBinding,
  UpdateGitlabConnectionPayload,
  UpdateGitlabRequirementBindingPayload,
  UpdateLlmConnectionPayload,
  UpdateZentaoConnectionPayload,
  ZentaoBinding,
  ZentaoConnection,
  ZentaoRemoteListResponse,
  ZentaoRemoteOption,
} from '../types'

function integrationPath(projectId: string, provider: 'llm' | 'zentao' | 'gitlab') {
  return `/v1/projects/${encodeURIComponent(projectId)}/integrations/${provider}/connections`
}

function integrationConnectionPath(projectId: string, provider: 'llm' | 'zentao' | 'gitlab', connectionId: string) {
  return `${integrationPath(projectId, provider)}/${encodeURIComponent(connectionId)}`
}

export const baseServicesApi = {
  updateZentaoBinding: (target: 'project' | 'sprint' | 'requirement', resourceId: string, bindingId: string, body: { connectionId: string; remoteResourceId: string }) =>
    request<ZentaoBinding>(`/v1/${target}s/${resourceId}/bindings/${bindingId}`, { method: 'PATCH', body: JSON.stringify(body) }),
  getLlmConnections: (projectId: string) => request<ListResponse<LlmConnection>>(integrationPath(projectId, 'llm')),
  getLlmConnection: (projectId: string, connectionId: string) =>
    request<LlmConnection>(integrationConnectionPath(projectId, 'llm', connectionId)),
  createLlmConnection: (projectId: string, body: CreateLlmConnectionPayload) =>
    request<LlmConnection>(integrationPath(projectId, 'llm'), {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateLlmConnection: (projectId: string, connectionId: string, body: UpdateLlmConnectionPayload) =>
    request<LlmConnection>(integrationConnectionPath(projectId, 'llm', connectionId), {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteLlmConnection: (projectId: string, connectionId: string) =>
    request<Record<string, never>>(integrationConnectionPath(projectId, 'llm', connectionId), {
      method: 'DELETE',
    }),
  getGitlabConnections: (projectId: string) =>
    request<ListResponse<GitlabConnection>>(integrationPath(projectId, 'gitlab')),
  getGitlabConnection: (projectId: string, connectionId: string) =>
    request<GitlabConnection>(integrationConnectionPath(projectId, 'gitlab', connectionId)),
  createGitlabConnection: (projectId: string, body: CreateGitlabConnectionPayload) =>
    request<GitlabConnection>(integrationPath(projectId, 'gitlab'), {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateGitlabConnection: (projectId: string, connectionId: string, body: UpdateGitlabConnectionPayload) =>
    request<GitlabConnection>(integrationConnectionPath(projectId, 'gitlab', connectionId), {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  reauthGitlabConnection: (projectId: string, connectionId: string, body?: ReauthGitlabConnectionPayload) =>
    request<GitlabConnection>(integrationConnectionPath(projectId, 'gitlab', connectionId) + '/reauth', {
      method: 'POST',
      ...(body?.accessToken ? { body: JSON.stringify(body) } : {}),
    }),
  deleteGitlabConnection: (projectId: string, connectionId: string) =>
    request<Record<string, never>>(integrationConnectionPath(projectId, 'gitlab', connectionId), {
      method: 'DELETE',
    }),
  getZentaoConnections: (projectId: string) => request<ListResponse<ZentaoConnection>>(integrationPath(projectId, 'zentao')),
  getZentaoConnection: (projectId: string, connectionId: string) =>
    request<ZentaoConnection>(integrationConnectionPath(projectId, 'zentao', connectionId)),
  createZentaoConnection: (projectId: string, body: CreateZentaoConnectionPayload) =>
    request<ZentaoConnection>(integrationPath(projectId, 'zentao'), {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateZentaoConnection: (projectId: string, connectionId: string, body: UpdateZentaoConnectionPayload) =>
    request<ZentaoConnection>(integrationConnectionPath(projectId, 'zentao', connectionId), {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  reauthZentaoConnection: (projectId: string, connectionId: string) =>
    request<ZentaoConnection>(`${integrationConnectionPath(projectId, 'zentao', connectionId)}/reauth`, {
      method: 'POST',
    }),
  deleteZentaoConnection: (projectId: string, connectionId: string) =>
    request<Record<string, never>>(integrationConnectionPath(projectId, 'zentao', connectionId), {
      method: 'DELETE',
    }),
  getZentaoRemoteProjects: (projectId: string, connectionId: string, page = 1, pageSize = 100) =>
    request<ZentaoRemoteListResponse<ZentaoRemoteOption>>(
      `${integrationConnectionPath(projectId, 'zentao', connectionId)}/projects?page=${page}&pageSize=${pageSize}`,
    ),
  getZentaoRemoteExecutions: (projectId: string, connectionId: string, remoteProjectId: string, page = 1, pageSize = 100) =>
    request<ZentaoRemoteListResponse<ZentaoRemoteOption>>(
      `${integrationConnectionPath(projectId, 'zentao', connectionId)}/projects/${encodeURIComponent(remoteProjectId)}/executions?page=${page}&pageSize=${pageSize}`,
    ),
  getZentaoRemoteTestTasks: (projectId: string, connectionId: string, remoteExecutionId: string, page = 1, pageSize = 100) =>
    request<ZentaoRemoteListResponse<ZentaoRemoteOption>>(
      `${integrationConnectionPath(projectId, 'zentao', connectionId)}/executions/${encodeURIComponent(remoteExecutionId)}/testtasks?page=${page}&pageSize=${pageSize}`,
    ),
  getZentaoRemoteStories: (projectId: string, connectionId: string, remoteExecutionId: string, page = 1, pageSize = 100) =>
    request<ZentaoRemoteListResponse<ZentaoRemoteOption>>(
      `${integrationConnectionPath(projectId, 'zentao', connectionId)}/executions/${encodeURIComponent(remoteExecutionId)}/stories?page=${page}&pageSize=${pageSize}`,
    ),
  getZentaoRemoteCases: (projectId: string, connectionId: string, remoteExecutionId: string, page = 1, pageSize = 100) =>
    request<ZentaoRemoteListResponse<ZentaoRemoteOption>>(
      `${integrationConnectionPath(projectId, 'zentao', connectionId)}/executions/${encodeURIComponent(remoteExecutionId)}/cases?page=${page}&pageSize=${pageSize}`,
    ),
  getProjectBindings: (projectId: string) => request<ListResponse<ZentaoBinding>>(`/v1/projects/${projectId}/bindings`),
  createProjectBinding: (projectId: string, body: CreateZentaoBindingPayload) =>
    request<ZentaoBinding>(`/v1/projects/${projectId}/bindings`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteProjectBinding: (projectId: string, bindingId: string) =>
    request<Record<string, never>>(`/v1/projects/${projectId}/bindings/${bindingId}`, {
      method: 'DELETE',
    }),
  getSprintBindings: (sprintId: string) => request<ListResponse<ZentaoBinding>>(`/v1/sprints/${sprintId}/bindings`),
  createSprintBinding: (sprintId: string, body: CreateZentaoBindingPayload) =>
    request<ZentaoBinding>(`/v1/sprints/${sprintId}/bindings`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteSprintBinding: (sprintId: string, bindingId: string) =>
    request<Record<string, never>>(`/v1/sprints/${sprintId}/bindings/${bindingId}`, {
      method: 'DELETE',
    }),
  getRequirementBindings: (requirementId: string) =>
    request<ListResponse<ZentaoBinding>>(`/v1/requirements/${requirementId}/bindings`),
  createRequirementBinding: (requirementId: string, body: CreateZentaoBindingPayload) =>
    request<ZentaoBinding>(`/v1/requirements/${requirementId}/bindings`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteRequirementBinding: (requirementId: string, bindingId: string) =>
    request<Record<string, never>>(`/v1/requirements/${requirementId}/bindings/${bindingId}`, {
      method: 'DELETE',
    }),
  getGitlabGroups: (projectId: string, connectionId: string, search: string, page = 1, pageSize = 100) =>
    request<GitlabResourceListResponse<GitlabGroup>>(
      `${integrationConnectionPath(projectId, 'gitlab', connectionId)}/groups?search=${encodeURIComponent(search)}&page=${page}&pageSize=${pageSize}`,
    ),
  getGitlabGroupRepositories: (projectId: string, connectionId: string, groupId: string, page = 1, pageSize = 100) =>
    request<GitlabResourceListResponse<GitlabRepository>>(
      `${integrationConnectionPath(projectId, 'gitlab', connectionId)}/groups/${encodeURIComponent(groupId)}/repositories?page=${page}&pageSize=${pageSize}`,
    ),
  getGitlabRepositoryBranches: (projectId: string, connectionId: string, repositoryId: string, search: string, page = 1, pageSize = 100) =>
    request<GitlabResourceListResponse<GitlabBranch>>(
      `${integrationConnectionPath(projectId, 'gitlab', connectionId)}/repositories/${encodeURIComponent(repositoryId)}/branches?search=${encodeURIComponent(search)}&page=${page}&pageSize=${pageSize}`,
    ),
  createGitlabGroupBinding: (projectId: string, body: CreateGitlabGroupBindingPayload) =>
    request<ResourceBinding>(`/v1/projects/${projectId}/bindings`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getGitlabProjectBindings: (projectId: string) =>
    request<ListResponse<ResourceBinding>>(`/v1/projects/${projectId}/bindings`),
  revalidateGitlabGroupBinding: (projectId: string, bindingId: string, connectionId: string) =>
    request<ResourceBinding>(`/v1/projects/${projectId}/bindings/${bindingId}`, {
      method: 'PATCH',
      body: JSON.stringify({ connectionId }),
    }),
  deleteGitlabGroupBinding: (projectId: string, bindingId: string) =>
    request<Record<string, never>>(`/v1/projects/${projectId}/bindings/${bindingId}`, {
      method: 'DELETE',
    }),
  getGitlabRequirementBindings: (requirementId: string) =>
    request<ListResponse<ResourceBinding>>(`/v1/requirements/${requirementId}/bindings`),
  createGitlabRequirementBinding: (requirementId: string, body: CreateGitlabRequirementBindingPayload) =>
    request<ResourceBinding>(`/v1/requirements/${requirementId}/bindings`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateGitlabRequirementBinding: (requirementId: string, bindingId: string, body: UpdateGitlabRequirementBindingPayload) =>
    request<ResourceBinding>(`/v1/requirements/${requirementId}/bindings/${bindingId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteGitlabRequirementBinding: (requirementId: string, bindingId: string) =>
    request<Record<string, never>>(`/v1/requirements/${requirementId}/bindings/${bindingId}`, {
      method: 'DELETE',
    }),
}
