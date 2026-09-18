import { request, requestBlob, type ListResponse } from '@/shared/api/request'
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

function normalizeUploadDocumentType(documentType?: RequirementDocumentType) {
  if (documentType === 'word' || documentType === 'docx') return 'docx'
  return documentType
}

function buildRequirementJsonBody(body: RequirementCreatePayload | RequirementUpdatePayload) {
  const payload: Record<string, string> = {}

  if (body.name !== undefined) payload.name = body.name
  if (body.documentType !== undefined) payload.documentType = normalizeRequestDocumentType(body.documentType) ?? ''
  if (body.documentContent !== undefined) payload.documentContent = body.documentContent

  return JSON.stringify(payload)
}

function buildRequirementMultipartBody(body: RequirementDocumentUploadPayload) {
  const formData = new FormData()

  if (body.name !== undefined) formData.append('name', body.name)
  if (body.documentType !== undefined) {
    formData.append('documentType', normalizeUploadDocumentType(body.documentType) ?? '')
  }
  if (body.file) formData.append('file', body.file, body.file.name)

  return formData
}

export const requirementsApi = {
  getRequirements: (sprintId: string) => request<ListResponse<Requirement>>(`/v1/sprints/${sprintId}/requirements`),
  createRequirement: (sprintId: string, body: RequirementCreatePayload) => {
    if (body.file) {
      return request<Requirement>(`/v1/sprints/${sprintId}/requirements/upload`, {
        method: 'POST',
        body: buildRequirementMultipartBody(body),
      })
    }

    return request<Requirement>(`/v1/sprints/${sprintId}/requirements`, {
      method: 'POST',
      body: buildRequirementJsonBody(body),
    })
  },
  getRequirement: (requirementId: string) => request<Requirement>(`/v1/requirements/${requirementId}`),
  updateRequirement: (requirementId: string, body: RequirementUpdatePayload) =>
    request<Requirement>(`/v1/requirements/${requirementId}`, {
      method: 'PATCH',
      body: buildRequirementJsonBody(body),
    }),
  replaceRequirementDocument: (requirementId: string, body: RequirementDocumentUploadPayload) =>
    request<Requirement>(`/v1/requirements/${requirementId}/document`, {
      method: 'PUT',
      body: buildRequirementMultipartBody(body),
    }),
  downloadRequirementDocument: (requirementId: string) =>
    requestBlob(`/v1/requirements/${requirementId}/download`),
  deleteRequirement: (requirementId: string) =>
    request<Record<string, never>>(`/v1/requirements/${requirementId}`, { method: 'DELETE' }),
}
