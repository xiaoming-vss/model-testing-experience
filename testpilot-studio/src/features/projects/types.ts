export type ProjectRole = 'owner' | 'member' | 'viewer'
export type ProjectAction = 'read' | 'write' | 'execute' | 'review' | 'manage'
export type ProjectMember = { userId: string; name: string; role: ProjectRole }

export type Project = {
  role?: ProjectRole
  permissions?: ProjectAction[]
  projectId?: string
  project_id?: string
  userId?: string
  user_id?: string
  name: string
  description?: string
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type Sprint = {
  sprintId?: string
  sprint_id?: string
  projectId?: string
  project_id?: string
  name: string
  description?: string
  status: SprintStatus
  startTime?: string
  start_time?: string
  endTime?: string
  end_time?: string
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type SprintStatus = 'planned' | 'running' | 'completed'

export type SprintCreatePayload = {
  name: string
  description?: string
  startTime: string
  endTime: string
}

export type ProjectUpdatePayload = Partial<Pick<Project, 'name' | 'description'>>

export type SprintUpdatePayload = Partial<{
  name: string
  description: string
  startTime: string
  endTime: string
}>

export type SprintDailyMetricsTestStats = {
  total?: number
  executed?: number
  pending?: number
  unexecuted?: number
  success?: number
  failed?: number
  passed?: number
}

export type SprintDailyMetricsBugStats = {
  total?: number
  fatal?: number
  serious?: number
  severe?: number
  normal?: number
  suggestion?: number
  hint?: number
  resolved?: number
  closed?: number
  unresolved?: number
}

export type SprintDailyMetricsSnapshot = {
  sprintId?: string
  sprint_id?: string
  snapshotDate?: string
  snapshot_date?: string
  date?: string
  projectId?: string
  project_id?: string
  totalCases?: number
  total_cases?: number
  functional?: SprintDailyMetricsTestStats
  function?: SprintDailyMetricsTestStats
  functionTesting?: SprintDailyMetricsTestStats
  function_testing?: SprintDailyMetricsTestStats
  api?: SprintDailyMetricsTestStats
  ui?: SprintDailyMetricsTestStats
  bug?: SprintDailyMetricsBugStats
  bugs?: SprintDailyMetricsBugStats
  functionTotal?: number
  function_total?: number
  apiTotal?: number
  api_total?: number
  uiTotal?: number
  ui_total?: number
  bugTotal?: number
  bug_total?: number
  bugResolved?: number
  bug_resolved?: number
  bugClosed?: number
  bug_closed?: number
  bugUnresolved?: number
  bug_unresolved?: number
  bugFatal?: number
  bug_fatal?: number
  bugSevere?: number
  bug_severe?: number
  bugNormal?: number
  bug_normal?: number
  bugHint?: number
  bug_hint?: number
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}
export type CreateTestReportGenerateRunPayload = {
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
  snapshot_date?: string
  dailyMetrics?: SprintDailyMetricsSnapshot
  daily_metrics?: SprintDailyMetricsSnapshot
  [key: string]: unknown
}

export type TestReportGenerateRun = {
  runId?: string
  run_id?: string
  projectId?: string
  project_id?: string
  sprintId?: string
  sprint_id?: string
  status?: TestReportGenerateRunStatus
  connectionId?: string
  connection_id?: string
  llmConnectionId?: string
  llm_connection_id?: string
  instruction?: string
  resultYaml?: string
  result_yaml?: string
  resultSummaryJson?: unknown
  result_summary_json?: unknown
  errorMessage?: string
  error_message?: string
  snapshotJson?: TestReportGenerateRunSnapshot
  snapshot_json?: TestReportGenerateRunSnapshot
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
  startedAt?: string
  started_at?: string
  finishedAt?: string
  finished_at?: string
}

export type SprintCodeOverviewRepository = {
  instanceUrl?: string
  repositoryId: string
  name: string
  groupId: string
  branch: string
  baselineRef?: string | null
  baselineNote?: string
  isNewRepository?: boolean
  commitsCount?: number
  additions?: number
  deletions?: number
  error?: string
  remediation?: string
}

export type SprintCodeOverview = {
  sprintId: string
  projectId: string
  generatedAt: string
  repositories: SprintCodeOverviewRepository[]
}
