import type { ListResponse } from '@/shared/api/request'

export function listResponse<T>(items: T[], total = items.length): ListResponse<T> {
  return Object.assign([...items], { items, total })
}
