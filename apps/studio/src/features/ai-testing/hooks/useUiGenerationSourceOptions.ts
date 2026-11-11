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
