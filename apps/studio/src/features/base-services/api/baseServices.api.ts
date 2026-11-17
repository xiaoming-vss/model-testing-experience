import { request, type ListResponse } from '@/shared/api/request'
import type {
  CreateZentaoBindingPayload,
  GitlabBranch,
  GitlabConnection,
  GitlabGroup,
  GitlabRepository,
  GitlabResourceListResponse,
  LlmConnection,
  ZentaoBinding,
  ZentaoConnection,
} from '../types'

function integrationPath(projectId: string, provider: 'llm' | 'zentao' | 'gitlab') {
  return `/v1/projects/${encodeURIComponent(projectId)}/integrations/${provider}/connections`
}

function integrationConnectionPath(projectId: string, provider: 'llm' | 'zentao' | 'gitlab', connectionId: string) {
  return `${integrationPath(projectId, provider)}/${encodeURIComponent(connectionId)}`
}

export const baseServicesApi = {
  updateZentaoBinding: (target: 'project' | 'sprint' | 'requirement', resourceId: string, bindingId: string, body: { connectionId?: string; remoteResourceId: string; mcpServiceId?: string; confirmInstanceSwitch?: boolean }) =>
    request<ZentaoBinding>(`/v1/${target}s/${resourceId}/bindings/${bindingId}`, { method: 'PATCH', body: JSON.stringify(body) }),
  getLlmConnections: (projectId: string) => request<ListResponse<LlmConnection>>(integrationPath(projectId, 'llm')),
  getGitlabConnections: (projectId: string) =>
    request<ListResponse<GitlabConnection>>(integrationPath(projectId, 'gitlab')),
  getZentaoConnections: (projectId: string) => request<ListResponse<ZentaoConnection>>(integrationPath(projectId, 'zentao')),
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
}
