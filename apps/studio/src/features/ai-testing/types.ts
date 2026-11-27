import type { ListResponse } from '@/shared/api/request'

export type RunHistoryResponse<T> = ListResponse<T> & { statusCounts?: Record<string, number>; reviewPendingCount?: number; latestRun?: T }
export type AiTaskListResponse<T> = ListResponse<T> & { statusCounts?: Record<string, number> }

export type ApiCaseGenerateTaskRunStatus =
  | 'draft'
  | 'pending'
  | 'claimed'
  | 'running'
  | 'success'
  | 'failed'
  | 'error'
  | 'canceled'
  | string

export type AiSkillLibraryItem = {
  skillSpaceId: string
  projectId?: string | null
  filename: string
  isDefault?: boolean
  downloadUrl?: string
  hash?: string
  size?: number
  fileCount?: number
  createdAt?: string
  updatedAt?: string
}

export type UploadAiSkillPayload = {
  files: File[]
}

export type CodeRiskTask = {
  taskId?: string
  taskType?: 'code_risk_analysis' | string
  name: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  creatorUserId?: string
  sourceType?: string
  sourceContent?: string
  instruction: string
  latestRunStatus?: ApiCaseGenerateTaskRunStatus
  createdAt?: string
  updatedAt?: string
}

export type CodeRiskReportRepository = {
  repositoryId?: string
  branch?: string
  baselineCommit?: string
  headCommit?: string
  filesChanged?: number
  additions?: number
  deletions?: number
  [key: string]: unknown
}

export type CodeRiskContextReceiptRepository = {
  repositoryId?: string
  instanceUrl?: string
  pathWithNamespace?: string
  branch?: string
  baselineBranch?: string
  baseCommit?: string
  headCommit?: string
  localPath?: string
  changedFiles?: string[]
  filesChanged?: number
  additions?: number
  deletions?: number
  [key: string]: unknown
}

export type CodeRiskContextReceipt = {
  mode?: string
  repositories?: CodeRiskContextReceiptRepository[]
  counts?: {
    repositories?: number
    changedFiles?: number
    diffChars?: number
    [key: string]: unknown
  }
  truncatedFiles?: string[]
  summary?: string
  filesRead?: string[]
  toolsUsed?: string[]
  receivedRepositories?: unknown[]
  [key: string]: unknown
}

export type CodeRiskReport = {
  analyzedAt?: string | null
  repositories?: CodeRiskReportRepository[]
  contextReceipt?: CodeRiskContextReceipt | null
  changeOverview?: {
    filesChanged?: number
    additions?: number
    deletions?: number
    [key: string]: unknown
  } | null
  risks?: Array<{
    level?: string
    location?: string
    reason?: string
    [key: string]: unknown
  }> | null
  affectedCases?: Array<{
    caseType?: string
    caseId?: string
    title?: string
    suiteId?: string
    suiteName?: string
    impact?: string
    [key: string]: unknown
  }> | null
  coverageGaps?: Array<{
    gap?: string
    suggestion?: string
    [key: string]: unknown
  }> | null
}

export type CodeRiskTaskRun = {
  availableArtifacts?: string[]
  hasResult?: boolean
  runId?: string
  taskId?: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  status?: ApiCaseGenerateTaskRunStatus
  triggerType?: string
  triggerUserId?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  errorMessage?: string
  currentStage?: string
  stageStatus?: string
  snapshot?: unknown
  configJson?: unknown
  resultYaml?: string
  resultSummaryJson?: unknown
  createdAt?: string
  updatedAt?: string
  report?: CodeRiskReport | null
}

export type CreateCodeRiskTaskPayload = {
  name?: string
  requirementId: string
  instruction?: string
}

export type RunCodeRiskTaskPayload = {
  requestId?: string
  gitlabConnectionIds?: Record<string, string>
  llmConnectionId?: string
  instruction?: string
  triggerType?: 'manual' | string
}

export type RepositoryProfileRole = 'frontend' | 'backend' | 'fullstack' | 'infra' | 'test' | 'unknown'

export type RepositoryProfileRepository = {
  repositoryId: string
  pathWithNamespace: string
  role: RepositoryProfileRole
  responsibilitySummary: string
  techStack: string[]
  keyPaths: string[]
  confidence: number
  evidence: string[]
}

export type RepositoryProfile = {
  repositories: RepositoryProfileRepository[]
  overallSummary: string
}

export type RepositoryProfileTask = {
  taskId?: string
  taskType?: 'repository_profile' | string
  name: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  creatorUserId?: string
  sourceType?: string
  sourceContent?: string
  instruction: string
  createdAt?: string
  updatedAt?: string
}

export type RepositoryProfileTaskRun = {
  availableArtifacts?: string[]
  hasResult?: boolean
  runId?: string
  taskId?: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  status?: ApiCaseGenerateTaskRunStatus
  triggerType?: string
  triggerUserId?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  errorMessage?: string
  currentStage?: string
  stageStatus?: string
  reviewStatus?: string
  configJson?: unknown
  resultYaml?: string
  resultSummaryJson?: unknown
  createdAt?: string
  updatedAt?: string
  profile?: RepositoryProfile | null
}

/** 仓库画像候选的展示数据。 */
export type RepositoryProfileCandidateView = {
  candidateId: string
  label: string
  profile?: RepositoryProfile | null
  resultYaml: string
  createdAt: string
}

export type CreateRepositoryProfileTaskPayload = {
  name?: string
  requirementId: string
  instruction?: string
}

export type RunRepositoryProfileTaskPayload = {
  requestId?: string
  gitlabConnectionIds?: Record<string, string>
  llmConnectionId?: string
  instruction?: string
  triggerType?: 'manual' | string
}
