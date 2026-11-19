import { getErrorMessage } from '@/utils/format'
import { Alert, Spin } from 'antd'
import { useMemo, type ReactNode } from 'react'
import { useProjectAccess } from '../hooks/useProjectAccess'
import { useProjectAccessContext, type ProjectAccessValue } from '../hooks/projectAccessContext'
import { ProjectScope } from '../hooks/projectScope'
import { ProjectAccessValueProvider } from './ProjectAccessProvider'

function ProjectAccessGate({ access, projectId, children, resourceError }: { access: ProjectAccessValue; projectId: string; children: ReactNode; resourceError?: unknown }) {
  if (resourceError) return <Alert type="error" showIcon title={getErrorMessage(resourceError)} />
  if (access.loading) return <Spin aria-label="加载项目权限" />
  if (access.error || !access.can('read')) return <Alert type="warning" showIcon title="无法访问此项目" description="项目可能已删除，或你的成员权限已变更。请返回项目总览选择可访问的项目。" />
  return (
    <ProjectAccessValueProvider value={access}>
      <ProjectScope.Provider value={projectId}>{children}</ProjectScope.Provider>
    </ProjectAccessValueProvider>
  )
}

function ProjectAccessScopeWithQuery({ projectId, children, resourceError }: { projectId: string; children: ReactNode; resourceError?: unknown }) {
  const { project, can, loading, error } = useProjectAccess(projectId)
  const value = useMemo<ProjectAccessValue>(
    () => ({ projectId, project, can, loading, error }),
    [can, error, loading, project, projectId],
  )
  return <ProjectAccessGate access={value} projectId={projectId} resourceError={resourceError}>{children}</ProjectAccessGate>
}

export function ProjectAccessScope({ projectId, children, resourceError }: { projectId: string; children: ReactNode; resourceError?: unknown }) {
  const outer = useProjectAccessContext()
  // 外层守卫已经取过同一个项目时直接复用，避免详情页再挂一个权限 observer。
  if (outer?.projectId === projectId) {
    return <ProjectAccessGate access={outer} projectId={projectId} resourceError={resourceError}>{children}</ProjectAccessGate>
  }
  return <ProjectAccessScopeWithQuery projectId={projectId} resourceError={resourceError}>{children}</ProjectAccessScopeWithQuery>
}
