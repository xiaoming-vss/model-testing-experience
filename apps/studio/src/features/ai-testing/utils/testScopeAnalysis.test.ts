import { describe, expect, it } from 'vitest'
import {
  buildTestScopeView,
  questionRelatedCounts,
  relationRows,
  testObjectGroup,
} from './testScopeAnalysis'

const analysis = {
  schemaVersion: '1.0',
  artifactType: 'test_scope_impact_risk',
  testObjects: [
    { id: 'TO1', name: '存量记录迁移', type: '历史数据', description: '旧记录升级后仍需可读', basisStatus: 'confirmed', sourceBlockIds: ['b1'] },
    { id: 'TO2', name: '结果页导出', type: '页面交互', description: '结果页提供导出入口', basisStatus: 'inferred', sourceBlockIds: ['b1'] },
    { id: 'TO3', name: '接口失败重试', type: '接口流程', description: '失败后允许重试', basisStatus: 'unconfirmed', sourceBlockIds: [] },
    { id: 'TO4', name: '报告文件', type: '导出文件', description: '报告需要落盘', basisStatus: 'confirmed', sourceBlockIds: [] },
  ],
  impactAreas: [{ id: 'I1', area: '旧记录处理', impact: '升级后回退可能混用历史产物', testObjectIds: ['TO1'], sourceBlockIds: ['b1'], basisStatus: 'confirmed' }],
  risks: [{ id: 'R1', description: '历史产物可能混用', testObjectIds: ['TO1'], impactAreaIds: ['I1'], sourceBlockIds: ['b1'], basisStatus: 'inferred' }],
  openQuestions: [{ id: 'Q1', question: '其他记录如何处理？', testObjectIds: ['TO1'], impactAreaIds: ['I1'], riskIds: ['R1'], sourceBlockIds: ['b1'], sourceQuestionIds: ['MQ1'] }],
}

const material = JSON.stringify({
  sources: [{ id: 's1', name: '需求说明书', type: 'document' }],
  materialBlocks: [{ id: 'b1', sourceId: 's1', locator: '需求 2.1', kind: 'paragraph', content: { text: '指定记录回退' } }],
  questions: [{ id: 'MQ1', question: '旧数据是否保留？' }],
})

describe('测试范围视图模型', () => {
  it('按测试对象类型归入可浏览的粗分组', () => {
    expect(testObjectGroup('历史数据')).toBe('存量与配置')
    expect(testObjectGroup('页面交互')).toBe('页面与操作')
    expect(testObjectGroup('接口流程')).toBe('流程与异常')
    expect(testObjectGroup('导出文件')).toBe('数据与产物')
    expect(testObjectGroup('')).toBe('其他')
  })

  it('从正向引用推导反向关联，并汇总状态与待确认范围', () => {
    const view = buildTestScopeView(analysis, material)
    const object = view.categories.testObjects.items[0]
    const impact = view.categories.impactAreas.items[0]
    const risk = view.categories.risks.items[0]
    const question = view.categories.openQuestions.items[0]

    expect(object.relationIds.impactAreas).toEqual(['I1'])
    expect(object.relationIds.risks).toEqual(['R1'])
    expect(object.relationIds.openQuestions).toEqual(['Q1'])
    expect(impact.relationIds.testObjects).toEqual(['TO1'])
    expect(impact.relationIds.risks).toEqual(['R1'])
    expect(impact.relationIds.openQuestions).toEqual(['Q1'])
    expect(risk.relationIds.openQuestions).toEqual(['Q1'])
    expect(question.status).toBe('unconfirmed')
    expect(question.sourceQuestionIds).toEqual(['MQ1'])

    expect(view.categories.testObjects.statusCounts).toEqual({ confirmed: 2, inferred: 1, unconfirmed: 1 })
    expect(view.categories.testObjects.groups.map((group) => group.label)).toEqual(['页面与操作', '数据与产物', '流程与异常', '存量与配置'])
    expect(questionRelatedCounts(view.categories.openQuestions)).toEqual({ objects: 1, impacts: 1, risks: 1 })
    expect(relationRows(object, 'testObjects', view).map((row) => row.category)).toEqual(['impactAreas', 'risks', 'openQuestions'])
    expect(view.blockById.get('b1')).toMatchObject({ sourceName: '需求说明书', sourceType: 'document', locator: '需求 2.1' })
    expect(view.sourceQuestionById.get('MQ1')).toBe('旧数据是否保留？')
  })

  it('材料内容无法解析时不伪造证据', () => {
    const view = buildTestScopeView(analysis, '{not-json')
    expect(view.blockById.size).toBe(0)
    expect(view.sourceQuestionById.size).toBe(0)
  })
})
