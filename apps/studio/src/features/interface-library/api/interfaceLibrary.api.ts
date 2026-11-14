import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  ApiApp,
  ApiInterface,
  ApiInterfaceFilters,
  ApiInterfaceListItem,
  CreateApiAppPayload,
  CreateApiInterfacePayload,
  ImportCommitResult,
  ImportPreview,
  UpdateApiAppPayload,
  UpdateApiInterfacePayload,
} from '../types'

function interfaceQuery(filters: ApiInterfaceFilters) {
  return buildQuery({
    appId: filters.appId,
    method: filters.method,
    requirementId: filters.requirementId,
    sprintId: filters.sprintId,
    enabled: filters.enabled === undefined ? undefined : String(filters.enabled),
    keyword: filters.keyword,
    page: filters.page,
    pageSize: filters.pageSize,
  })
}

export const interfaceLibraryApi = {
  getApiApps: (projectId: string) =>
    request<ListResponse<ApiApp>>(`/v1/projects/${projectId}/api-apps`),
  createApiApp: (projectId: string, body: CreateApiAppPayload) =>
    request<ApiApp>(`/v1/projects/${projectId}/api-apps`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getApiApp: (appId: string) => request<ApiApp>(`/v1/api-apps/${appId}`),
  updateApiApp: (appId: string, body: UpdateApiAppPayload) =>
    request<ApiApp>(`/v1/api-apps/${appId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteApiApp: (appId: string) =>
    request<Record<string, never>>(`/v1/api-apps/${appId}`, { method: 'DELETE' }),

  getProjectApiInterfaces: (projectId: string, filters: ApiInterfaceFilters = {}) =>
    request<ListResponse<ApiInterfaceListItem>>(
      `/v1/projects/${projectId}/api-interfaces${interfaceQuery(filters)}`,
    ),
  getAppApiInterfaces: (appId: string, filters: ApiInterfaceFilters = {}) =>
    request<ListResponse<ApiInterfaceListItem>>(
      `/v1/api-apps/${appId}/interfaces${interfaceQuery(filters)}`,
    ),
  createApiInterface: (appId: string, body: CreateApiInterfacePayload) =>
    request<ApiInterface>(`/v1/api-apps/${appId}/interfaces`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getApiInterface: (interfaceId: string) =>
    request<ApiInterface>(`/v1/api-interfaces/${interfaceId}`),
  updateApiInterface: (interfaceId: string, body: UpdateApiInterfacePayload) =>
    request<ApiInterface>(`/v1/api-interfaces/${interfaceId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteApiInterface: (interfaceId: string) =>
    request<Record<string, never>>(`/v1/api-interfaces/${interfaceId}`, {
      method: 'DELETE',
    }),

  previewOpenApiImport: (appId: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file, file.name)
    return request<ImportPreview>(`/v1/api-apps/${appId}/interfaces/import/preview`, {
      method: 'POST',
      body: formData,
    })
  },
  commitOpenApiImport: (
    appId: string,
    payload: {
      file: File
      sourceDigest: string
      selectedKeys: string[]
      expectedItems: Record<string, number>
      applyBasePath: boolean
      expectedAppVersion?: number
    },
  ) => {
    const formData = new FormData()
    formData.append('file', payload.file, payload.file.name)
    formData.append('sourceDigest', payload.sourceDigest)
    formData.append('selectedKeys', JSON.stringify(payload.selectedKeys))
    formData.append('expectedItems', JSON.stringify(payload.expectedItems))
    formData.append('applyBasePath', String(payload.applyBasePath))
    if (payload.expectedAppVersion !== undefined) {
      formData.append('expectedAppVersion', String(payload.expectedAppVersion))
    }
    return request<ImportCommitResult>(`/v1/api-apps/${appId}/interfaces/import`, {
      method: 'POST',
      body: formData,
    })
  },
}
