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

export type CreateZentaoConnectionPayload = {
  name: string
  baseUrl: string
  account: string
  password: string
}

export type UpdateZentaoConnectionPayload = Partial<CreateZentaoConnectionPayload>

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

export type CreateGitlabConnectionPayload = {
  name: string
  baseUrl: string
  accessToken: string
}

export type UpdateGitlabConnectionPayload = Partial<CreateGitlabConnectionPayload>

export type ReauthGitlabConnectionPayload = {
  accessToken?: string
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

export type ResourceBinding = {
  instanceUrl?: string
  bindingId?: string
  binding_id?: string
  provider: string
  connectionId?: string
  connection_id?: string
  localResourceType?: string
  local_resource_type?: string
  localResourceId?: string
  local_resource_id?: string
  remoteResourceType?: string
  remote_resource_type?: string
  remoteResourceId?: string
  remote_resource_id?: string
  remoteParentId?: string
  remote_parent_id?: string
  remoteNameSnapshot?: string
  remote_name_snapshot?: string
  status?: string
  boundAt?: string
  bound_at?: string
  lastVerifiedAt?: string
  last_verified_at?: string
  lastSyncError?: string
  last_sync_error?: string
  branch?: string
  baselineBranch?: string
  baseline_branch?: string
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type CreateGitlabGroupBindingPayload = {
  provider: 'gitlab'
  connectionId: string
  remoteResourceType: 'group'
  remoteResourceId: string
  remoteNameSnapshot: string
}

export type CreateGitlabRequirementBindingPayload = {
  connectionId?: string
  instanceUrl?: string
  provider: 'gitlab'
  remoteResourceType: 'repository'
  remoteResourceId: string
  remoteParentId: string
  remoteNameSnapshot: string
  extraJson: {
    branch: string
    baselineBranch?: string
  }
}

export type UpdateGitlabRequirementBindingPayload = {
  connectionId?: string
  branch?: string
  baselineBranch?: string
}

export type ZentaoRemoteListResponse<T> = {
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
  provider: 'zentao'
  connectionId: string
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

export type CreateLlmConnectionPayload = {
  name: string
  baseUrl: string
  modelId: string
  apiKey: string
}

export type UpdateLlmConnectionPayload = {
  name?: string
  baseUrl?: string
  modelId?: string
  apiKey?: string
}
