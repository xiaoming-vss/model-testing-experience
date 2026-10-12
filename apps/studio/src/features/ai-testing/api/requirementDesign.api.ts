import { buildQuery, request } from '@/shared/api/request'
import type { RequirementAnalysisTask, RequirementAnalysisTaskRun } from '../types'

export type RequirementDesignRun = RequirementAnalysisTaskRun & { hasResult?: boolean; availableArtifacts?: string[] }

export type RequirementDesignHistory = {
  items: RequirementDesignRun[]; total: number; statusCounts?: Record<string, number>;
  reviewPendingCount?: number; latestRun?: RequirementDesignRun
}

export type RequirementDesignKind = 'requirement_analysis' | 'function' | 'api' | 'ui'
export type RequirementDesignTask = {
  taskId: string
  kind: RequirementDesignKind
  name: string
  sourceType: string
  hasSource: boolean
  sourceFilename: string
  createdAt?: string
  updatedAt?: string
}
export type RequirementDesignOverview = {
  tasks: RequirementDesignTask[]
  runCounts: Record<RequirementDesignKind, number>
  adoptedUnderstanding: boolean
  activeTaskIds?: string[]
}
export type RequirementDesignConfiguration = {
  taskId?: string
  newConfiguration?: boolean
  requestId?: string
  sourceContent?: string
  instruction?: string
}
export const requirementDesignApi = {
  overview: (requirementId: string) => request<RequirementDesignOverview>(`/v1/requirements/${requirementId}/design`),
  history: (requirementId: string, kind: RequirementDesignKind, params: { page: number; pageSize: number; pipelineFilter: string }) =>
    request<RequirementDesignHistory>(`/v1/requirements/${requirementId}/design/${kind}/runs${buildQuery(params)}`),
  configure: (requirementId: string, kind: RequirementDesignKind, body: RequirementDesignConfiguration) =>
    request<RequirementAnalysisTask>(`/v1/requirements/${requirementId}/design/${kind}/configuration`, { method: 'POST', body: JSON.stringify(body) }),
  start: (requirementId: string, kind: RequirementDesignKind, body: { taskId: string; requestId: string; connectionId: string; checkpointEnabled: boolean; instruction?: string }) =>
    request<RequirementAnalysisTaskRun>(`/v1/requirements/${requirementId}/design/${kind}/run`, { method: 'POST', body: JSON.stringify(body) }),
}
