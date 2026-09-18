import { request, type ListResponse } from '@/shared/api/request'

export type ServiceProvider = 'llm' | 'zentao' | 'gitlab'
export type SharedService = {
  serviceId: string
  projectId: string
  provider: ServiceProvider
  name: string
  baseUrl: string
  modelId: string
  authorization: {
    status: 'unauthorized' | 'authorized' | 'invalid'
    connectionId?: string | null
    account?: string
    lastAuthAt?: string | null
  }
}
export type ServiceConfiguration = { name: string; baseUrl: string; modelId?: string }
export type PersonalAuthorization = { apiKey?: string; accessToken?: string; account?: string; password?: string }
const path = (projectId: string, provider: ServiceProvider, serviceId?: string) =>
  `/v1/projects/${encodeURIComponent(projectId)}/services/${provider}${serviceId ? `/${encodeURIComponent(serviceId)}` : ''}`

export const sharedServicesApi = {
  list: (projectId: string, provider: ServiceProvider) => request<ListResponse<SharedService>>(path(projectId, provider)),
  create: (projectId: string, provider: ServiceProvider, body: ServiceConfiguration) =>
    request<SharedService>(path(projectId, provider), { method: 'POST', body: JSON.stringify(body) }),
  rename: (projectId: string, provider: ServiceProvider, serviceId: string, name: string) =>
    request<SharedService>(path(projectId, provider, serviceId), { method: 'PATCH', body: JSON.stringify({ name }) }),
  delete: (projectId: string, provider: ServiceProvider, serviceId: string) =>
    request<Record<string, never>>(path(projectId, provider, serviceId), { method: 'DELETE' }),
  authorize: (projectId: string, provider: ServiceProvider, serviceId: string, body: PersonalAuthorization) =>
    request<SharedService>(`${path(projectId, provider, serviceId)}/authorization`, { method: 'PUT', body: JSON.stringify(body) }),
  revoke: (projectId: string, provider: ServiceProvider, serviceId: string) =>
    request<SharedService>(`${path(projectId, provider, serviceId)}/authorization`, { method: 'DELETE' }),
}
