import { request } from '@/shared/api/request'
import type {
  CandidateAdoptBody,
  CandidateAdoptResult,
  CandidateDetail,
  CandidateDispositionBody,
  CandidateDispositionResult,
  CandidateList,
  CurrentClearBody,
  CurrentClearResult,
  CurrentStage,
} from './generationCandidates.contract'

const base = (requirementId: string) => `/v1/requirements/${encodeURIComponent(requirementId)}/repository-profile`

export const profileCandidatesApi = {
  list: (requirementId: string, page = 1, pageSize = 20) =>
    request<CandidateList>(`${base(requirementId)}/candidates?page=${page}&pageSize=${pageSize}`),
  detail: (requirementId: string, candidateId: string) =>
    request<CandidateDetail>(`${base(requirementId)}/candidates/${encodeURIComponent(candidateId)}`),
  current: (requirementId: string) => request<CurrentStage>(`${base(requirementId)}/current`),
  adopt: (requirementId: string, body: CandidateAdoptBody) =>
    request<CandidateAdoptResult>(`${base(requirementId)}/current/adopt`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  clear: (requirementId: string, body: CurrentClearBody) =>
    request<CurrentClearResult>(`${base(requirementId)}/current/clear`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  dispose: (requirementId: string, candidateId: string, body: CandidateDispositionBody) =>
    request<CandidateDispositionResult>(`${base(requirementId)}/candidates/${encodeURIComponent(candidateId)}/disposition`, {
      method: 'POST', body: JSON.stringify(body),
    }),
}
