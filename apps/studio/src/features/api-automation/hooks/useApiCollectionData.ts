import {
  DRAFT_CASE_ID
} from '@/features/api-automation/config/collectionConfig'
import {
  EMPTY_API_ENVIRONMENTS
} from '@/features/api-automation/utils/apiCaseEditor'
import {
  api
} from '@/services/api'
import {
  normalizeEnvironmentId
} from '@/utils/format'
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

type Options = {
  collectionId: string
  selectedEnvironmentId: string | undefined
  selectedCaseId: string
}

export function useApiCollectionData({ collectionId, selectedEnvironmentId, selectedCaseId }: Options) {
  const collectionQuery = useQuery({
    queryKey: ['apiCollection', collectionId],
    queryFn: () => api.getApiCollection(collectionId),
    enabled: Boolean(collectionId),
  })

  const casesQuery = useQuery({
    queryKey: ['apiCases', collectionId],
    queryFn: () => api.getApiCases(collectionId),
    enabled: Boolean(collectionId),
  })

  const requirementId = collectionQuery.data?.requirementId ?? collectionQuery.data?.requirement_id

  const requirementQuery = useQuery({
    queryKey: ['requirement', requirementId],
    queryFn: () => api.getRequirement(requirementId!),
    enabled: Boolean(requirementId),
  })

  const sprintId = requirementQuery.data?.sprintId ?? requirementQuery.data?.sprint_id

  const sprintQuery = useQuery({
    queryKey: ['sprint', sprintId],
    queryFn: () => api.getSprint(sprintId!),
    enabled: Boolean(sprintId),
  })

  const projectId = sprintQuery.data?.projectId ?? sprintQuery.data?.project_id

  const environmentsQuery = useQuery({
    queryKey: ['apiEnvironments', projectId],
    queryFn: () => api.getApiEnvironments(projectId!),
    enabled: Boolean(projectId),
  })

  const environments = environmentsQuery.data ?? EMPTY_API_ENVIRONMENTS

  const selectedEnvironment =
    environments.find((environment) => normalizeEnvironmentId(environment) === selectedEnvironmentId) ??
    environments.find((environment) => environment.isDefault) ??
    environments[0]

  const resolvedEnvironmentId = selectedEnvironment ? normalizeEnvironmentId(selectedEnvironment) : undefined

  const environmentVarsQuery = useQuery({
    queryKey: ['apiEnvironmentVars', resolvedEnvironmentId],
    queryFn: () => api.getApiEnvironmentVars(resolvedEnvironmentId!),
    enabled: Boolean(resolvedEnvironmentId),
  })

  const environmentVars = useMemo(() => environmentVarsQuery.data ?? [], [environmentVarsQuery.data])

  const activeCaseId = selectedCaseId && selectedCaseId !== DRAFT_CASE_ID ? selectedCaseId : ''

  const selectedCaseDetailQuery = useQuery({
    queryKey: ['apiCase', activeCaseId],
    queryFn: () => api.getApiCase(activeCaseId),
    enabled: Boolean(activeCaseId),
    refetchOnWindowFocus: false,
  })
  return {
    collectionQuery,
    casesQuery,
    requirementId,
    requirementQuery,
    sprintId,
    sprintQuery,
    projectId,
    environmentsQuery,
    environments,
    selectedEnvironment,
    resolvedEnvironmentId,
    environmentVarsQuery,
    environmentVars,
    activeCaseId,
    selectedCaseDetailQuery,
  }
}
