import { describe, expect, it } from 'vitest'
import type { Project } from '../types'
import { hasProjectPermission, isBugOnlyProject, projectRoleLabel } from './useProjectAccess'

function project(overrides: Partial<Project> = {}): Project {
  return { projectId: 'p', name: '项目', ...overrides }
}

describe('服务端项目能力', () => {
  it('所有者和系统管理员标签不自动授予能力', () => {
    const value = project({ role: 'owner', isSuperAdmin: true, permissions: [] })
    expect(projectRoleLabel(value)).toBe('系统管理员')
    expect(hasProjectPermission(value, 'manage')).toBe(false)
    expect(hasProjectPermission(value, 'write')).toBe(false)
  })

  it('按能力选择 Bug 专用数据入口，不按角色名称推断', () => {
    expect(isBugOnlyProject(project({ role: 'member', permissions: ['bug_read'] }))).toBe(true)
    expect(isBugOnlyProject(project({ role: 'developer', permissions: ['read', 'bug_read'] }))).toBe(false)
    expect(isBugOnlyProject(undefined)).toBe(false)
    expect(isBugOnlyProject(project({ role: 'developer', permissions: [] }))).toBe(false)
  })

  it('保留旧服务端 read/write 兼容，开发成员不会被兼容逻辑扩大授权', () => {
    const old = project({ role: 'member', permissions: ['read', 'write'] })
    expect(hasProjectPermission(old, 'bug_read')).toBe(true)
    expect(hasProjectPermission(old, 'bug_handle')).toBe(true)
    expect(hasProjectPermission(old, 'project_read')).toBe(true)
    expect(hasProjectPermission(old, 'manage')).toBe(false)
    expect(hasProjectPermission(project({ role: 'developer', permissions: ['write'] }), 'bug_handle')).toBe(false)
  })
})
