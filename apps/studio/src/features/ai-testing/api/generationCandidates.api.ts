import { request } from '@/shared/api/request'
import type { UiGenerationSourceCheck } from './generationChain.api'
import type {
  AdoptionCheck,
  CandidateAdoptBody,
  CandidateAdoptResult,
  CandidateChain,
  CandidateChainKind,
  CandidateDetail,
  CandidateDeriveBody,
  CandidateDeriveResult,
  CandidateDispositionBody,
  CandidateDispositionResult,
  CandidateEditBody,
  CandidateList,
  CandidateRelationsView,
  CandidateRevisionBody,
  CandidateRunBody,
  CandidateRunResult,
  CurrentImportBody,
  CurrentImportPreview,
  CurrentImportResult,
  CurrentStage,
} from './generationCandidates.contract'

function chainPath(requirementId: string, kind: CandidateChainKind) {
  return `/v1/requirements/${encodeURIComponent(requirementId)}/generation/${kind}`
}

function stagePath(requirementId: string, kind: CandidateChainKind, stage: string) {
  return `${chainPath(requirementId, kind)}/stages/${encodeURIComponent(stage)}`
}

function candidatePath(requirementId: string, kind: CandidateChainKind, stage: string) {
  return `${stagePath(requirementId, kind, stage)}/candidates`
}

export const generationCandidatesApi = {
  initialize: (requirementId: string, kind: CandidateChainKind, taskId: string) =>
    request<CandidateChain>(`${chainPath(requirementId, kind)}/candidate-chain`, {
      method: 'POST', body: JSON.stringify({ taskId }),
    }),
  current: (requirementId: string, kind: CandidateChainKind, stage: string) =>
    request<CurrentStage>(`${stagePath(requirementId, kind, stage)}/current`),
  relations: (requirementId: string, currentToken: string) =>
    request<CandidateRelationsView>(`${chainPath(requirementId, 'function')}/relations/current?currentToken=${encodeURIComponent(currentToken)}`),
  runRelations: (requirementId: string, body: { currentToken: string; connectionId: string; requestId: string }) =>
    request<{ attemptId: string; replayed: boolean }>(`${chainPath(requirementId, 'function')}/relations/current/run`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  run: (requirementId: string, kind: CandidateChainKind, stage: string, body: CandidateRunBody) =>
    request<CandidateRunResult>(`${stagePath(requirementId, kind, stage)}/candidate-run`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  revise: (requirementId: string, kind: CandidateChainKind, stage: string, candidateId: string, body: CandidateRevisionBody) =>
    request<CandidateRunResult>(`${candidatePath(requirementId, kind, stage)}/${encodeURIComponent(candidateId)}/revision`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  checkAdoption: (requirementId: string, kind: CandidateChainKind, stage: string, body: CandidateAdoptBody) =>
    request<AdoptionCheck>(`${stagePath(requirementId, kind, stage)}/adoption/check`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  adopt: (requirementId: string, kind: CandidateChainKind, stage: string, body: CandidateAdoptBody) =>
    request<CandidateAdoptResult>(`${stagePath(requirementId, kind, stage)}/adoption`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  previewImport: (requirementId: string, kind: CandidateChainKind, stage: string, body: { expectedCurrentToken: string; targetId?: string }) =>
    request<CurrentImportPreview>(`${stagePath(requirementId, kind, stage)}/current/import-preview`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  importCurrent: (requirementId: string, kind: CandidateChainKind, stage: string, body: CurrentImportBody) =>
    request<CurrentImportResult>(`${stagePath(requirementId, kind, stage)}/current/import`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  list: (requirementId: string, kind: CandidateChainKind, stage: string, page = 1, pageSize = 20) =>
    request<CandidateList>(`${candidatePath(requirementId, kind, stage)}?page=${page}&pageSize=${pageSize}`),
  detail: (requirementId: string, kind: CandidateChainKind, stage: string, candidateId: string) =>
    request<CandidateDetail>(`${candidatePath(requirementId, kind, stage)}/${encodeURIComponent(candidateId)}`),
  checkUiSource: (requirementId: string, stage: string, candidateId: string, body: { expectedCandidateToken: string; gitlabConnectionId?: string }) =>
    request<UiGenerationSourceCheck>(`${candidatePath(requirementId, 'ui', stage)}/${encodeURIComponent(candidateId)}/source-check`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  dispose: (requirementId: string, kind: CandidateChainKind, stage: string, candidateId: string, body: CandidateDispositionBody) =>
    request<CandidateDispositionResult>(`${candidatePath(requirementId, kind, stage)}/${encodeURIComponent(candidateId)}/disposition`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  edit: (requirementId: string, kind: CandidateChainKind, stage: string, candidateId: string, body: CandidateEditBody) =>
    request<CandidateDetail>(`${candidatePath(requirementId, kind, stage)}/${encodeURIComponent(candidateId)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  derive: (requirementId: string, kind: CandidateChainKind, stage: string, candidateId: string, body: CandidateDeriveBody) =>
    request<CandidateDeriveResult>(`${candidatePath(requirementId, kind, stage)}/${encodeURIComponent(candidateId)}/derive`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}
