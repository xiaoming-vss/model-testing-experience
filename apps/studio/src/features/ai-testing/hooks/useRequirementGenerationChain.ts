import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'
import { RUN_HISTORY_POLL_INTERVAL } from '@/domain/runs/polling'
import { generationChainApi, type GenerationChainKind } from '../api/generationChain.api'
import { usePersonalLlmChoice } from './usePersonalLlmChoice'

export type SelectedChainStage = { kind: GenerationChainKind; stage: string }

const OVERVIEW_KEY = (requirementId: string) => ['generationChain', requirementId, 'overview'] as const

/** Resolve a stage key to its server-owned display name across every chain. */
export function useGenerationStageLabels(requirementId: string, enabled: boolean) {
  const overview = useQuery({
    queryKey: OVERVIEW_KEY(requirementId),
    queryFn: () => generationChainApi.overview(requirementId),
    enabled,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })
  return useMemo(() => {
    const labels: Record<string, string> = {}
    for (const chain of overview.data?.chains ?? []) for (const item of chain.stages) labels[item.stage] = item.label
    return (stage: string) => labels[stage] ?? stage
  }, [overview.data])
}

/** Read the candidate-chain overview and manage the selected stage. */
export function useRequirementGenerationChain({ requirementId, projectId, enabled }: {
  requirementId: string
  projectId: string
  enabled: boolean
}) {
  const client = useQueryClient()
  const [selected, setSelected] = useState<SelectedChainStage>()
  const personalLlm = usePersonalLlmChoice(projectId)
  const overview = useQuery({
    queryKey: OVERVIEW_KEY(requirementId),
    queryFn: () => generationChainApi.overview(requirementId),
    enabled,
    refetchInterval: query => (query.state.data?.chains ?? []).some(chain => chain.active || chain.busy)
      ? 5_000 : RUN_HISTORY_POLL_INTERVAL,
  })
  const detail = useQuery({
    queryKey: ['generationChain', requirementId, selected?.kind, 'detail'],
    queryFn: () => generationChainApi.chain(requirementId, selected!.kind),
    enabled: enabled && Boolean(selected),
    refetchInterval: query => query.state.data?.active || query.state.data?.busy ? 5_000 : RUN_HISTORY_POLL_INTERVAL,
  })
  const chain = detail.data
  const stage = useMemo(() => chain?.stages.find(item => item.stage === selected?.stage), [chain, selected?.stage])
  const refresh = useCallback(() => {
    void client.invalidateQueries({ queryKey: ['generationChain', requirementId] })
  }, [client, requirementId])
  const openStage = useCallback((kind: GenerationChainKind, stageName: string) => {
    setSelected({ kind, stage: stageName })
  }, [])
  const clearStage = useCallback(() => setSelected(undefined), [])
  return { overview, detail, chain, stage, selected, refresh, openStage, clearStage, personalLlm }
}

export type GenerationChainWorkspace = ReturnType<typeof useRequirementGenerationChain>
