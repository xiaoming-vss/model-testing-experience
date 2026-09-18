export type RequirementDocumentType = 'text' | 'word' | 'docx'

export type Requirement = {
  requirementId?: string
  requirement_id?: string
  sprintId?: string
  sprint_id?: string
  name: string
  documentType?: RequirementDocumentType
  documentContent?: string
  documentFilename?: string
  documentHash?: string
  documentDownloadUrl?: string
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type RequirementCreatePayload = {
  name: string
  documentType: RequirementDocumentType
  documentContent?: string
  file?: File
}

export type RequirementUpdatePayload = Partial<
  Pick<Requirement, 'name' | 'documentType' | 'documentContent'>
>

export type RequirementDocumentUploadPayload = {
  name?: string
  documentType?: RequirementDocumentType
  documentContent?: string
  file?: File
}
