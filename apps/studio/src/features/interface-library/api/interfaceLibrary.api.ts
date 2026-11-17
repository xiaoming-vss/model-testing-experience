import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  ApiInterface,
  ApiInterfaceFilters,
  ApiInterfaceGroupMutation,
  ApiInterfaceListItem,
  CreateApiInterfaceGroupPayload,
  CreateApiInterfacePayload,
  CreateRequirementSoftwareRepositoryPayload,
  CreateSoftwareRepositoryPayload,
  DeleteApiInterfaceGroupPayload,
  ImportCommitResult,
  ImportPreview,
  MoveApiInterfaceGroupPayload,
  RenameApiInterfaceGroupPayload,
  RequirementSoftwareRepository,
  SoftwareRepository,
  UpdateApiInterfacePayload,
  UpdateRequirementSoftwareRepositoryPayload,
  UpdateSoftwareRepositoryPayload,
} from '../types'

function interfaceQuery(filters: ApiInterfaceFilters) {
  return buildQuery({
    softwareRepositoryId: filters.softwareRepositoryId,
    method: filters.method,
    requirementId: filters.requirementId,
    sprintId: filters.sprintId,
    keyword: filters.keyword,
    page: filters.page,
    pageSize: filters.pageSize,
  })
}

export const interfaceLibraryApi = {
  getSoftwareRepositories: (projectId: string) =>
    request<ListResponse<SoftwareRepository>>(
      `/v1/projects/${projectId}/software-repositories`,
    ),
  createSoftwareRepository: (projectId: string, body: CreateSoftwareRepositoryPayload) =>
    request<SoftwareRepository>(`/v1/projects/${projectId}/software-repositories`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateSoftwareRepository: (
    softwareRepositoryId: string,
    body: UpdateSoftwareRepositoryPayload,
  ) =>
    request<SoftwareRepository>(
      `/v1/software-repositories/${softwareRepositoryId}`,
      {
        method: 'PATCH',
        body: JSON.stringify(body),
      },
    ),
  deleteSoftwareRepository: (softwareRepositoryId: string) =>
    request<Record<string, never>>(
      `/v1/software-repositories/${softwareRepositoryId}`,
      { method: 'DELETE' },
    ),

  getProjectApiInterfaces: (projectId: string, filters: ApiInterfaceFilters = {}) =>
    request<ListResponse<ApiInterfaceListItem>>(
      `/v1/projects/${projectId}/api-interfaces${interfaceQuery(filters)}`,
    ),
  getSoftwareRepositoryApiInterfaces: (
    softwareRepositoryId: string,
    filters: ApiInterfaceFilters = {},
  ) =>
    request<ListResponse<ApiInterfaceListItem>>(
      `/v1/software-repositories/${softwareRepositoryId}/interfaces${interfaceQuery(filters)}`,
    ),
  createApiInterface: (
    softwareRepositoryId: string,
    body: CreateApiInterfacePayload,
  ) =>
    request<ApiInterface>(
      `/v1/software-repositories/${softwareRepositoryId}/interfaces`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    ),
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
  createApiInterfaceGroup: (
    softwareRepositoryId: string,
    body: CreateApiInterfaceGroupPayload,
  ) =>
    request<ApiInterfaceGroupMutation>(
      `/v1/software-repositories/${softwareRepositoryId}/interface-groups`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    ),
  renameApiInterfaceGroup: (
    softwareRepositoryId: string,
    body: RenameApiInterfaceGroupPayload,
  ) =>
    request<ApiInterfaceGroupMutation>(
      `/v1/software-repositories/${softwareRepositoryId}/interface-groups/rename`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    ),
  deleteApiInterfaceGroup: (
    softwareRepositoryId: string,
    body: DeleteApiInterfaceGroupPayload,
  ) =>
    request<ApiInterfaceGroupMutation>(
      `/v1/software-repositories/${softwareRepositoryId}/interface-groups/delete`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    ),
  moveApiInterfaceToGroup: (
    interfaceId: string,
    body: MoveApiInterfaceGroupPayload,
  ) =>
    request<ApiInterface>(
      `/v1/api-interfaces/${interfaceId}/group`,
      {
        method: 'PATCH',
        body: JSON.stringify(body),
      },
    ),

  previewOpenApiImport: (softwareRepositoryId: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file, file.name)
    return request<ImportPreview>(
      `/v1/software-repositories/${softwareRepositoryId}/interfaces/import/preview`,
      {
        method: 'POST',
        body: formData,
      },
    )
  },
  commitOpenApiImport: (
    softwareRepositoryId: string,
    payload: {
      file: File
      sourceDigest: string
      selectedKeys: string[]
      expectedItems: Record<string, number>
      applyBasePath: boolean
      expectedSoftwareRepositoryVersion?: number
    },
  ) => {
    const formData = new FormData()
    formData.append('file', payload.file, payload.file.name)
    formData.append('sourceDigest', payload.sourceDigest)
    formData.append('selectedKeys', JSON.stringify(payload.selectedKeys))
    formData.append('expectedItems', JSON.stringify(payload.expectedItems))
    formData.append('applyBasePath', String(payload.applyBasePath))
    if (payload.expectedSoftwareRepositoryVersion !== undefined) {
      formData.append(
        'expectedSoftwareRepositoryVersion',
        String(payload.expectedSoftwareRepositoryVersion),
      )
    }
    return request<ImportCommitResult>(
      `/v1/software-repositories/${softwareRepositoryId}/interfaces/import`,
      {
        method: 'POST',
        body: formData,
      },
    )
  },

  getRequirementSoftwareRepositories: (requirementId: string) =>
    request<ListResponse<RequirementSoftwareRepository>>(
      `/v1/requirements/${requirementId}/software-repositories`,
    ),
  createRequirementSoftwareRepository: (
    requirementId: string,
    body: CreateRequirementSoftwareRepositoryPayload,
  ) =>
    request<RequirementSoftwareRepository>(
      `/v1/requirements/${requirementId}/software-repositories`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    ),
  updateRequirementSoftwareRepository: (
    requirementId: string,
    softwareRepositoryId: string,
    body: UpdateRequirementSoftwareRepositoryPayload,
  ) =>
    request<RequirementSoftwareRepository>(
      `/v1/requirements/${requirementId}/software-repositories/${softwareRepositoryId}`,
      {
        method: 'PATCH',
        body: JSON.stringify(body),
      },
    ),
  deleteRequirementSoftwareRepository: (
    requirementId: string,
    softwareRepositoryId: string,
  ) =>
    request<Record<string, never>>(
      `/v1/requirements/${requirementId}/software-repositories/${softwareRepositoryId}`,
      { method: 'DELETE' },
    ),
}
