import { useQuery } from '@tanstack/react-query'
import { getRunPollingInterval } from '@/domain/runs/polling'
import { isRunInProgress } from '@/domain/runs/status'
import { generationCandidatesApi } from '../api/generationCandidates.api'
import type { CandidateRelationsView } from '../api/generationCandidates.contract'

export type CandidateRelationsSource = { requirementId: string; currentToken: string }

export function relationQueryKey(candidate: CandidateRelationsSource) {
  return ['candidateRelations', candidate.requirementId, candidate.currentToken]
}

const failedStatuses = ['failed', 'error', 'canceled']

export function relationGenerating(view?: Pick<CandidateRelationsView, 'status'>) {
  return isRunInProgress(view?.status)
}

export function relationFailed(view?: Pick<CandidateRelationsView, 'status'>) {
  return failedStatuses.includes(view?.status ?? '')
}

export function useFunctionalCaseRelationsRun(
  candidate: CandidateRelationsSource,
  enabled = true,
  poll = true,
) {
  return useQuery({
    queryKey: relationQueryKey(candidate),
    queryFn: () => generationCandidatesApi.relations(candidate.requirementId, candidate.currentToken),
    enabled: enabled && Boolean(candidate.currentToken),
    refetchInterval: query =>
      poll && relationGenerating(query.state.data) ? getRunPollingInterval('running') : false,
    refetchIntervalInBackground: true,
  })
}
