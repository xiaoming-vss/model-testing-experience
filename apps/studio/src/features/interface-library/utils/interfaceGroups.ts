import type { ApiInterfaceListItem } from '../types'

export const UNTAGGED_GROUP = '未分类'

export type InterfaceGroup<T extends { tags?: string[] } = ApiInterfaceListItem> = {
  tag: string
  items: T[]
}

export function firstTag(tags?: string[] | null): string {
  for (const raw of tags ?? []) {
    const tag = String(raw ?? '').trim()
    if (tag) return tag
  }
  return ''
}

export function groupLabel(tag?: string | null): string {
  return String(tag ?? '').trim() || UNTAGGED_GROUP
}

function normalizedTags(tags?: string[] | null): string[] {
  const normalized: string[] = []
  for (const raw of tags ?? []) {
    const tag = String(raw ?? '').trim()
    if (!tag || normalized.includes(tag)) continue
    normalized.push(tag)
  }
  return normalized
}

export function replaceFirstTag(tags: string[] | null | undefined, newTag: string): string[] {
  const values = normalizedTags(tags)
  const target = String(newTag ?? '').trim()
  if (!target) return []
  return normalizedTags([target, ...values.slice(1)])
}

export function setFirstTag(tags: string[] | null | undefined, target: string): string[] {
  const text = String(target ?? '').trim()
  if (!text) return []
  return normalizedTags([text, ...normalizedTags(tags)])
}

export function groupItemsByTag<T extends { tags?: string[]; path: string; method: string }>(
  items: T[],
): InterfaceGroup<T>[] {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const tag = firstTag(item.tags) || UNTAGGED_GROUP
    const group = groups.get(tag) ?? []
    group.push(item)
    groups.set(tag, group)
  }
  return [...groups.entries()]
    .sort(([left], [right]) => compareGroupTags(left, right))
    .map(([tag, groupItems]) => ({
      tag,
      items: [...groupItems].sort(
        (left, right) =>
          left.path.localeCompare(right.path) || left.method.localeCompare(right.method),
      ),
    }))
}

/** Merge persisted manual groups (possibly empty) with groups derived from tags. */
export function withEmptyGroups<T extends { tags?: string[]; path: string; method: string }>(
  groups: InterfaceGroup<T>[],
  groupNames?: string[] | null,
): InterfaceGroup<T>[] {
  const seen = new Set(groups.map(group => group.tag))
  const merged = [...groups]
  for (const raw of groupNames ?? []) {
    const tag = String(raw ?? '').trim()
    if (!tag || tag === UNTAGGED_GROUP || seen.has(tag)) continue
    seen.add(tag)
    merged.push({ tag, items: [] })
  }
  return merged.sort((left, right) => compareGroupTags(left.tag, right.tag))
}

function compareGroupTags(left: string, right: string) {
  if (left === UNTAGGED_GROUP) return right === UNTAGGED_GROUP ? 0 : 1
  if (right === UNTAGGED_GROUP) return -1
  return left.localeCompare(right, 'zh-CN')
}
