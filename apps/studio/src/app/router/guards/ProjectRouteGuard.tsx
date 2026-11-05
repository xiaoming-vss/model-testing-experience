import { useMemo, type ReactNode } from 'react'
import { Alert, Spin } from 'antd'
import { Navigate, useLocation } from 'react-router-dom'
import { ProjectAccessValueProvider } from '@/features/projects/components/ProjectAccessProvider'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import type { ProjectAccessValue } from '@/features/projects/hooks/projectAccessContext'
import { ProjectScope } from '@/features/projects/hooks/projectScope'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'

export function ProjectRouteGuard({ children }: { children: ReactNode }) {
  const projectId = useWorkbenchStore((state) => state.activeProjectId)
  const { can, loading, error, project } = useProjectAccess(projectId)
  const { pathname, search } = useLocation()
  const accessValue = useMemo<ProjectAccessValue | null>(
    () => projectId ? { projectId, project, can, loading, error } : null,
    [can, error, loading, project, projectId],
  )
  if (['/profile', '/change-password', '/admin/users', '/admin/ldap'].some((path) => pathname.startsWith(path)) || !projectId) return children
  if (loading) return <Spin aria-label="项目权限加载中" />
  if (error) return <Alert type="error" title="无法获取项目权限，请重新选择项目" />
  // Check the current project role before mounting requirement detail: developer
  // routes must not start requirement requests. Read-capable users still resolve
  // the canonical project inside the detail page.
  const isBugRoute = (pathname === '/testing' && new URLSearchParams(search).get('tab') === 'bugs')
    || (pathname.startsWith('/bugs/') && pathname !== '/bugs/new')
  if (!can('read') && !(isBugRoute && can('bug_read'))) {
    return can('bug_read') ? <Navigate to="/testing?tab=bugs" replace />
      : <Alert type="error" title="没有项目访问权限" />
  }
  /*
   * 放行后把这次已经取到的权限下发给页面：列表里的按钮不再各自订阅 projectAccess，
   * 同时提供 ProjectScope，解决没有 ProjectAccessScope 包裹的 /testing 等页面。
   */
  return accessValue ? (
    <ProjectAccessValueProvider value={accessValue}>
      <ProjectScope.Provider value={projectId}>{children}</ProjectScope.Provider>
    </ProjectAccessValueProvider>
  ) : children
}
