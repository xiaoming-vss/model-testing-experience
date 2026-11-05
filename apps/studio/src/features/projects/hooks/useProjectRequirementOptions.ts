import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api } from '@/services/api'
import type { RequirementOption } from '@/features/requirements/types'
import { normalizeRequirementId } from '@/utils/format'
import { REQUIREMENTS_STALE_TIME } from './requirementQueries'

/**
 * 项目级需求下拉数据：一次返回全部迭代的摘要（id/名称/迭代），不包含需求正文。
 * key 放在 requirementsPool 前缀下，需求/迭代/成员变更时的现有失效逻辑可以直接覆盖。
 */
export function useProjectRequirementOptions({
  activeProjectId,
  enabled = true,
}: {
  activeProjectId?: string
  enabled?: boolean
}) {
  const allRequirementsQuery = useQuery({
    queryKey: ['requirementsPool', activeProjectId, 'options'],
    queryFn: () => api.getProjectRequirementOptions(activeProjectId!),
    enabled: Boolean(activeProjectId) && enabled,
    staleTime: REQUIREMENTS_STALE_TIME,
  })

  const allRequirements = useMemo(
    () => (allRequirementsQuery.data ?? []) as RequirementOption[],
    [allRequirementsQuery.data],
  )
  const requirementNameMap = useMemo(
    () => new Map(allRequirements.map((requirement) => [normalizeRequirementId(requirement), requirement.name])),
    [allRequirements],
  )
  const requirementSprintMap = useMemo(
    () => new Map(allRequirements.map((requirement) => [normalizeRequirementId(requirement), requirement.sprintId])),
    [allRequirements],
  )
  // 摘要本身带 sprintName；引用需求的页面只需要“需求 → 迭代名称”，不需要再拉迭代列表。
  const sprintNameMap = useMemo(
    () => new Map(allRequirements.map((requirement) => [requirement.sprintId, requirement.sprintName])),
    [allRequirements],
  )

  return { allRequirements, allRequirementsQuery, requirementNameMap, requirementSprintMap, sprintNameMap }
}
