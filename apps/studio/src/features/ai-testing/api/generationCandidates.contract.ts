/** Candidate read contracts and target contracts for subsequent write flows. */
import type { UiGenerationSourceInputs } from './generationChain.api'
export type CandidateChainKind = 'requirement_analysis' | 'function' | 'api' | 'ui'
export type CandidateDisposition = 'available' | 'rejected' | 'discarded'
export type CandidateSourceTrace = {
  chainKind: CandidateChainKind
  stage: string
  sourceKind: 'current' | 'candidate'
  candidateId: string
  snapshotId: string
}
export type CandidateBasisSource = {
  chainKind: CandidateChainKind
  stage: string
  sourceKind?: 'current' | 'candidate' | null
  candidateId: string
  snapshotId: string
  direct: boolean
}
export type CandidateSummary = {
  candidateId: string
  snapshotId: string
  candidateToken: string
  currentAttemptId: string | null
  derivedFromCandidateId: string | null
  disposition: CandidateDisposition
  generationMode: 'current' | 'trial'
  frozenAt: string | null
  createdBy: string
  createdAt: string
  isCurrent: boolean
}
export type CandidateList = {
  items: CandidateSummary[]
  total: number
  page: number
  pageSize: number
}
export type CandidateDetail = CandidateSummary & {
  content: string
  format: string
  sourceInputs?: UiGenerationSourceInputs | null
  materialContent?: string | null
  sourceTrace?: CandidateSourceTrace[]
  basisSources?: CandidateBasisSource[]
}
export type AdoptionBlockReason =
  | 'source_stale'
  | 'source_unknown'
  | 'source_conflict'
  | 'concurrent_change'

type SourceNode = { chainKind: CandidateChainKind; stage: string }
export type CandidateSourceSelection = SourceNode & {
  sourceKind: 'candidate'
  candidateId: string
  snapshotId: string
  expectedCandidateToken: string
  expectedCurrentToken?: never
}
export type CurrentSourceSelection = SourceNode & {
  sourceKind: 'current'
  expectedCurrentToken: string
  candidateId?: never
  snapshotId?: never
  expectedCandidateToken?: never
}
export type CandidateRunBody = {
  connectionId: string
  requestId?: string
  refreshInputs?: boolean
  functionCaseIds?: string[] | null
  instruction?: string | null
  configJson?: unknown
  sourceRepositoryId?: string | null
  sourceProfileCandidateId?: string | null
  sourceCommitMode?: 'profile' | 'latest'
  gitlabConnectionId?: string
} & (
  | { generationMode?: 'current'; sourceSelections?: [] }
  | { generationMode: 'trial'; sourceSelections: (CandidateSourceSelection | CurrentSourceSelection)[] }
)
export type CandidateAdoptBody = {
  action: 'adopt'
  candidateId: string
  expectedCandidateToken: string
  expectedAttemptId: string
  expectedCurrentToken: string
  requestId: string
  continueAfter?: boolean
  connectionId?: string
  instruction?: string
  gitlabConnectionId?: string
  comment?: string
}
export type CandidateEditBody = {
  expectedCandidateToken: string
  expectedAttemptId: string
  content: string
}
export type CandidateDeriveBody = CandidateEditBody & { requestId: string }
export type CandidateRevisionBody = {
  expectedCandidateToken: string
  expectedAttemptId: string
  connectionId: string
  instruction: string
  requestId: string
  attachmentFileIds?: string[]
  gitlabConnectionId?: string
}
export type CandidateDeriveResult = {
  requestId: string
  candidateId: string
  candidateToken: string
  snapshotId: string
}
export type CandidateDispositionBody = {
  action: 'reject' | 'discard'
  expectedCandidateToken: string
  requestId: string
  comment?: string
}
export type CandidateDispositionResult = {
  requestId: string
  candidateId: string
  disposition: 'rejected' | 'discarded'
  candidateToken: string
}
export type CurrentClearBody = { expectedCurrentToken: string; requestId: string }
export type CurrentImportBody = {
  expectedCurrentToken: string
  expectedLineageHash: string
  previewToken: string
  requestId: string
  targetId?: string
  confirmOverwrite?: boolean
}
export type CandidateChain = { chainId: string; taskId: string; created: boolean }
export type CandidateRunResult = { requestId: string; attemptId: string; replayed: boolean }
export type CurrentStage = {
  stage: string
  currentToken: string
  candidateId: string | null
  sourceAttemptId?: string | null
  content: string | null
  format: string | null
  invalidatedAt: string | null
  invalidatedReason: string | null
  active: boolean
  sourceInputs?: UiGenerationSourceInputs | null
  materialContent?: string | null
  sourceTrace?: CandidateSourceTrace[]
  basisSources?: CandidateBasisSource[]
}
export type CandidateRelationsView = {
  candidateId: string
  snapshotId: string
  currentToken: string
  sourceAttemptId: string | null
  resultYaml: string
  status: string
  attemptId: string | null
  errorMessage: string
  caseRelations: Record<string, unknown> | null
}
export type CandidateAdoptResult = {
  requestId: string
  candidateId: string
  contentToken: string
  replayed: boolean
  continuationAttemptId?: string | null
  continuationError?: string
}
export type CurrentClearResult = { requestId: string; contentToken: string; replayed: boolean }
export type CurrentImportPreview = {
  currentToken: string
  fullLineageHash: string
  contentHash: string
  basisHash: string
  candidateId: string
  targetId: string
  previewToken: string
  previewExpiresAt: number
  requiresConfirmation: boolean
  conflicts: Record<string, unknown>[]
}
export type CurrentImportResult = {
  imported: boolean
  replayed: boolean
  requiresConfirmation: boolean
  conflicts: Record<string, unknown>[]
  importRecords: Record<string, unknown>[]
  changedCaseIds: string[]
}
export type AdoptionCheck = {
  canAdopt: boolean
  lineageHash: string
  blockingSources: (SourceNode & { reason: AdoptionBlockReason })[]
}
