import type { RepositoryProfileRole } from '../types'

const roleMeta: Record<RepositoryProfileRole, { label: string; color: string }> = {
  frontend: { label: '前端', color: 'blue' },
  backend: { label: '后端', color: 'green' },
  fullstack: { label: '全栈', color: 'purple' },
  infra: { label: '基础设施', color: 'orange' },
  test: { label: '测试', color: 'cyan' },
  unknown: { label: '未知', color: 'default' },
}

export function repositoryRoleMeta(role: string) {
  return roleMeta[role as RepositoryProfileRole] ?? { label: role || '未知', color: 'default' }
}

export function formatProfileConfidence(value: number) {
  if (!Number.isFinite(value)) return '-'
  return `${Math.round(value * 100)}%`
}
