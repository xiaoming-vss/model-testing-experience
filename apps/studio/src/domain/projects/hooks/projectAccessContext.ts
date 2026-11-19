import { createContext, useContext } from 'react'
import type { Project, ProjectAction } from '../types'

/*
 * 项目权限上下文：路由边界已经取过一次项目详情，叶子按钮直接消费，
 * 不再让每个实例各自挂一个 useProjectAccess observer。
 */
export type ProjectAccessValue = {
  projectId: string
  project?: Project
  can: (action: ProjectAction) => boolean
  loading: boolean
  error: unknown
}

export const ProjectAccessContext = createContext<ProjectAccessValue | null>(null)

/** 读取当前上下文；传入 projectId 时只有上下文项目一致才返回，便于调用方回退。 */
export function useProjectAccessContext(projectId?: string) {
  const value = useContext(ProjectAccessContext)
  if (!value) return null
  return projectId && value.projectId !== projectId ? null : value
}
