import { formatTime } from '@/utils/format'

export type InvalidatableCase = {
  invalidatedAt?: string | null
}

export type CaseInvalidationFilter = 'all' | 'valid' | 'invalid'

export function invalidatedFilterParam(filter: CaseInvalidationFilter): boolean | undefined {
  if (filter === 'valid') return false
  if (filter === 'invalid') return true
  return undefined
}

export function isCaseInvalidated(item: InvalidatableCase): boolean {
  return Boolean(item.invalidatedAt)
}

export function invalidatedAtText(value?: string | null): string {
  return value ? formatTime(value) : ''
}
