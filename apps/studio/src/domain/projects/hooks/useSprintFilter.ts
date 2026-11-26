import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { listItems } from '@/shared/api/request'
import type { Sprint } from '@/domain/projects/types'
import { pickCreatedAt } from '@/utils/format'
import { SPRINTS_STALE_TIME } from './requirementQueries'

export const ALL_SPRINTS_VALUE = 'all'

export type SprintSource = {
  sprintId?: string
  name: string
  status?: Sprint['status']
  createdAt?: string
}

type SprintFilterController = {
  value?: string | null
  onChange: (sprintId: string | null | undefined) => void
}

type UseSprintFilterOptions<S extends SprintSource> = {
  /** 是否提供「全部迭代」。 */
  allowAll?: boolean
  /** 关闭项目迭代请求，用于已由其他接口带回选项的场景（Bug-only 成员）。 */
  enabled?: boolean
  /** 外部已取回的迭代选项；传入时不再请求 /sprints。 */
  sprints?: S[]
  /** 未选择时的默认范围：最新迭代，或全部迭代。 */
  defaultSelection?: 'latest' | 'all'
  /** 受控模式：页面把筛选范围放在 URL 时使用。 */
  controller?: SprintFilterController
}

function sprintIdOf(sprint: SprintSource) {
  return sprint.sprintId ?? ''
}

function byCreatedAtDesc(left: SprintSource, right: SprintSource) {
  const leftTime = Date.parse(pickCreatedAt(left) ?? '') || 0
  const rightTime = Date.parse(pickCreatedAt(right) ?? '') || 0
  return rightTime - leftTime
}

/** 默认跟随进行中的最新迭代；没有进行中的迭代时取最新创建的一个。 */
export function pickDefaultSprintId(sprints: SprintSource[]) {
  const running = sprints.filter((sprint) => sprint.status === 'running')
  const latest = [...(running.length ? running : sprints)].sort(byCreatedAtDesc)[0]
  return latest ? sprintIdOf(latest) : undefined
}

export function useSprintFilter<S extends SprintSource = Sprint>(
  projectId: string | undefined,
  options: UseSprintFilterOptions<S> = {},
) {
  const {
    allowAll = false,
    enabled = true,
    sprints: providedSprints,
    defaultSelection = 'latest',
    controller,
  } = options
  const [selection, setSelection] = useState<{ projectId?: string; value?: string | null }>({})

  const sprintsQuery = useQuery({
    queryKey: ['sprints', projectId],
    queryFn: () => api.getSprints(projectId!),
    enabled: Boolean(projectId) && enabled && !providedSprints,
    staleTime: SPRINTS_STALE_TIME,
  })

  const sprints = useMemo(
    () => (providedSprints ?? listItems(sprintsQuery.data)) as S[],
    [providedSprints, sprintsQuery.data],
  )

  const defaultSprintId = useMemo(() => {
    if (defaultSelection === 'all' && allowAll) return undefined
    return pickDefaultSprintId(sprints)
  }, [allowAll, defaultSelection, sprints])

  const selectedValue = controller
    ? controller.value
    : selection.projectId === projectId
      ? selection.value
      : undefined

  const selectedSprintId = useMemo(() => {
    if (selectedValue === null) return allowAll ? undefined : defaultSprintId
    if (selectedValue === undefined) return defaultSprintId
    if (sprintsQuery.isLoading) return selectedValue
    return sprints.some((sprint) => sprintIdOf(sprint) === selectedValue)
      ? selectedValue
      : defaultSprintId
  }, [allowAll, defaultSprintId, selectedValue, sprints, sprintsQuery.isLoading])

  const filterOptions = useMemo(
    () => [
      ...(allowAll ? [{ label: '全部迭代', value: ALL_SPRINTS_VALUE }] : []),
      ...sprints
        .map((sprint) => ({ label: sprint.name, value: sprintIdOf(sprint) }))
        .filter((option) => option.value),
    ],
    [allowAll, sprints],
  )

  function selectSprint(value?: string | null) {
    const next = !value || value === ALL_SPRINTS_VALUE ? null : value
    if (controller) {
      controller.onChange(allowAll ? next : next ?? undefined)
      return
    }
    setSelection({ projectId, value: next })
  }

  return {
    sprints,
    sprintsQuery,
    filterOptions,
    loading: sprintsQuery.isLoading,
    error: sprintsQuery.error,
    selectedSprintId,
    selectValue: selectedSprintId ?? (allowAll ? ALL_SPRINTS_VALUE : ''),
    selectSprint,
  }
}
