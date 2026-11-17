export type IntegrationConnectionStatus = 'active' | 'auth_failed' | 'disabled' | (string & {})

export type ZentaoConnection = {
  connectionId: string
  projectId?: string
  provider: 'zentao' | string
  name: string
  baseUrl: string
  authType: 'account_password' | string
  account: string
  status: IntegrationConnectionStatus
  hasAccessToken: boolean
  tokenExpiresAt?: string
  lastAuthAt?: string
  lastAuthError?: string
  createdAt?: string
  updatedAt?: string
}

export type GitlabConnection = {
  connectionId: string
  projectId?: string
  provider: 'gitlab' | string
  name: string
  baseUrl: string
  authType: 'personal_access_token' | string
  account: string
  status: IntegrationConnectionStatus
  hasAccessToken: boolean
  modelId?: string
  tokenExpiresAt?: string | null
  lastAuthAt?: string
  lastAuthError?: string
  createdAt?: string
  updatedAt?: string
}

export type GitlabGroup = {
  id?: string | number
  name?: string
  fullPath?: string
  parentId?: string | number | null
  description?: string
  webUrl?: string
  [key: string]: unknown
}

export type GitlabRepository = {
  id?: string | number
  name?: string
  path?: string
  pathWithNamespace?: string
  namespaceFullPath?: string
  defaultBranch?: string
  description?: string
  webUrl?: string
  [key: string]: unknown
}

export type GitlabBranch = {
  name?: string
  isDefault?: boolean
  isProtected?: boolean
  commitId?: string
  commitTitle?: string
  [key: string]: unknown
}

export type GitlabResourceListResponse<T> = {
  connectionId?: string
  groupId?: string
  repositoryId?: string
  items: T[]
  total: number
}

export type ZentaoRemoteOption = {
  id?: string | number
  name?: string
  code?: string
  title?: string
  remoteResourceId?: string
  remote_resource_id?: string
  remoteNameSnapshot?: string
  remote_name_snapshot?: string
  [key: string]: unknown
}

export type ZentaoBindingTargetType = 'project' | 'sprint' | 'requirement'

export type ZentaoBinding = {
  mcpServiceId?: string
  instanceUrl?: string
  bindingId?: string
  binding_id?: string
  provider: 'zentao' | string
  connectionId?: string
  connection_id?: string
  remoteResourceId?: string
  remote_resource_id?: string
  remoteNameSnapshot?: string
  remote_name_snapshot?: string
  status?: string
  boundAt?: string
  bound_at?: string
  createdAt?: string
  created_at?: string
}

export type CreateZentaoBindingPayload = {
  mcpServiceId?: string
  provider: 'zentao'
  connectionId?: string
  remoteResourceId: string
}

export type LlmConnection = {
  connectionId: string
  projectId?: string
  provider: 'llm' | string
  name: string
  baseUrl: string
  authType: 'api_key' | string
  account: string
  status: IntegrationConnectionStatus
  hasAccessToken: boolean
  modelId?: string
  createdAt?: string
  updatedAt?: string
}
