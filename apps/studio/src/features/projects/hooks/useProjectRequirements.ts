import { useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type Requirement, type Sprint } from '@/services/api'
import { normalizeRequirementId, normalizeSprintId } from '@/utils/format'
import { REQUIREMENTS_STALE_TIME, requirementsQueryKey, fetchSprintRequirements } from './requirementQueries'

export function useProjectRequirements({
  activeProjectId,
  enabled = true,
  sprints,
}: {
  activeProjectId?: string
  enabled?: boolean
  sprints: Sprint[]
}) {
  const queryClient = useQueryClient()
  const sprintIds = useMemo(() => sprints.map(normalizeSprintId), [sprints])

  const allRequirementsQuery = useQuery({
    queryKey: ['requirementsPool', activeProjectId, sprintIds.join(',')],
    queryFn: async () => {
      if (sprintIds.length === 0) return []
      // 逐迭代取需求，但走统一的 ['requirements', sprintId] 缓存：
      // 当前迭代的那份往往已被迭代/需求选择器请求过，这里直接命中，不再重复拉全量文档。
      const requirementGroups = await Promise.all(sprintIds.map((sprintId) =>
        queryClient.ensureQueryData({
          queryKey: requirementsQueryKey(sprintId),
          queryFn: () => fetchSprintRequirements(sprintId),
          staleTime: REQUIREMENTS_STALE_TIME,
        }),
      ))
      return requirementGroups.flat()
    },
    enabled: Boolean(activeProjectId) && enabled,
    staleTime: REQUIREMENTS_STALE_TIME,
  })

  const allRequirements = useMemo(() => allRequirementsQuery.data ?? [], [allRequirementsQuery.data])
  const sprintNameMap = useMemo(
    () => new Map(sprints.map((sprint) => [normalizeSprintId(sprint), sprint.name])),
    [sprints],
  )
  const requirementNameMap = useMemo(
    () => new Map(allRequirements.map((requirement) => [normalizeRequirementId(requirement), requirement.name])),
    [allRequirements],
  )
  const requirementSprintMap = useMemo(
    () =>
      new Map(
        allRequirements.map((requirement: Requirement) => [
          normalizeRequirementId(requirement),
          requirement.sprintId ?? requirement.sprint_id,
        ]),
      ),
    [allRequirements],
  )

  return {
    allRequirements,
    allRequirementsQuery,
    requirementNameMap,
    requirementSprintMap,
    sprintNameMap,
  }
}
