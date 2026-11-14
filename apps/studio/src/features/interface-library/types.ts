export type ApiAppRepository = {
  projectId: string
  path: string
  name: string
  instanceUrl: string
}

export type ApiAppRepositoryPayload = {
  connectionId: string
  groupId: string
  repositoryId: string
}

export type ApiApp = {
  appId: string
  projectId: string
  name: string
  description: string
  basePath: string
  repository: ApiAppRepository | null
  enabled: boolean
  interfaceCount: number
  enabledInterfaceCount: number
  version: number
  createdAt?: string
  updatedAt?: string
}

export type CreateApiAppPayload = {
  name: string
  description?: string
  basePath?: string
  repository?: ApiAppRepositoryPayload | null
  enabled?: boolean
}

export type UpdateApiAppPayload = Partial<CreateApiAppPayload>

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
  appId: string
  appName: string
  name: string
  method: string
  path: string
  description: string
  tags: string[]
  requirements: ApiInterfaceRequirement[]
  enabled: boolean
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
  enabled?: boolean
  requirementIds?: string[]
}

export type UpdateApiInterfacePayload = Partial<CreateApiInterfacePayload>

export type ApiInterfaceFilters = {
  appId?: string
  method?: string
  requirementId?: string
  sprintId?: string
  enabled?: boolean
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
  app: { appId: string; name: string; basePath: string }
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
  appBasePath: string
  interfaces: { key: string; interfaceId: string; changeType: string }[]
}
