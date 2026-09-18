import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type Requirement, type Sprint } from '@/services/api'
import { normalizeRequirementId, normalizeSprintId } from '@/utils/format'

export function useProjectRequirements({
  activeProjectId,
  enabled = true,
  sprints,
}: {
  activeProjectId?: string
  enabled?: boolean
  sprints: Sprint[]
}) {
  const sprintIds = useMemo(() => sprints.map(normalizeSprintId), [sprints])

  const allRequirementsQuery = useQuery({
    queryKey: ['requirementsPool', activeProjectId, sprintIds.join(',')],
    queryFn: async () => {
      if (sprintIds.length === 0) return []
      const requirementGroups = await Promise.all(sprintIds.map((sprintId) => api.getRequirements(sprintId)))
      return requirementGroups.flat()
    },
    enabled: Boolean(activeProjectId) && enabled,
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
