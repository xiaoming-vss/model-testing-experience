import { listItems, listTotal } from '@/shared/api/request'
import { api } from '@/services/api'

// 迭代 / 需求列表在 30s 内视为新鲜：列表只返回需求元数据，正文走详情接口；
// 测试工作区的多个标签页和弹窗消费同一批数据。
// 集中在这里统一 key 与新鲜度，保证不同消费方命中同一份缓存而不是重复请求。
export const SPRINTS_STALE_TIME = 30_000
export const REQUIREMENTS_STALE_TIME = 30_000

const SPRINT_REQUIREMENTS_PAGE_SIZE = 100

export function requirementsQueryKey(sprintId: string | null | undefined) {
  return ['requirements', sprintId]
}

export async function fetchSprintRequirements(sprintId: string) {
  const firstPage = await api.getRequirements(sprintId, {
    page: 1,
    pageSize: SPRINT_REQUIREMENTS_PAGE_SIZE,
  })
  const items = [...listItems(firstPage)]
  const total = listTotal(firstPage)
  for (let page = 2; items.length < total; page += 1) {
    const nextPage = await api.getRequirements(sprintId, {
      page,
      pageSize: SPRINT_REQUIREMENTS_PAGE_SIZE,
    })
    const nextItems = listItems(nextPage)
    if (nextItems.length === 0) break
    items.push(...nextItems)
  }
  return Object.assign(items, { items, total })
}
