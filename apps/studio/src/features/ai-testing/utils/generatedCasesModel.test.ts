import { describe, expect, it } from 'vitest'
import { buildGeneratedCasesModel, hasOnlyGeneratedCaseHistory, readGeneratedCaseHistory } from './generatedCasesModel'

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

  it('无效或空产物返回空模型', () => {
    expect(buildGeneratedCasesModel('')).toBeNull()
    expect(buildGeneratedCasesModel('{}')).toBeNull()
    expect(buildGeneratedCasesModel(JSON.stringify({ cases: [] }))).toBeNull()
  })

  it('读取产物里的历史用例结论，没有时返回 null', () => {
    const findings = [{ caseId: 'old-1', decision: 'reuse' }]
    expect(readGeneratedCaseHistory(JSON.stringify({ cases: [], historicalCaseFindings: findings }))).toEqual(findings)
    expect(readGeneratedCaseHistory(content)).toBeNull()
    expect(readGeneratedCaseHistory('not json')).toBeNull()
  })

  it('只有历史结论、没有新用例的完整用例产物不提供导入', () => {
    expect(hasOnlyGeneratedCaseHistory(JSON.stringify({ cases: [], historicalCaseFindings: [] }))).toBe(true)
    expect(hasOnlyGeneratedCaseHistory(JSON.stringify({ cases: [{ case_id: 'case-a' }], historicalCaseFindings: [] }))).toBe(false)
    expect(hasOnlyGeneratedCaseHistory(content)).toBe(false)
    expect(hasOnlyGeneratedCaseHistory('')).toBe(false)
    expect(hasOnlyGeneratedCaseHistory(undefined)).toBe(false)
  })
})
