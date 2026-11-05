import { useMemo, type ReactNode } from 'react'
import { useProjectAccess } from '../hooks/useProjectAccess'
import { ProjectAccessContext, type ProjectAccessValue } from '../hooks/projectAccessContext'

/** 需要独立取权限的边界使用；同一页面只应有一个实例。 */
export function ProjectAccessProvider({ projectId, children }: { projectId: string; children: ReactNode }) {
  const { project, can, loading, error } = useProjectAccess(projectId)
  const value = useMemo<ProjectAccessValue>(
    () => ({ projectId, project, can, loading, error }),
    [can, error, loading, project, projectId],
  )
  return <ProjectAccessContext.Provider value={value}>{children}</ProjectAccessContext.Provider>
}

/** 已经在外层取好权限时使用，避免路由守卫再挂一个 observer。 */
export function ProjectAccessValueProvider({ value, children }: { value: ProjectAccessValue; children: ReactNode }) {
  return <ProjectAccessContext.Provider value={value}>{children}</ProjectAccessContext.Provider>
}
