import type { Project, ProjectAction } from '../types'

export const roleLabels = { owner: '所有者', member: '普通成员', viewer: '只读成员', developer: '开发' }

export function projectRoleLabel(project?: Project) {
  if (!project) return ''
  if (project.isSuperAdmin) return '系统管理员'
  return project.role ? roleLabels[project.role] : ''
}

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

export function isBugOnlyProject(project?: Project) {
  return hasProjectPermission(project, 'bug_read') && !hasProjectPermission(project, 'read')
}
