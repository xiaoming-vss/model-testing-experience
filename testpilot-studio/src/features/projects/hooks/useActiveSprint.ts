import { useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { normalizeSprintId, pickCreatedAt } from '@/utils/format'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'

export function useActiveSprint() {
  const { activeProjectId, projectsQuery } = useActiveProject()
  const storedSprintId = useWorkbenchStore((state) => state.activeSprintId)
  const storedSprintProjectId = useWorkbenchStore((state) => state.activeSprintProjectId)
  const setActiveSprintId = useWorkbenchStore((state) => state.setActiveSprintId)

  const sprintsQuery = useQuery({
    queryKey: ['sprints', activeProjectId],
    queryFn: () => api.getSprints(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })

  const sprints = useMemo(() => sprintsQuery.data ?? [], [sprintsQuery.data])

  const latestSprintId = useMemo(() => {
    const latest = [...sprints].sort((left, right) => {
      const leftTime = Date.parse(pickCreatedAt(left) ?? '') || 0
      const rightTime = Date.parse(pickCreatedAt(right) ?? '') || 0
      return rightTime - leftTime
    })[0]
    return latest ? normalizeSprintId(latest) : undefined
  }, [sprints])

  useEffect(() => {
    if (!activeProjectId || !sprintsQuery.isSuccess || !latestSprintId) return
    const state = useWorkbenchStore.getState()
    if (state.activeProjectId !== activeProjectId) return
    if (state.activeSprintProjectId === activeProjectId && state.activeSprintId !== undefined) return
    setActiveSprintId(latestSprintId)
  }, [activeProjectId, latestSprintId, setActiveSprintId, sprintsQuery.isSuccess, storedSprintId, storedSprintProjectId])

  const activeSprintId = useMemo(() => {
    if (!activeProjectId) return undefined
    if (storedSprintProjectId !== activeProjectId || storedSprintId === undefined) return latestSprintId
    if (!storedSprintId) return undefined
    if (sprintsQuery.isLoading) return storedSprintId
    return sprints.some((sprint) => normalizeSprintId(sprint) === storedSprintId) ? storedSprintId : undefined
  }, [activeProjectId, latestSprintId, sprints, sprintsQuery.isLoading, storedSprintId, storedSprintProjectId])

  const sprintSelectorOptions = useMemo(
    () => [
      { label: '全部迭代', value: 'all' },
      ...sprints.map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) })),
    ],
    [sprints],
  )

  function selectSprint(value?: string | null) {
    setActiveSprintId(!value || value === 'all' ? null : value)
  }

  return {
    activeProjectId,
    activeSprintId,
    projectsQuery,
    sprints,
    sprintsQuery,
    selectSprint,
    setActiveSprintId,
    sprintSelectorOptions,
  }
}
