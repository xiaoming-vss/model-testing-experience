import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { FunctionalCaseGenerateTaskRun } from '../types'

export function relationGenerating(run?: FunctionalCaseGenerateTaskRun) {
  return run?.currentStage === 'relation_analysis' && ['pending', 'claimed', 'running'].includes(run.status ?? '')
}

export function relationFailed(run?: FunctionalCaseGenerateTaskRun) {
  return run?.currentStage === 'relation_analysis' && ['failed', 'error', 'canceled'].includes(run.status ?? '')
}

export function useFunctionalCaseRelationsRun(runId: string, enabled = true, poll = true) {
  return useQuery({
    queryKey: ['functionalCaseGenerateTaskRun', runId],
    queryFn: () => api.getFunctionalCaseGenerateTaskRun(runId),
    enabled: enabled && Boolean(runId),
    refetchInterval: query => poll && relationGenerating(query.state.data) ? 1500 : false,
    refetchIntervalInBackground: true,
  })
}
