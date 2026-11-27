import { request } from '@/shared/api/request'

export type RequirementDesignKind = 'requirement_analysis' | 'function' | 'api' | 'ui'
export type RequirementDesignTask = {
  taskId: string
  kind: RequirementDesignKind
  name: string
  sourceType: string
  hasSource: boolean
  sourceFilename: string
  interfaceIds?: string[]
  createdAt?: string
  updatedAt?: string
}
export type RequirementDesignOverview = {
  tasks: RequirementDesignTask[]
  runCounts: Record<RequirementDesignKind, number>
  activeTaskIds?: string[]
}
export type RequirementDesignConfiguration = {
  taskId?: string
  newConfiguration?: boolean
  requestId?: string
  sourceContent?: string
  interfaceIds?: string[]
  instruction?: string
}
export const requirementDesignApi = {
  overview: (requirementId: string) => request<RequirementDesignOverview>(`/v1/requirements/${requirementId}/design`),
  configure: (requirementId: string, kind: RequirementDesignKind, body: RequirementDesignConfiguration) =>
    request<{ taskId?: string }>(`/v1/requirements/${requirementId}/design/${kind}/configuration`, { method: 'POST', body: JSON.stringify(body) }),
}
