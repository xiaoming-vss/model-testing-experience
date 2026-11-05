import type { ZentaoBinding } from '@/features/base-services/types'

export type RequirementDocumentType = 'word' | 'docx' | 'richtext'

export type Requirement = {
  codeBindings?: { repository: string; branch: string }[]
  zentaoBinding?: ZentaoBinding | null
  requirementId?: string
  requirement_id?: string
  sprintId?: string
  sprint_id?: string
  name: string
  documentType?: RequirementDocumentType
  documentContent?: string
  documentFilename?: string
  documentHash?: string
  documentFileId?: string
  documentDownloadUrl?: string
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type RequirementListItem = Requirement & { sprintName: string }

/** 下拉选项：只包含识别与展示字段，接口不返回 documentContent。 */
export type RequirementOption = {
  requirementId: string
  sprintId: string
  sprintName: string
  name: string
  documentFilename?: string
  createdAt?: string
}

export type RequirementCreatePayload = {
  name: string
  documentType: RequirementDocumentType
  documentContent?: string
  file?: File
  onUploadProgress?: (percent: number) => void
}

export type RequirementUpdatePayload = Partial<
  Pick<Requirement, 'name' | 'documentType' | 'documentContent' | 'documentFileId'>
>

export type RequirementDocumentUploadPayload = {
  name?: string
  documentType?: RequirementDocumentType
  documentContent?: string
  file?: File
  onUploadProgress?: (percent: number) => void
}
