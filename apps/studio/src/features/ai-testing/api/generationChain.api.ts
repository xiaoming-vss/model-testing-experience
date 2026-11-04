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

export type GenerationChainVersion = {
  versionId: string
  stage?: string
  stageLabel?: string
  versionNo: number
  label: string
  summary: string
  artifactFormat: string
  createdAt?: string | null
  reviewerUserId?: string
  sourceRunId?: string
  sourceBatchId?: string
  imported?: boolean
}

export type UiGenerationSourceInputs = {
  archive: { fileId?: string; filename?: string; sha256?: string; sizeBytes?: number }
  cases: { caseId: string; title: string; suiteName?: string; module?: string; content?: unknown }[]
}

export type GenerationChainDraft = {
  attemptId: string
  runId: string
  status: string
  summary: string
  artifactFormat: string
  content: string
  revision: number
  baseVersionId?: string
  baseVersionLabel?: string
  upstreamVersions?: Record<string, string>
  sourceInputs?: UiGenerationSourceInputs | null
  instruction?: string
  invalidated?: boolean
  invalidatedReason?: string
  createdAt?: string | null
}

export type GenerationChainStage = {
  stage: string
  label: string
  order: number
  state: GenerationChainStageState
  latestVersion?: GenerationChainVersion | null
  draft?: GenerationChainDraft | null
  versions: GenerationChainVersion[]
  upstreamStages: string[]
  blockedReason?: string
  errorMessage?: string
  failureRunId?: string
  failedAt?: string | null
  activeRunId?: string
}

export type GenerationChainLeaf = {
  stage?: string
  versionId?: string
  versionNo?: number
  imported?: boolean
  importedTargets?: { targetType: string; targetId: string }[]
  importedAt?: string | null
}

export type GenerationChain = {
  kind: GenerationChainKind
  label: string
  configured: boolean
  taskId?: string
  runId?: string
  sourceBatchId?: string
  active?: boolean
  busy?: boolean
  sourceInputs?: UiGenerationSourceInputs | null
  sourceChanged?: boolean
  updatedAt?: string | null
  draftCount: number
  continuationError?: string
  stages: GenerationChainStage[]
  leaf: GenerationChainLeaf
}

export type GenerationChainOverview = { chains: GenerationChain[] }

export type GenerationChainVersionDetail = {
  versionId: string
  kind: GenerationChainKind
  stage: string
  stageLabel: string
  versionNo: number
  label: string
  summary: string
  artifactFormat: string
  content: string
  reviewerUserId: string
  reviewedAt?: string | null
  reviewComment: string
  upstreamVersions: Record<string, string>
  upstream: GenerationChainVersion[]
  sourceInputs?: UiGenerationSourceInputs | null
}

export type GenerationChainRunBody = {
  refreshInputs?: boolean
  functionCaseIds?: string[]
  connectionId: string
  requestId?: string
  instruction?: string
  upstreamVersions?: Record<string, string>
}

export type GenerationChainImportRecord = {
  importId: string
  versionId: string
  versionNo: number
  versionLabel: string
  leafStage: string
  parentVersions: Record<string, string>
  changedCaseIds: string[]
  changedCaseCount: number
  targetCaseCount: number
  mixedSource: boolean
  importedBy: string
  importedAt?: string | null
  reviewComment: string
}

export type GenerationChainImportTarget = {
  targetType: 'function_suite' | 'api_collection' | 'ui_suite'
  targetId: string
  name: string
  caseCount: number
  effectiveImportId?: string
  effectiveImport?: GenerationChainImportRecord | null
  sourceDeleted?: boolean
}

export type GenerationChainImportOptions = {
  kind: GenerationChainKind
  versionId: string
  versionLabel: string
  leafStage: string
  parentVersions: Record<string, string>
  parents: GenerationChainVersion[]
  targets: GenerationChainImportTarget[]
  targetRequired: boolean
}

export type GenerationChainImportResult = {
  requiresConfirmation: boolean
  conflicts: Record<string, unknown>[]
  imported: boolean
  targetId: string
  targetType: string
  changedCaseIds: string[]
  changedCaseCount: number
  importRecord?: GenerationChainImportRecord | null
  importRecords: GenerationChainImportRecord[]
  chain?: GenerationChain | null
}

export type GenerationChainReviewBody = {
  action: 'approve' | 'reject'
  expectedAttemptId?: string
  continueAfter?: boolean
  comment?: string
  connectionId?: string
  instruction?: string
  requestId?: string
}

export const generationChainApi = {
  overview: (requirementId: string) =>
    request<GenerationChainOverview>(`/v1/requirements/${requirementId}/generation`),
  chain: (requirementId: string, kind: GenerationChainKind) =>
    request<GenerationChain>(`/v1/requirements/${requirementId}/generation/${kind}`),
  version: (requirementId: string, kind: GenerationChainKind, versionId: string) =>
    request<GenerationChainVersionDetail>(
      `/v1/requirements/${requirementId}/generation/${kind}/versions/${versionId}`,
    ),
  run: (
    requirementId: string,
    kind: GenerationChainKind,
    stage: string,
    body: GenerationChainRunBody,
  ) =>
    request<GenerationChain>(
      `/v1/requirements/${requirementId}/generation/${kind}/stages/${stage}/run`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  revise: (
    requirementId: string,
    kind: GenerationChainKind,
    stage: string,
    body: { connectionId: string; instruction: string; requestId?: string; attachmentFileIds?: string[] },
  ) =>
    request<GenerationChain>(
      `/v1/requirements/${requirementId}/generation/${kind}/stages/${stage}/revision`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  review: (
    requirementId: string,
    kind: GenerationChainKind,
    stage: string,
    body: GenerationChainReviewBody,
  ) =>
    request<GenerationChain>(
      `/v1/requirements/${requirementId}/generation/${kind}/stages/${stage}/review`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  saveDraft: (
    requirementId: string,
    kind: GenerationChainKind,
    stage: string,
    body: { expectedAttemptId: string; content: string },
  ) =>
    request<GenerationChain>(
      `/v1/requirements/${requirementId}/generation/${kind}/stages/${stage}/draft`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),
  importOptions: (
    requirementId: string,
    kind: GenerationChainKind,
    versionId: string,
  ) =>
    request<GenerationChainImportOptions>(
      `/v1/requirements/${requirementId}/generation/${kind}/versions/${versionId}/import-options`,
    ),
  importVersion: (
    requirementId: string,
    kind: GenerationChainKind,
    versionId: string,
    body: { targetId?: string; confirmOverwrite?: boolean },
  ) =>
    request<GenerationChainImportResult>(
      `/v1/requirements/${requirementId}/generation/${kind}/versions/${versionId}/import`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  deleteVersion: (
    requirementId: string,
    kind: GenerationChainKind,
    versionId: string,
  ) =>
    request<{ versionId: string; deleted: boolean; invalidatedDraftCount: number }>(
      `/v1/requirements/${requirementId}/generation/${kind}/versions/${versionId}`,
      { method: 'DELETE' },
    ),
}
