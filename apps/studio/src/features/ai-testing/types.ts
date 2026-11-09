import type { ListResponse } from '@/shared/api/request'

export type RunHistoryResponse<T> = ListResponse<T> & { statusCounts?: Record<string, number>; reviewPendingCount?: number; latestRun?: T }

export type ApiCaseGenerateTaskSourceType = 'openapi' | 'swagger'
export type UiCaseGenerateTaskSourceType = 'source_archive'
export type FunctionalCaseGenerateTaskSourceType = 'text' | 'docx'
export type RequirementAnalysisTaskSourceType = 'text' | 'word' | 'docx' | string
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

export type GenerateTaskRunReviewStatus = 'pending' | 'approved' | 'rejected'
export type GenerateTaskRunImportStatus = 'pending' | 'imported'

export type ImportedTarget = {
  targetType: 'api_collection' | 'function_suite' | 'ui_suite'
  targetId: string
}

export type GenerateTaskRunImportLifecycle = {
  generationChainManaged?: boolean
  availableArtifacts?: string[]
  hasResult?: boolean
  reviewStatus: GenerateTaskRunReviewStatus
  importStatus: GenerateTaskRunImportStatus
  importedTargets: ImportedTarget[]
  importedAt: string | null
}

export type ApiCaseGenerateTaskRunReviewStatus = GenerateTaskRunReviewStatus
export type ApiCaseGenerateTaskRunImportStatus = GenerateTaskRunImportStatus
export type ApiCaseGenerateTaskRunImportedTarget = ImportedTarget

export type CaseGenerateTaskRunStatus = ApiCaseGenerateTaskRunStatus
export type CaseGenerateTaskRunReviewStatus = ApiCaseGenerateTaskRunReviewStatus
export type CaseGenerateTaskRunImportStatus = ApiCaseGenerateTaskRunImportStatus
export type CaseGenerateTaskRunImportedTarget = ApiCaseGenerateTaskRunImportedTarget

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

export type FunctionalCaseGenerateTaskStage =
  | 'enhanced_text'
  | 'requirement_analysis'
  | 'case_names'
  | 'detailed_cases'
  | 'relation_analysis'
  | 'completed'
  | string

export type RequirementAnalysisTaskStage =
  | 'extracting_text'
  | 'feature_understanding'
  | string

export type FunctionalCaseGenerateTaskStageStatus =
  | 'pending'
  | 'claimed'
  | 'running'
  | 'waiting_review'
  | 'success'
  | 'failed'
  | 'error'
  | 'canceled'
  | string

export type ApiCaseGenerateTask = {
  taskId?: string
  taskType?: 'api_case_generate' | string
  name: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  creatorUserId?: string
  sourceType: ApiCaseGenerateTaskSourceType
  sourceContent: string
  instruction: string
  createdAt?: string
  updatedAt?: string
}

export type UiCaseSourceArchive = {
  fileId?: string
  archiveId: string
  filename: string
  sizeBytes: number
  sha256: string
  uploadedAt: string
}

export type UiCaseGenerateTask = {
  taskId?: string
  taskType?: 'ui_case_generate' | string
  name: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  creatorUserId?: string
  sourceType: UiCaseGenerateTaskSourceType
  sourceArchive: UiCaseSourceArchive | null
  instruction: string
  createdAt?: string
  updatedAt?: string
}

export type UiCaseGenerateTaskRunSnapshot = {
  instruction?: string
  name?: string
  projectId?: string
  requirementId?: string
  runId?: string
  sourceType?: UiCaseGenerateTaskSourceType
  sprintId?: string
  taskId?: string
  taskType?: string
  sourceArchive?: UiCaseSourceArchive | null
  [key: string]: unknown
}

export type UiCaseGenerateTaskRun = GenerateTaskRunImportLifecycle & {
  checkpointEnabled?: boolean
  currentStage?: string
  stageStatus?: string
  snapshotJson?: UiCaseGenerateTaskRunSnapshot
  runId?: string
  taskId?: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  status?: CaseGenerateTaskRunStatus
  reviewerUserId?: string
  reviewedAt?: string
  reviewComment?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  errorMessage?: string
  createdAt?: string
  updatedAt?: string
  triggerType?: string
  triggerUserId?: string
  snapshot?: UiCaseGenerateTaskRunSnapshot
  configJson?: unknown
  resultYaml?: string
  resultSummaryJson?: unknown
}

export type ApiCaseGenerateTaskRunSnapshot = {
  instruction?: string
  name?: string
  projectId?: string
  requirementId?: string
  runId?: string
  sourceContent?: string
  sourceType?: ApiCaseGenerateTaskSourceType | string
  sprintId?: string
  taskId?: string
  taskType?: string
}

export type ApiCaseGenerateTaskRun = GenerateTaskRunImportLifecycle & {
  checkpointEnabled?: boolean
  currentStage?: string
  stageStatus?: string
  runId?: string
  taskId?: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  status?: ApiCaseGenerateTaskRunStatus
  reviewerUserId?: string
  reviewedAt?: string
  reviewComment?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  errorMessage?: string
  createdAt?: string
  updatedAt?: string
  triggerType?: string
  triggerUserId?: string
  snapshot?: ApiCaseGenerateTaskRunSnapshot
  configJson?: string
  resultYaml?: string
  resultSummaryJson?: string
}

export type CreateApiCaseGenerateTaskPayload = {
  name: string
  sprintId: string
  requirementId: string
  sourceType: ApiCaseGenerateTaskSourceType
  sourceContent: string
  instruction: string
}

export type CreateUiCaseGenerateTaskPayload = {
  name: string
  sprintId: string
  requirementId: string
  instruction?: string
}

export type UpdateUiCaseGenerateTaskPayload = Partial<CreateUiCaseGenerateTaskPayload>

export type RunUiCaseGenerateTaskPayload = {
  functionCaseIds?: string[]
  checkpointEnabled?: boolean
  connectionId: string
}

export type UpdateUiCaseGenerateTaskRunResultPayload = {
  resultYaml: string
}

export type ReviewUiCaseGenerateTaskRunPayload =
  | { action: 'approve'; reviewComment?: string }
  | { action: 'reject'; reviewComment?: string }

export type ImportUiCaseGenerateTaskRunPayload = {
  suiteId: string
  confirmOverwrite: boolean
}

export type UiCaseGenerateTaskRunImportStep = {
  orderNo?: unknown
  stepName?: unknown
  keyword?: unknown
  locatorType?: unknown
  locatorValue?: unknown
  operationValue?: unknown
  continueOnFailure?: unknown
  enabled?: unknown
  [key: string]: unknown
}

export type UiCaseGenerateTaskRunImportCase = {
  name: string
  enabled: boolean
  orderNo: number
  stepsJson: unknown
}

export type UiCaseGenerateTaskRunImportConflict = {
  normalizedName: string
  existingCase: UiCaseGenerateTaskRunImportCase
  generatedCase: UiCaseGenerateTaskRunImportCase
}

export type UiCaseGenerateTaskRunImportResult = {
  requiresConfirmation: boolean
  conflicts: UiCaseGenerateTaskRunImportConflict[]
  run: UiCaseGenerateTaskRun
}

export type UpdateApiCaseGenerateTaskPayload = Partial<CreateApiCaseGenerateTaskPayload>

export type UpdateApiCaseGenerateTaskRunResultPayload = {
  resultYaml: string
}

export type ImportApiCaseGenerateTaskRunPayload = {
  collectionId: string
  confirmOverwrite: boolean
}

export type ApiCaseGenerateTaskRunImportExtractRule = {
  name: string
  enabled: boolean
  orderNo: number
  source: string
  sourceExpr: string
  varKey: string
  defaultValue: string
}

export type ApiCaseGenerateTaskRunImportAssertRule = {
  name: string
  enabled: boolean
  orderNo: number
  assertSource: string
  targetExpr: string
  comparator: string
  expectedValue: string
}

export type ApiCaseGenerateTaskRunImportCase = {
  name: string
  description: string
  enabled: boolean
  orderNo: number
  method: string
  urlTemplate: string
  headers: unknown
  query: unknown
  bodyType: string
  bodyJson: unknown
  bodyText: string
  timeoutMs: number
  continueOnFailure: boolean
  extractRules: ApiCaseGenerateTaskRunImportExtractRule[]
  assertRules: ApiCaseGenerateTaskRunImportAssertRule[]
}

export type ApiCaseGenerateTaskRunImportConflict = {
  normalizedName: string
  existingCase: ApiCaseGenerateTaskRunImportCase
  generatedCase: ApiCaseGenerateTaskRunImportCase
}

export type ImportApiCaseGenerateTaskRunResult = {
  requiresConfirmation: boolean
  conflicts: ApiCaseGenerateTaskRunImportConflict[]
  run: ApiCaseGenerateTaskRun
}

export type FunctionalCaseGenerateTask = {
  taskId?: string
  taskType?: 'functional_case_generate' | string
  name: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  creatorUserId?: string
  instruction: string
  createdAt?: string
  updatedAt?: string
}

export type RequirementAnalysisTask = {
  taskId?: string
  taskType?: 'requirement_analysis' | string
  name: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  creatorUserId?: string
  sourceType?: RequirementAnalysisTaskSourceType
  sourceContent?: string
  instruction: string
  createdAt?: string
  updatedAt?: string
}

export type FunctionalCaseGenerateTaskRunSnapshot = {
  generationChainManaged?: boolean
  instruction?: string
  name?: string
  projectId?: string
  requirementId?: string
  runId?: string
  sourceContent?: string
  sourceType?: FunctionalCaseGenerateTaskSourceType | string
  sprintId?: string
  taskId?: string
  taskType?: string
}

export type RequirementAnalysisTaskRunSnapshot = {
  workflowVersion?: number
  instruction?: string
  name?: string
  projectId?: string
  requirementId?: string
  runId?: string
  sourceContent?: string
  sourceType?: RequirementAnalysisTaskSourceType
  sprintId?: string
  taskId?: string
  taskType?: string
  [key: string]: unknown
}

export type FunctionalCaseGenerateTaskRun = GenerateTaskRunImportLifecycle & {
  snapshotJson?: FunctionalCaseGenerateTaskRunSnapshot
  runId?: string
  taskId?: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  status?: ApiCaseGenerateTaskRunStatus
  reviewerUserId?: string
  reviewedAt?: string
  reviewComment?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  errorMessage?: string
  createdAt?: string
  updatedAt?: string
  triggerType?: string
  triggerUserId?: string
  snapshot?: FunctionalCaseGenerateTaskRunSnapshot
  configJson?: unknown
  resultYaml?: string
  resultSummaryJson?: unknown
  checkpointEnabled?: boolean
  currentStage?: FunctionalCaseGenerateTaskStage
  stageStatus?: FunctionalCaseGenerateTaskStageStatus
  stageOutput?: unknown
}

export type RequirementAnalysisTaskRun = {
  generationChainManaged?: boolean
  importStatus?: GenerateTaskRunImportLifecycle['importStatus']
  /** 历史摘要按已发布阶段返回，详情接口按 configJson 返回，均为后端真实产物。 */
  availableArtifacts?: string[]
  hasResult?: boolean
  workflowVersion?: number
  runId?: string
  taskId?: string
  projectId?: string
  sprintId?: string
  requirementId?: string
  status?: ApiCaseGenerateTaskRunStatus
  reviewStatus?: ApiCaseGenerateTaskRunReviewStatus
  reviewerUserId?: string
  reviewedAt?: string
  reviewComment?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  errorMessage?: string
  createdAt?: string
  updatedAt?: string
  triggerType?: string
  triggerUserId?: string
  checkpointEnabled?: boolean
  currentStage?: RequirementAnalysisTaskStage
  stageStatus?: FunctionalCaseGenerateTaskStageStatus
  snapshotJson?: RequirementAnalysisTaskRunSnapshot
  configJson?: unknown
  firstStepOutput?: string | Record<string, unknown>
  resultYaml?: string
  resultSummaryJson?: unknown
}

export type CreateFunctionalCaseGenerateTaskPayload = {
  name: string
  sprintId: string
  requirementId: string
  instruction: string
}

export type UpdateFunctionalCaseGenerateTaskPayload = Partial<CreateFunctionalCaseGenerateTaskPayload>

export type RunFunctionalCaseGenerateTaskPayload = {
  connectionId: string
  checkpointEnabled?: boolean
  requirementUnderstandingVersionId?: string
}

export type CreateRequirementAnalysisTaskPayload = {
  name: string
  requirementId: string
  instruction?: string
}

export type UpdateRequirementAnalysisTaskPayload = Partial<CreateRequirementAnalysisTaskPayload>

export type RunRequirementAnalysisTaskPayload = {
  connectionId: string
  instruction?: string
  triggerType?: 'manual' | string
  checkpointEnabled?: boolean
  configJson?: string
}

export type ReviewApiCaseGenerateTaskRunPayload =
  | {
      action: 'approve'
      reviewComment?: string
    }
  | {
      action: 'reject'
      reviewComment?: string
    }

export type ReviewFunctionalCaseGenerateTaskRunPayload =
  | {
      action: 'approve'
      reviewComment?: string
    }
  | {
      action: 'reject'
      reviewComment?: string
    }

export type UpdateFunctionalCaseGenerateTaskRunResultPayload = {
  resultYaml: string
}

export type ImportFunctionalCaseGenerateTaskRunPayload = {
  confirmOverwrite: boolean
  requirementId?: string
}

export type FunctionalCaseGenerateTaskRunImportCase = {
  module: string
  title: string
  preconditions: string
  steps: string
  expectedResults: string
  priority: string
  caseType: string
}

export type FunctionalCaseGenerateTaskRunImportConflict = {
  normalizedName: string
  existingCase: FunctionalCaseGenerateTaskRunImportCase
  generatedCase: FunctionalCaseGenerateTaskRunImportCase
}

export type ImportFunctionalCaseGenerateTaskRunResult = {
  requiresConfirmation: boolean
  conflicts: FunctionalCaseGenerateTaskRunImportConflict[]
  run: FunctionalCaseGenerateTaskRun
}

export type UpdateFunctionalCaseGenerateTaskRunStageOutputPayload = {
  stage: string
  configJson: string
}

export type UpdateRequirementAnalysisTaskRunStageOutputPayload = {
  stage: string
  configJson: Record<string, unknown>
  resultYaml?: string
}

export type ReviewFunctionalCaseGenerateTaskRunStagePayload = { llmConnectionId?: string } & (
  | {
      stage: string
      action: 'approve'
      comment?: string
    }
  | {
      stage: string
      action: 'reject'
      comment?: string
    }
)

export type RetryFunctionalCaseGenerateTaskRunStagePayload = {
  llmConnectionId?: string
  stage: string
}

export type ReviewRequirementAnalysisTaskRunStagePayload = {
  llmConnectionId?: string
  stage: string
  action: 'approve' | 'reject'
  configJson: Record<string, unknown>
}

export type ReviseRequirementAnalysisTaskRunStagePayload = {
  llmConnectionId?: string
  stage: string
  revisionInstruction: string
  configJson: Record<string, unknown>
  resultYaml?: string
  attachmentFileIds?: string[]
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
  requirementUnderstandingVersionId?: string
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

export type RepositoryProfileSnapshotBinding = {
  bindingId?: string
  repositoryId?: string
  pathWithNamespace?: string
  branch?: string
  headCommit?: string
  profileError?: string
  [key: string]: unknown
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
  snapshotJson?: {
    requirementUnderstandingVersion?: {
      versionId?: string
      versionNo?: number
      taskId?: string
      runId?: string
      [key: string]: unknown
    } | null
    bindings?: RepositoryProfileSnapshotBinding[]
    [key: string]: unknown
  }
  configJson?: unknown
  resultYaml?: string
  resultSummaryJson?: unknown
  createdAt?: string
  updatedAt?: string
  profile?: RepositoryProfile | null
}

/** 一次成功的仓库画像运行投影为一个不可变版本。 */
export type RepositoryProfileVersion = {
  versionId: string
  versionNo: number
  label: string
  profile?: RepositoryProfile | null
  resultYaml: string
  sourceRunId: string
  requirementUnderstandingVersion?: {
    versionId?: string
    versionNo?: number
    taskId?: string
    runId?: string
    [key: string]: unknown
  } | null
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
  requirementUnderstandingVersionId?: string
}
