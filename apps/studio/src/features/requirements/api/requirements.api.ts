import { request, requestBlob, type ListResponse } from '@/shared/api/request'
import { storageCapabilities, uploadStoredFile } from '@/shared/api/files'
import type {
  Requirement,
  RequirementCreatePayload,
  RequirementDocumentType,
  RequirementDocumentUploadPayload,
  RequirementUpdatePayload,
} from '../types'

function normalizeRequestDocumentType(documentType?: RequirementDocumentType) {
  if (documentType === 'docx') return 'word'
  return documentType
}

function buildRequirementJsonBody(body: RequirementCreatePayload | RequirementUpdatePayload) {
  const payload: Record<string, string> = {}

  if (body.name !== undefined) payload.name = body.name
  if (body.documentType !== undefined) payload.documentType = normalizeRequestDocumentType(body.documentType) ?? ''
  if (body.documentContent !== undefined) payload.documentContent = body.documentContent

  return JSON.stringify(payload)
}

export const requirementsApi = {
  getRequirements: (sprintId: string) => request<ListResponse<Requirement>>(`/v1/sprints/${sprintId}/requirements`),
  createRequirement: async (sprintId: string, body: RequirementCreatePayload) => {
    const capabilities = await storageCapabilities()
    if (!capabilities.enabled) throw new Error('S3 文件存储未启用，请联系管理员配置')
    const file = body.file ?? (body.documentContent
      ? new File([body.documentContent], 'requirement.txt', { type: 'text/plain' }) : undefined)
    if (file) {
      const sprint = await request<{ projectId: string }>(`/v1/sprints/${sprintId}`)
      if (file.size > capabilities.maxBytes) throw new Error('文件超过大小限制')
      const documentFileId = await uploadStoredFile(sprint.projectId, file, 'requirement', body.onUploadProgress)
      return request<Requirement>(`/v1/sprints/${sprintId}/requirements`, {
        method: 'POST', body: JSON.stringify({ name: body.name,
          documentType: normalizeRequestDocumentType(body.documentType), documentFileId }),
      })
    }
    throw new Error('请上传需求文件或填写需求内容')
  },
  getRequirement: (requirementId: string) => request<Requirement>(`/v1/requirements/${requirementId}`),
  updateRequirement: (requirementId: string, body: RequirementUpdatePayload) =>
    request<Requirement>(`/v1/requirements/${requirementId}`, {
      method: 'PATCH',
      body: buildRequirementJsonBody(body),
    }),
  replaceRequirementDocument: async (requirementId: string, body: RequirementDocumentUploadPayload) => {
    const capabilities = await storageCapabilities()
    if (!capabilities.enabled) throw new Error('S3 文件存储未启用，请联系管理员配置')
    if (body.file) {
      if (body.file.size > capabilities.maxBytes) throw new Error('文件超过大小限制')
      const requirement = await request<Requirement>(`/v1/requirements/${requirementId}`)
      const sprint = await request<{ projectId: string }>(`/v1/sprints/${requirement.sprintId ?? requirement.sprint_id}`)
      const documentFileId = await uploadStoredFile(sprint.projectId, body.file, 'requirement', body.onUploadProgress)
      return request<Requirement>(`/v1/requirements/${requirementId}`, {
        method: 'PATCH', body: JSON.stringify({ documentFileId,
          documentType: normalizeRequestDocumentType(body.documentType) }),
      })
    }
    throw new Error('请选择需求文件')
  },
  downloadRequirementDocument: (requirementId: string) =>
    requestBlob(`/v1/requirements/${requirementId}/download`, { headers: { Accept: 'application/json' } }, true),
  deleteRequirement: (requirementId: string) =>
    request<Record<string, never>>(`/v1/requirements/${requirementId}`, { method: 'DELETE' }),
}
