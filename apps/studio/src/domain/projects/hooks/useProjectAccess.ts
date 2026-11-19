import { useQuery } from '@tanstack/react-query'
import { useCallback } from 'react'
import { usePaneActive } from '@/shared/ui/paneActivity'
import { projectsApi } from '../api/projects.api'
import { hasProjectPermission } from './projectPermissions'
import { useWorkbenchStore } from '../store/workbench.store'
import type { ProjectAction } from '../types'

// 纯权限判断集中在 projectPermissions，避免被 useProjectAccess 的测试 mock 连带影响。
export { hasProjectPermission, isBugOnlyProject, projectRoleLabel, roleLabels } from './projectPermissions'

export function useProjectAccess(projectId?: string) {
  const activeId = useWorkbenchStore((s) => s.activeProjectId)
  const id = projectId ?? activeId
  // 隐藏的标签页保留挂载，但不再按时刷新权限；切回来时按下一个周期继续。
  const paneActive = usePaneActive()
  const query = useQuery({
    queryKey: ['projectAccess', id],
    queryFn: () => projectsApi.getProject(id!),
    enabled: Boolean(id),
    staleTime: 30_000,
    refetchInterval: paneActive ? 30_000 : false,
    refetchOnWindowFocus: paneActive,
    retry: false,
  })
  const can = useCallback(
    (action: ProjectAction) => !query.isError && hasProjectPermission(query.data, action),
    [query.data, query.isError],
  )
  return { project: query.data, can, loading: query.isPending, error: query.error }
}
