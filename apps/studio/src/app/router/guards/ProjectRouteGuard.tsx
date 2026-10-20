import type { ReactNode } from 'react'
import { Alert, Spin } from 'antd'
import { Navigate, useLocation } from 'react-router-dom'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'

export function ProjectRouteGuard({ children }: { children: ReactNode }) {
  const projectId = useWorkbenchStore((state) => state.activeProjectId)
  const { can, loading, error } = useProjectAccess(projectId)
  const { pathname, search } = useLocation()
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
  return children
}
