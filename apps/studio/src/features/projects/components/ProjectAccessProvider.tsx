import type { ReactNode } from 'react'
import { ProjectAccessContext, type ProjectAccessValue } from '../hooks/projectAccessContext'

/** 已经在外层取好权限时使用，避免路由守卫再挂一个 observer。 */
export function ProjectAccessValueProvider({ value, children }: { value: ProjectAccessValue; children: ReactNode }) {
  return <ProjectAccessContext.Provider value={value}>{children}</ProjectAccessContext.Provider>
}
