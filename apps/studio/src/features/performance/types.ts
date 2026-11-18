export type PerfDataFile = {
  fileId: string
  filename: string
  size: number
  sha256: string
}

export type PerfCaseSummary = {
  caseId: string
  projectId: string
  suiteId: string
  orderNo: number
  name: string
  version: number
  dataFiles: PerfDataFile[]
  createdAt?: string
  updatedAt?: string
}

export type PerfSuiteCase = PerfCaseSummary & {
  yaml: string
}

export type PerfCase = PerfCaseSummary & {
  yaml: string
  createdBy: string
}

export type CreatePerfCasePayload = {
  name: string
  yaml: string
  dataFileIds?: string[]
  suiteId?: string
  orderNo?: number
}

export type UpdatePerfCasePayload = {
  name?: string
  yaml?: string
  dataFileIds?: string[]
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
  remoteWriteUrl: string
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

export type PerfSuiteSummary = {
  suiteId: string
  projectId: string
  name: string
  description: string
  caseCount: number
  stepCount: number
  dataFileCount: number
  loadModels: string[]
  lastRunStatus: PerfRunStatus | ''
  lastRunOutcome: PerfRunOutcome | ''
  createdAt?: string
  updatedAt?: string
}

export type PerfSuite = PerfSuiteSummary & {
  cases: PerfSuiteCase[]
  createdBy: string
}

export type CreatePerfSuitePayload = {
  name: string
  description?: string
}

export type UpdatePerfSuitePayload = Partial<CreatePerfSuitePayload>

export type PerfSuiteRunItemStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'stopped'
  | 'canceled'
  | 'skipped'

export type PerfSuiteRunSummary = {
  suiteRunId: string
  suiteId: string
  projectId: string
  suiteName: string
  environmentId: string
  environmentName: string
  monitoringConnectionId: string
  monitoringConnectionName: string
  triggerUserId: string
  triggerType: string
  status: PerfRunStatus
  outcome?: PerfRunOutcome | ''
  totalCount: number
  completedCount: number
  failedCount: number
  skippedCount: number
  errorMessage: string
  startedAt?: string
  finishedAt?: string
  durationMs: number
  createdAt?: string
}

export type PerfSuiteRunItem = {
  itemId: string
  caseId: string
  caseName: string
  orderNo: number
  status: PerfSuiteRunItemStatus
  outcome?: PerfRunOutcome | ''
  childRunId: string
  errorMessage: string
  startedAt?: string
  finishedAt?: string
  durationMs: number
  summary?: Record<string, unknown> | null
  load?: Record<string, unknown> | null
  logTail: string
  flags: string[]
  k6Version: string
}

export type PerfSuiteRun = PerfSuiteRunSummary & {
  items: PerfSuiteRunItem[]
}

export type StartPerfSuiteRunPayload = StartPerfRunPayload

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
  remoteWriteUrl: string
  remoteWriteAuthType: MonitoringAuthType
  hasRemoteWriteCredentials: boolean
  enabled: boolean
  createdAt?: string
  updatedAt?: string
}

export type CreateMonitoringConnectionPayload = {
  name: string
  remoteWriteUrl: string
  remoteWriteAuth?: MonitoringAuthPayload
  enabled?: boolean
}

export type UpdateMonitoringConnectionPayload = Partial<CreateMonitoringConnectionPayload>
