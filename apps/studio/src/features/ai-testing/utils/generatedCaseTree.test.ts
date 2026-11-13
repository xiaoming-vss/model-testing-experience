import { describe, expect, it } from 'vitest'
import { buildGeneratedCaseTree } from './generatedCaseTree'

describe('generated case tree', () => {
  const content = JSON.stringify({ cases: [
    { case_module: '模块:A', case_title: '相同标题', case_type: '功能测试' },
    { case_module: '模块:A', case_title: '相同标题', case_type: '异常测试' },
    { case_module: '模块B', case_title: '未匹配' },
  ] })
  it('groups cases by module and case type and keeps candidates without a case type', () => {
    const model = buildGeneratedCaseTree(content, '需求')
    expect(model.entries.map((entry) => entry.caseType)).toEqual(['功能测试', '异常测试', '未分类用例'])
    expect(new Set(model.entries.map((entry) => entry.key)).size).toBe(3)
    expect(model.tree.children).toHaveLength(2)
  })
  it('searches case types without changing candidate identity or raw details', () => {
    const model = buildGeneratedCaseTree(content, '需求', '异常')
    expect(model.visible).toHaveLength(1)
    expect(model.visible[0].key).toBe('模块:A:1')
    expect(model.tree.children[0].children[0].children[0].id).toBe('模块:A:1')
  })
})
