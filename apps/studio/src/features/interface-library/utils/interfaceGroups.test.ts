import { describe, expect, it } from 'vitest'
import {
  UNTAGGED_GROUP,
  firstTag,
  groupItemsByTag,
  groupLabel,
  replaceFirstTag,
  setFirstTag,
  withEmptyGroups,
} from './interfaceGroups'

describe('interface group helpers', () => {
  it('uses the first non-empty tag as the group', () => {
    expect(firstTag([' ', '订单', '查询'])).toBe('订单')
    expect(firstTag([])).toBe('')
    expect(firstTag(undefined)).toBe('')
    expect(groupLabel('  ')).toBe(UNTAGGED_GROUP)
  })

  it('replaces only the first tag and de-duplicates the result', () => {
    expect(replaceFirstTag(['订单', '查询', '订单'], '订单管理')).toEqual([
      '订单管理',
      '查询',
    ])
    expect(replaceFirstTag([], '订单管理')).toEqual(['订单管理'])
    expect(replaceFirstTag(['订单', '查询'], '')).toEqual([])
  })

  it('puts the target tag first without losing the remaining tags', () => {
    expect(setFirstTag(['订单', '查询'], '账户')).toEqual(['账户', '订单', '查询'])
    expect(setFirstTag(['订单'], '订单')).toEqual(['订单'])
    expect(setFirstTag(['订单'], '')).toEqual([])
  })

  it('sorts named groups alphabetically, untagged last, and interfaces by path then method', () => {
    const groups = groupItemsByTag([
      { path: '/orders/{id}', method: 'PUT', tags: ['Orders'] },
      { path: '/health', method: 'GET', tags: [] },
      { path: '/auth/login', method: 'POST', tags: ['Auth'] },
      { path: '/orders', method: 'GET', tags: ['Orders'] },
      { path: '/admin', method: 'GET', tags: ['Admin'] },
    ])

    expect(groups.map(group => group.tag)).toEqual([
      'Admin',
      'Auth',
      'Orders',
      UNTAGGED_GROUP,
    ])
    expect(groups[2]?.items.map(item => `${item.method} ${item.path}`)).toEqual([
      'GET /orders',
      'PUT /orders/{id}',
    ])
  })
})

describe('withEmptyGroups', () => {
  it('merges persisted empty groups, deduplicates derived groups and sorts them', () => {
    const groups = groupItemsByTag([
      { path: '/orders', method: 'GET', tags: ['Orders'] },
      { path: '/health', method: 'GET', tags: [] },
    ])

    const merged = withEmptyGroups(groups, ['Zeta', 'Orders', 'Alpha', '未分类', ' '])

    expect(merged.map(group => group.tag)).toEqual([
      'Alpha',
      'Orders',
      'Zeta',
      UNTAGGED_GROUP,
    ])
    expect(merged.find(group => group.tag === 'Zeta')?.items).toEqual([])
    expect(merged.find(group => group.tag === 'Orders')?.items).toHaveLength(1)
  })
})
