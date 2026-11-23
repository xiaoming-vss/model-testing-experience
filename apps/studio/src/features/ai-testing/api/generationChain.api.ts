import { request } from '@/shared/api/request'
import type { RequirementDesignKind } from './requirementDesign.api'

export type GenerationChainKind = RequirementDesignKind
export type GenerationChainStageState =
  | 'approved'
  | 'draft'
  | 'invalid'
  | 'running'
  | 'failed'
  | 'not_started'
  | 'imported'

export type UiGenerationSourceCommitMode = 'profile' | 'latest'

export type UiGenerationSourceCaseInput = {
  caseId: string
  title: string
  suiteName?: string
  module?: string
  content?: unknown
}

/** Frozen source projection returned with a UI generation version. No credentials or clone URL. */
export type UiGenerationSourceInputs = {
  sourceKind: 'repository'
  repository: {
    repositoryId: string
    pathWithNamespace: string
    branch: string
    commit: string
    commitMode: UiGenerationSourceCommitMode
    profileCandidateId: string
    resolvedAt: string
  }
  cases: UiGenerationSourceCaseInput[]
  sourceBatchId?: string
}

/** One repository candidate from a successful repository profile version. */
export type UiGenerationSourceRepository = {
  repositoryId: string
  pathWithNamespace: string
  role: string
  confidence: number
  responsibilitySummary: string
  keyPaths: string[]
  branch: string
  commit: string
  isFrontend: boolean
  available: boolean
  profileError: string
}

export type UiGenerationSourceCurrentProfile = {
  candidateId: string
  label: string
  createdAt: string
  repositories: UiGenerationSourceRepository[]
}

export type UiGenerationSourceOptions = {
  currentProfile: UiGenerationSourceCurrentProfile | null
}

export type UiGenerationSourceCheck = {
  pinnedCommit: string
  currentCommit: string
  branch: string
  changed: boolean
}

export type UiGenerationRunInputs = {
  refreshInputs?: boolean
  functionCaseIds?: string[]
  sourceProfileCandidateId: string
  sourceRepositoryId: string
  sourceCommitMode: UiGenerationSourceCommitMode
}

export type ModuleAgentProgress = {
  id: string
  module: string
  status: 'queued' | 'running' | 'repairing' | 'completed' | 'failed' | 'canceled'
  elapsedMs: number
  caseCount: number
  pointCount?: number
  repairAttempt: number
}

export type ModuleGenerationProgress = {
  stage?: 'detailed_cases' | 'case_names'
  reviewRound?: number
  issueCount?: number
  attemptId: string
  sequence: number
  concurrency: number
  status: 'running' | 'merging' | 'reviewing' | 'revising' | 'review_failed' | 'completed' | 'failed' | 'canceled'
  modules: ModuleAgentProgress[]
}

export type GenerationChainStage = {
  stage: string
  label: string
  order: number
  state: GenerationChainStageState
  upstreamStages: string[]
  blockedReason?: string
  errorMessage?: string
  failureRunId?: string
  failedAt?: string | null
  activeRunId?: string
  moduleGeneration?: ModuleGenerationProgress | null
}

export type GenerationChain = {
  kind: GenerationChainKind
  label: string
  configured: boolean
  candidateMode?: boolean
  taskId?: string
  runId?: string
  sourceBatchId?: string
  active?: boolean
  busy?: boolean
  sourceInputs?: UiGenerationSourceInputs | null
  sourceChanged?: boolean
  updatedAt?: string | null
  pendingCandidateCount: number
  continuationError?: string
  stages: GenerationChainStage[]
}

export type GenerationChainOverview = { chains: GenerationChain[] }

export const generationChainApi = {
  overview: (requirementId: string) =>
    request<GenerationChainOverview>(`/v1/requirements/${requirementId}/generation`),
  chain: (requirementId: string, kind: GenerationChainKind) =>
    request<GenerationChain>(`/v1/requirements/${requirementId}/generation/${kind}`),
  uiSourceOptions: (requirementId: string) =>
    request<UiGenerationSourceOptions>(
      `/v1/requirements/${requirementId}/generation/ui/source-options`,
    ),
  uiSourceCheck: (requirementId: string, body: {
    profileCandidateId: string
    repositoryId: string
    pinnedCommit: string
    gitlabConnectionId?: string
  }) =>
    request<UiGenerationSourceCheck>(
      `/v1/requirements/${requirementId}/generation/ui/source-check`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
}
