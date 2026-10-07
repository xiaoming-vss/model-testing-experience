import { useQuery } from '@tanstack/react-query'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { bugsApi } from '../api/bugs.api'

/** Bug-only members receive labels, never full sprint or project-member resources. */
export function useBugScope(projectId: string | undefined, enabled: boolean) {
  const storedSprintId = useWorkbenchStore((state) => state.activeSprintId)
  const storedProjectId = useWorkbenchStore((state) => state.activeSprintProjectId)
  const setActiveSprintId = useWorkbenchStore((state) => state.setActiveSprintId)
  const optionsQuery = useQuery({
    queryKey: ['bugOptions', projectId],
    queryFn: () => bugsApi.getBugOptions(projectId!),
    enabled: Boolean(projectId) && enabled,
    refetchInterval: enabled ? 30_000 : false,
  })
  const sprints = optionsQuery.data?.sprints ?? []
  const activeSprintId = storedProjectId === projectId && sprints.some((sprint) => sprint.sprintId === storedSprintId)
    ? storedSprintId ?? undefined : undefined
  return {
    optionsQuery, members: optionsQuery.data?.members ?? [], sprints, activeSprintId,
    sprintsQuery: optionsQuery,
    sprintSelectorOptions: [{ label: '全部迭代', value: 'all' }, ...sprints.map((sprint) => ({ label: sprint.name, value: sprint.sprintId }))],
    selectSprint: (value?: string | null) => setActiveSprintId(!value || value === 'all' ? null : value),
  }
}
