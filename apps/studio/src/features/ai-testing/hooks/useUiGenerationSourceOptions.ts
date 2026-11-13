import { useQuery } from '@tanstack/react-query'
import { generationChainApi } from '../api/generationChain.api'

/** Requirement-scoped repository profile candidates accepted by UI generation. */
export function useUiGenerationSourceOptions(requirementId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['generationChain', requirementId, 'ui', 'sourceOptions'],
    queryFn: () => generationChainApi.uiSourceOptions(requirementId),
    enabled: enabled && Boolean(requirementId),
    retry: false,
  })
}

/** The overview omits the frozen source inputs. Read them when the UI group is open. */
export function useUiGenerationSourceSnapshot(requirementId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['generationChain', requirementId, 'ui', 'detail'],
    queryFn: () => generationChainApi.chain(requirementId, 'ui'),
    enabled: enabled && Boolean(requirementId),
    select: chain => chain.sourceInputs,
  })
}
