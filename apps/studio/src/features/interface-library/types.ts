export type SoftwareRepositoryGitRepository = {
  projectId: string
  path: string
  name: string
  instanceUrl: string
}

export type SoftwareRepositoryGitRepositoryPayload = {
  connectionId: string
  groupId: string
  repositoryId: string
}

export type SoftwareRepository = {
  softwareRepositoryId: string
  projectId: string
  name: string
  description: string
  basePath: string
  repository: SoftwareRepositoryGitRepository | null
  interfaceGroups: string[]
  interfaceCount: number
  version: number
  createdAt?: string
  updatedAt?: string
}

export type CreateSoftwareRepositoryPayload = {
  name: string
  description?: string
  basePath?: string
  repository: SoftwareRepositoryGitRepositoryPayload
}

export type UpdateSoftwareRepositoryPayload = Partial<CreateSoftwareRepositoryPayload>

export type RequirementSoftwareRepository = {
  requirementId: string
  softwareRepositoryId: string
  softwareRepositoryName: string
  basePath: string
  repository: SoftwareRepositoryGitRepository | null
  branch: string
  baselineBranch: string
  createdByUserId?: string
  createdAt?: string
  updatedAt?: string
}

export type CreateRequirementSoftwareRepositoryPayload = {
  softwareRepositoryId: string
  branch: string
  baselineBranch: string
}

export type UpdateRequirementSoftwareRepositoryPayload = {
  branch?: string
  baselineBranch?: string
}

export type InterfaceRow = {
  enabled: boolean
  name: string
  type: string
  required: boolean
  example: string
  description: string
}

export type ApiInterfaceRequirement = {
  requirementId: string
  name: string
  sprintId: string
  sprintName: string
}

export type ApiInterfaceSource = {
  type: string
  name: string
  url: string
  version: string
  importedAt?: string | null
}

export type ApiInterfaceListItem = {
  interfaceId: string
  softwareRepositoryId: string
  softwareRepositoryName: string
  name: string
  method: string
  path: string
  description: string
  tags: string[]
  requirements: ApiInterfaceRequirement[]
  sourceType: string
  updatedAt?: string
}

export type ApiInterface = Omit<ApiInterfaceListItem, 'sourceType'> & {
  /** 列表接口返回来源类型；详情接口只返回 source 对象，字段可能缺省。 */
  sourceType?: string
  headers: InterfaceRow[]
  pathParams: InterfaceRow[]
  queryParams: InterfaceRow[]
  bodyType: 'none' | 'json' | 'form' | 'raw'
  bodySchema: unknown
  bodyExample: unknown
  bodyText: string
  responseStatus: number
  responseDescription: string
  responseSchema: unknown
  responseExample: unknown
  security: unknown
  securitySchemes: unknown
  version: number
  source: ApiInterfaceSource
  createdAt?: string
}

export type CreateApiInterfacePayload = {
  name: string
  method: string
  path: string
  description?: string
  tags?: string[]
  headers?: InterfaceRow[]
  pathParams?: InterfaceRow[]
  queryParams?: InterfaceRow[]
  bodyType?: 'none' | 'json' | 'form' | 'raw'
  bodySchema?: unknown
  bodyExample?: unknown
  bodyText?: string
  responseStatus?: number
  responseDescription?: string
  responseSchema?: unknown
  responseExample?: unknown
  requirementIds?: string[]
}

export type UpdateApiInterfacePayload = Partial<CreateApiInterfacePayload>

export type ApiInterfaceFilters = {
  softwareRepositoryId?: string
  method?: string
  requirementId?: string
  sprintId?: string
  keyword?: string
  page?: number
  pageSize?: number
}

export type ImportWarning = {
  code: string
  message: string
  method?: string
  path?: string
}

export type ImportItem = {
  key: string
  changeType: 'new' | 'modified' | 'unchanged' | 'library_only'
  method: string
  path: string
  name: string
  existingInterfaceId?: string | null
  existingVersion?: number | null
  changedFields: string[]
  /** 导入后的分组标签：新接口用文档标签，已有接口用库内标签。 */
  tags: string[]
  existingTags: string[]
}

export type ApiInterfaceGroupMutation = {
  groupName: string
  newGroupName: string
  updatedCount: number
}

export type RenameApiInterfaceGroupPayload = {
  currentGroupName: string
  newGroupName: string
}

export type CreateApiInterfaceGroupPayload = {
  groupName: string
}

export type DeleteApiInterfaceGroupPayload = {
  groupName: string
}

export type MoveApiInterfaceGroupPayload = {
  groupName: string
}

export type ImportPreview = {
  source: {
    type: string
    name: string
    url: string
    version: string
    digest: string
    basePath: string
  }
  softwareRepository: {
    softwareRepositoryId: string
    name: string
    basePath: string
  }
  summary: { new: number; modified: number; unchanged: number; libraryOnly: number }
  basePathChange: { current: string; document: string; canApply: boolean } | null
  warnings: ImportWarning[]
  items: ImportItem[]
}

export type ImportCommitResult = {
  created: number
  updated: number
  skipped: number
  libraryOnly: number
  softwareRepositoryBasePath: string
  interfaces: { key: string; interfaceId: string; changeType: string }[]
}
