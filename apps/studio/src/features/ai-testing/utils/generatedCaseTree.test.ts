import { describe, expect, it } from 'vitest'
import { buildGeneratedCaseTree } from './generatedCaseTree'

describe('generated case tree', () => {
  const content = JSON.stringify({ cases: [
    { case_module: '模块:A', case_title: '相同标题', precondition: ['甲'] },
    { case_module: '模块:A', case_title: '相同标题', test_model: '边界场景' },
    { case_module: '模块B', case_title: '未匹配' },
  ] })
  const points = JSON.stringify({ categories: [{ model: '模块:A', data: [{ test_model: '功能场景', test_points: ['相同标题'] }] }] })
  it('uses upstream scenarios, prefers explicit scenes, and retains unmatched candidates', () => {
    const model = buildGeneratedCaseTree(content, points, '需求')
    expect(model.entries.map((entry) => entry.scene)).toEqual(['功能场景', '边界场景', '未分组场景'])
    expect(new Set(model.entries.map((entry) => entry.key)).size).toBe(3)
    expect(model.tree.children).toHaveLength(2)
  })
  it('searches scenes without changing candidate identity or raw details', () => {
    const model = buildGeneratedCaseTree(content, points, '需求', '边界')
    expect(model.visible).toHaveLength(1)
    expect(model.visible[0].key).toBe('模块:A:1')
    expect(model.tree.children[0].children[0].children[0].id).toBe('模块:A:1')
  })
})
