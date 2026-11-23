import { describe, expect, it } from 'vitest'
import { buildGeneratedCasesModel, generatedCaseMatches } from './generatedCasesModel'

const content = JSON.stringify({
  cases: [
    { case_id: 'case-a', case_module: '清洗核验', case_type: '功能测试', case_title: '验证保存' },
    { case_id: 'case-b', case_module: '清洗核验', case_type: '功能测试', case_title: '验证取消' },
    { case_id: 'case-c', case_module: '清洗核验', case_type: '异常测试', case_title: '验证失败' },
    { case_id: 'case-d', case_module: '数据切片', case_title: '验证切片' },
  ],
})

describe('generatedCasesModel', () => {
  it('按模块和用例类型建立索引，保留源序号作为稳定 key', () => {
    const model = buildGeneratedCasesModel(content)!
    expect(model.modules).toHaveLength(2)
    expect(model.modules[0].scenes.map(scene => scene.title)).toEqual(['功能测试', '异常测试'])
    expect(model.modules[0].scenes[0].cases.map(entry => entry.testCase.displayName)).toEqual(['验证保存', '验证取消'])
    expect(model.modules[1].scenes[0].title).toBe('未分类用例')
    expect(model.entries.map(entry => entry.key)).toEqual(['清洗核验:0', '清洗核验:1', '清洗核验:2', '数据切片:3'])
    expect(model.sceneByEntryKey.get('清洗核验:2')?.title).toBe('异常测试')
    expect(model.moduleByEntryKey.get('数据切片:3')?.title).toBe('数据切片')
  })

  it('搜索覆盖用例名、模块、类型和标签值', () => {
    const model = buildGeneratedCasesModel(content)!
    expect(generatedCaseMatches(model.entries[0], '保存')).toBe(true)
    expect(generatedCaseMatches(model.entries[0], '清洗核验')).toBe(true)
    expect(generatedCaseMatches(model.entries[2], '异常测试')).toBe(true)
    expect(generatedCaseMatches(model.entries[0], 'case-a')).toBe(true)
    expect(generatedCaseMatches(model.entries[0], '不存在')).toBe(false)
  })

  it('无效或空产物返回空模型', () => {
    expect(buildGeneratedCasesModel('')).toBeNull()
    expect(buildGeneratedCasesModel('{}')).toBeNull()
    expect(buildGeneratedCasesModel(JSON.stringify({ cases: [] }))).toBeNull()
  })
})
