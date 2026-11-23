import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { FunctionalCaseGenerateTaskRun } from '../types'
import { generationCandidatesApi } from '../api/generationCandidates.api'

export type CandidateRelationsSource = { requirementId: string; currentToken: string }

export function relationQueryKey(runId: string, candidate?: CandidateRelationsSource) {
  return candidate ? ['candidateRelations', candidate.requirementId, candidate.currentToken] : ['functionalCaseGenerateTaskRun', runId]
}

export function relationGenerating(run?: FunctionalCaseGenerateTaskRun) {
  return run?.currentStage === 'relation_analysis' && ['pending', 'queued', 'claimed', 'running'].includes(run.status ?? '')
}

export function relationFailed(run?: FunctionalCaseGenerateTaskRun) {
  return run?.currentStage === 'relation_analysis' && ['failed', 'error', 'canceled'].includes(run.status ?? '')
}

export function useFunctionalCaseRelationsRun(runId: string, enabled = true, poll = true, candidate?: CandidateRelationsSource) {
  return useQuery({
    queryKey: relationQueryKey(runId, candidate),
    queryFn: async (): Promise<FunctionalCaseGenerateTaskRun> => {
      if (!candidate) return api.getFunctionalCaseGenerateTaskRun(runId)
      const value = await generationCandidatesApi.relations(candidate.requirementId, candidate.currentToken)
      return {
        runId: value.sourceAttemptId ?? value.candidateId,
        requirementId: candidate.requirementId,
        status: value.status === 'not_started' ? 'success' : value.status,
        currentStage: value.status === 'not_started' || value.status === 'success' ? 'completed' : 'relation_analysis',
        errorMessage: value.errorMessage,
        resultYaml: value.resultYaml,
        configJson: value.caseRelations ? { caseRelations: value.caseRelations } : {},
        reviewStatus: 'approved', importStatus: 'pending', importedTargets: [], importedAt: null,
      }
    },
    enabled: enabled && Boolean(runId),
    refetchInterval: query => poll && relationGenerating(query.state.data) ? (candidate ? 5000 : 1500) : false,
    refetchIntervalInBackground: true,
  })
}
