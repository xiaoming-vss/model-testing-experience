export type PerfDataFile = {
  fileId: string
  filename: string
  size: number
  sha256: string
}

export type PerfCaseSummary = {
  caseId: string
  projectId: string
  name: string
  description: string
  version: number
  enabled: boolean
  dataFiles: PerfDataFile[]
  createdAt?: string
  updatedAt?: string
}

export type PerfCase = PerfCaseSummary & {
  yaml: string
  createdBy: string
}

export type CreatePerfCasePayload = {
  name: string
  description?: string
  yaml: string
  dataFileIds?: string[]
}

export type UpdatePerfCasePayload = {
  name?: string
  description?: string
  yaml?: string
  dataFileIds?: string[]
  enabled?: boolean
}

export type PerfRunStatus =
  | 'queued'
  | 'running'
  | 'stopping'
  | 'completed'
  | 'failed'
  | 'stopped'
  | 'canceled'

export type PerfRunOutcome =
  | 'passed'
  | 'threshold_failed'
  | 'inconclusive'
  | 'execution_error'
  | 'stopped'

export type PerfMonitoringSnapshot = {
  connectionId: string
  name: string
  queryUrl: string
  remoteWriteUrl: string
  grafanaUrl: string
  grafanaDashboardUid: string
  defaultFilters: Record<string, unknown>
}

export type PerfRunSummary = {
  runId: string
  caseId: string
  projectId: string
  caseVersion: number
  caseName: string
  environmentId: string
  environmentName: string
  monitoringConnectionId: string
  monitoringConnectionName: string
  triggerUserId: string
  triggerType: string
  status: PerfRunStatus
  outcome?: PerfRunOutcome | ''
  flags: string[]
  errorMessage: string
  k6Version: string
  templateVersion: string
  scriptSha256: string
  startedAt?: string
  finishedAt?: string
  durationMs: number
  createdAt?: string
}

export type PerfRun = PerfRunSummary & {
  summary?: Record<string, unknown> | null
  logTail: string
  runner?: Record<string, unknown> | null
  dataFiles: PerfDataFile[]
  monitoring?: PerfMonitoringSnapshot | null
}

export type StartPerfRunPayload = {
  environmentId: string
  monitoringConnectionId: string
}

export type MonitoringAuthType = 'none' | 'basic' | 'bearer' | 'headers'

export type MonitoringAuthPayload = {
  type: MonitoringAuthType
  username?: string
  password?: string
  token?: string
  headers?: Record<string, string>
}

export type MonitoringConnection = {
  connectionId: string
  projectId: string
  name: string
  queryUrl: string
  remoteWriteUrl: string
  queryAuthType: MonitoringAuthType
  remoteWriteAuthType: MonitoringAuthType
  hasQueryCredentials: boolean
  hasRemoteWriteCredentials: boolean
  grafanaUrl: string
  grafanaDashboardUid: string
  defaultFilters: Record<string, unknown>
  enabled: boolean
  createdAt?: string
  updatedAt?: string
}

export type CreateMonitoringConnectionPayload = {
  name: string
  queryUrl: string
  remoteWriteUrl: string
  queryAuth?: MonitoringAuthPayload
  remoteWriteAuth?: MonitoringAuthPayload
  grafanaUrl?: string
  grafanaDashboardUid?: string
  defaultFilters?: Record<string, unknown>
  enabled?: boolean
}

export type UpdateMonitoringConnectionPayload = Partial<CreateMonitoringConnectionPayload>
