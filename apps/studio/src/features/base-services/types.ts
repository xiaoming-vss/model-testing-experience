export type IntegrationConnectionStatus = 'active' | 'auth_failed' | 'disabled' | (string & {})

export type GitlabConnection = {
  connectionId: string
  projectId?: string
  provider: 'gitlab' | string
  name: string
  baseUrl: string
  allowHttp?: boolean
  insecureSkipVerify?: boolean
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
  remoteNameSnapshot?: string
  [key: string]: unknown
}

export type { ZentaoBinding, ZentaoBindingTargetType } from '@/domain/projects/types'

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
