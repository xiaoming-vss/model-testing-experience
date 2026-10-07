import { useQuery } from '@tanstack/react-query'
import { projectsApi } from '../api/projects.api'
import { useWorkbenchStore } from '../store/workbench.store'
import type { Project, ProjectAction } from '../types'

export const roleLabels = { owner: '所有者', member: '普通成员', viewer: '只读成员', developer: '开发' }

export function hasProjectPermission(project: Project | undefined, action: ProjectAction) {
  if (project?.permissions?.includes(action)) return true
  // Older servers expose project-wide read/write capabilities for existing roles.
  if (project?.role !== 'developer') {
    const equivalent = action === 'bug_handle' ? 'write'
      : action === 'bug_read' || action === 'project_read' ? 'read' : action
    return Boolean(project?.permissions?.includes(equivalent))
  }
  return false
}

export function useProjectAccess(projectId?: string) {
  const activeId = useWorkbenchStore((s) => s.activeProjectId)
  const id = projectId ?? activeId
  const query = useQuery({
    queryKey: ['projectAccess', id],
    queryFn: () => projectsApi.getProject(id!),
    enabled: Boolean(id),
    staleTime: 30_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    retry: false,
  })
  const can = (action: ProjectAction) => !query.isError && hasProjectPermission(query.data, action)
  return { project: query.data, can, loading: query.isPending, error: query.error }
}
