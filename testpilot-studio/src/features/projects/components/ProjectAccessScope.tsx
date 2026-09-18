import { getErrorMessage } from '@/utils/format'
import { Alert, Spin } from 'antd'
import { useProjectAccess } from '../hooks/useProjectAccess'
import type { ReactNode } from 'react'
import { ProjectScope } from '../hooks/projectScope'

export function ProjectAccessScope({ projectId, children, resourceError }: { projectId: string; children: ReactNode; resourceError?: unknown }) {
  const { can, loading, error } = useProjectAccess(projectId)
  if (resourceError) return <Alert type="error" showIcon title={getErrorMessage(resourceError)} />
  if (loading) return <Spin aria-label="加载项目权限" />
  if (error || !can('read')) return <Alert type="warning" showIcon title="无法访问此项目" description="项目可能已删除，或你的成员权限已变更。请返回项目总览选择可访问的项目。" />
  return <ProjectScope.Provider value={projectId}>{children}</ProjectScope.Provider>
}
