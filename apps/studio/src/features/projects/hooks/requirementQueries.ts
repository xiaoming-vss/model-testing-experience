import { api } from '@/services/api'

// 迭代 / 需求列表在 30s 内视为新鲜：需求响应内嵌每条需求的完整文档内容，
// 体积不小，而测试工作区的多个标签页和弹窗消费同一批数据。
// 集中在这里统一 key 与新鲜度，保证不同消费方命中同一份缓存而不是重复请求。
export const SPRINTS_STALE_TIME = 30_000
export const REQUIREMENTS_STALE_TIME = 30_000

export function requirementsQueryKey(sprintId: string | null | undefined) {
  return ['requirements', sprintId]
}

export function fetchSprintRequirements(sprintId: string) {
  return api.getRequirements(sprintId)
}
