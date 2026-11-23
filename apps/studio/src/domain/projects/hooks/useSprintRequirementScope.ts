import { useMemo, useState } from 'react'
import type { RequirementOption } from '@/domain/requirements/types'
import { useQuery } from '@tanstack/react-query'
import { api, type Requirement } from '@/services/api'
import { normalizeRequirementId, normalizeSprintId, pickCreatedAt } from '@/utils/format'
import { REQUIREMENTS_STALE_TIME, SPRINTS_STALE_TIME, requirementsQueryKey, fetchSprintRequirements } from './requirementQueries'
import { pickDefaultSprintId } from './useSprintFilter'

type ProjectScopedSelection = {
  projectId?: string
  sprintId?: string
  value?: string | null
}

const UNSET_SELECTION = Symbol('unset-selection')
type ScopeSelectionValue = string | null | typeof UNSET_SELECTION

type UseSprintRequirementScopeOptions = {
  activeProjectId?: string
  includeAllSprintOption?: boolean
  includeAllRequirementOption?: boolean
  /** 未选需求时的默认范围；用例库默认展示当前迭代的全部需求。 */
  defaultRequirementSelection?: 'latest' | 'all'
  /** 已由 useProjectRequirementOptions 取回的项目级摘要；传入时不再请求 sprint 全量列表。 */
  requirementOptions?: RequirementOption[]
  requirementOptionsLoading?: boolean
}

function pickLatestItem<T>(items: T[], getTime: (item: T) => string | undefined) {
  return [...items].sort((left, right) => {
    const leftTime = new Date(getTime(left) ?? 0).getTime()
    const rightTime = new Date(getTime(right) ?? 0).getTime()
    return rightTime - leftTime
  })[0]
}

export function useSprintRequirementScope(options: UseSprintRequirementScopeOptions) {
  const {
    activeProjectId,
    includeAllSprintOption = false,
    includeAllRequirementOption = false,
    defaultRequirementSelection = 'latest',
    requirementOptions,
    requirementOptionsLoading = false,
  } = options
  const [sprintSelection, setSprintSelection] = useState<ProjectScopedSelection>({})
  const [requirementSelection, setRequirementSelection] = useState<ProjectScopedSelection>({})

  const sprintsQuery = useQuery({
    queryKey: ['sprints', activeProjectId],
    queryFn: () => api.getSprints(activeProjectId!),
    enabled: Boolean(activeProjectId),
    staleTime: SPRINTS_STALE_TIME,
  })

  const sprints = useMemo(() => sprintsQuery.data ?? [], [sprintsQuery.data])
  const defaultSprintId = useMemo(() => pickDefaultSprintId(sprints), [sprints])
  const resolvedSelectedSprintId = sprintSelection.projectId === activeProjectId
    ? sprintSelection.value ?? undefined
    : defaultSprintId

  const requirementsQuery = useQuery({
    queryKey: requirementsQueryKey(resolvedSelectedSprintId),
    queryFn: () => fetchSprintRequirements(resolvedSelectedSprintId!),
    // 有项目级摘要时按 sprint 本地过滤，避免下拉再拉一次含正文的 sprint 列表。
    enabled: Boolean(resolvedSelectedSprintId) && !requirementOptions,
    staleTime: REQUIREMENTS_STALE_TIME,
  })

  const requirements = useMemo(
    () => requirementOptions
      ? (resolvedSelectedSprintId
        ? requirementOptions.filter((requirement) => requirement.sprintId === resolvedSelectedSprintId)
        : requirementOptions)
      : requirementsQuery.data ?? [],
    [requirementOptions, requirementsQuery.data, resolvedSelectedSprintId],
  )
  const requirementsLoading = requirementOptions ? requirementOptionsLoading : requirementsQuery.isLoading
  const latestRequirement = useMemo(() => pickLatestItem<Requirement>(requirements, pickCreatedAt), [requirements])
  const currentRequirementSelection: ScopeSelectionValue =
    requirementSelection.projectId === activeProjectId && requirementSelection.sprintId === resolvedSelectedSprintId ? (requirementSelection.value ?? null) : UNSET_SELECTION
  const resolvedSelectedRequirementId =
    currentRequirementSelection === UNSET_SELECTION
      ? defaultRequirementSelection === 'all' && includeAllRequirementOption
        ? undefined
        : latestRequirement
          ? normalizeRequirementId(latestRequirement)
          : undefined
      : currentRequirementSelection ?? undefined

  const sprintFilterOptions = useMemo(
    () => [
      ...(includeAllSprintOption ? [{ label: '全部迭代', value: 'all' }] : []),
      ...sprints.map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) }))
        .filter((option) => option.value),
    ],
    [includeAllSprintOption, sprints],
  )

  const requirementFilterOptions = useMemo(
    () => [
      ...(includeAllRequirementOption ? [{ label: '全部需求', value: 'all' }] : []),
      ...requirements.map((requirement) => ({ label: requirement.name, value: normalizeRequirementId(requirement) })),
    ],
    [includeAllRequirementOption, requirements],
  )

  function selectSprint(value?: string | null) {
    const next = !value || value === 'all' ? null : value
    setSprintSelection({
      projectId: activeProjectId,
      value: next,
    })
    setRequirementSelection({
      sprintId: next ?? undefined,
      projectId: activeProjectId,
      value: null,
    })
  }

  function selectRequirement(value?: string | null) {
    setRequirementSelection({
      sprintId: resolvedSelectedSprintId,
      projectId: activeProjectId,
      value: value ?? null,
    })
  }

  return {
    currentRequirementSelection,
    requirementFilterOptions,
    requirements,
    requirementsLoading,
    requirementsQuery,
    resolvedSelectedRequirementId,
    resolvedSelectedSprintId,
    selectRequirement,
    selectSprint,
    sprintFilterOptions,
    sprints,
    sprintsQuery,
  }
}
