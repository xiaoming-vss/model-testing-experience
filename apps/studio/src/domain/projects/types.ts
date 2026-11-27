export type ProjectRole = 'owner' | 'member' | 'viewer' | 'developer'
export type ProjectAction = 'read' | 'write' | 'execute' | 'review' | 'manage' | 'project_read' | 'bug_read' | 'bug_handle'
export type ProjectMember = { userId: string; name: string; role: ProjectRole }

export type ZentaoBindingTargetType = 'project' | 'sprint' | 'requirement'

export type ZentaoBinding = {
  mcpServiceId?: string
  instanceUrl?: string
  bindingId?: string
  provider: 'zentao' | string
  connectionId?: string
  remoteResourceId?: string
  remoteNameSnapshot?: string
  status?: string
  boundAt?: string
  createdAt?: string
}

export type Project = {
  role?: ProjectRole
  isSuperAdmin?: boolean
  permissions?: ProjectAction[]
  projectId?: string
  userId?: string
  name: string
  description?: string
  createdAt?: string
  updatedAt?: string
}

export type Sprint = {
  zentaoBinding?: ZentaoBinding | null
  sprintId?: string
  projectId?: string
  name: string
  description?: string
  status: SprintStatus
  startTime?: string
  endTime?: string
  createdAt?: string
  updatedAt?: string
}

export type SprintStatus = 'planned' | 'running' | 'completed'

export type SprintCreatePayload = {
  name: string
  description?: string
  startTime: string
  endTime: string
}

export type DateLikeValue = string | Date | { toDate?: () => Date; toISOString?: () => string } | null | undefined

export type SprintFormValues = Omit<SprintCreatePayload, 'startTime' | 'endTime'> & {
  startTime: DateLikeValue
  endTime: DateLikeValue
}

export type ProjectUpdatePayload = Partial<Pick<Project, 'name' | 'description'>>

export type SprintUpdatePayload = Partial<{
  name: string
  description: string
  startTime: string
  endTime: string
}>

export type SprintDailyMetricsTestStats = {
  total: number
  executed: number
  pending: number
  success: number
  failed: number
}

export type SprintDailyMetricsBugStats = {
  total: number
  resolved: number
  closed: number
  unresolved: number
  fatal: number
  serious: number
  normal: number
  suggestion: number
}

/** 与后端 dump_metric 的响应字段一一对应。 */
export type SprintDailyMetricsSnapshot = {
  projectId: string
  sprintId: string
  snapshotDate: string
  function: SprintDailyMetricsTestStats
  api: SprintDailyMetricsTestStats
  ui: SprintDailyMetricsTestStats
  bug: SprintDailyMetricsBugStats | null
  createdAt?: string
  updatedAt?: string
}
export type CreateTestReportGenerateRunPayload = {
  requestId?: string
  sprintId: string
  snapshotDate: string
  connectionId: string
  instruction?: string
}

export type TestReportGenerateRunStatus =
  | 'pending'
  | 'claimed'
  | 'running'
  | 'waiting_review'
  | 'success'
  | 'failed'
  | 'error'
  | 'canceled'
  | (string & {})

export type TestReportGenerateRunSnapshot = {
  snapshotDate?: string
  dailyMetrics?: SprintDailyMetricsSnapshot
  [key: string]: unknown
}

export type TestReportGenerateRun = {
  runId?: string
  projectId?: string
  sprintId?: string
  status?: TestReportGenerateRunStatus
  connectionId?: string
  llmConnectionId?: string
  instruction?: string
  resultYaml?: string
  resultSummaryJson?: unknown
  errorMessage?: string
  snapshotJson?: TestReportGenerateRunSnapshot
  createdAt?: string
  updatedAt?: string
  startedAt?: string
  finishedAt?: string
}
