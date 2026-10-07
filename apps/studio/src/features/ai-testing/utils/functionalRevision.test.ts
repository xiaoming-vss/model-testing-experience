import { describe, expect, it } from 'vitest'
import { buildRevisionTemplate, getRevisionQuestions } from './functionalRevision'

const questions = [{ questionId: 'Q01', question: '离线时如何提示？' }, { questionId: 'Q02', question: '解绑入口在哪里？' }]
describe('优化问题模板', () => {
  it.each([
    { openQuestions: questions },
    JSON.stringify({ openQuestions: questions }),
    { requirementAnalysis: { openQuestions: questions } },
    JSON.stringify({ requirementAnalysis: JSON.stringify({ openQuestions: questions }) }),
  ])('兼容直接分析和嵌套配置', (input) => {
    expect(getRevisionQuestions(input)).toEqual([{ id: 'Q01', question: '离线时如何提示？' }, { id: 'Q02', question: '解绑入口在哪里？' }])
  })
  it('忽略无效问题，为缺失编号提供编号', () => {
    expect(getRevisionQuestions({ openQuestions: [null, { question: ' ' }, { question: ' 哪个入口？ ' }] })).toEqual([{ id: 'Q03', question: '哪个入口？' }])
    expect(getRevisionQuestions('invalid')).toEqual([])
  })
  it('两阶段需求产物保留问题编号并排除历史已解决项', () => {
    expect(getRevisionQuestions(JSON.stringify({ questions: [
      { id: 'Q07', question: ' 结果如何展示？ ', status: 'open' },
      { id: 'Q08', question: '已确认的入口？', status: 'resolved' },
    ] }))).toEqual([{ id: 'Q07', question: '结果如何展示？' }])
    expect(buildRevisionTemplate([{ id: 'Q07', question: '结果如何展示？' }], '材料提取结果', '答复')).toContain('答复：[请填写已确认的信息]')
    expect(getRevisionQuestions({ questions: [], openQuestions: questions })).toEqual([])
  })
  it('预填全部问题和答案占位符，不推测答案', () => {
    const template = buildRevisionTemplate(getRevisionQuestions({ openQuestions: questions }), '测试点')
    expect(template).toContain('优化当前测试点')
    expect(template).toContain('【Q01】离线时如何提示？')
    expect(template).toContain('【Q02】解绑入口在哪里？')
    expect(template.match(/补充：\[请填写已确认的信息\]/g)).toHaveLength(2)
    expect(template).toContain('继续保留为待确认，不要推测答案')
    expect(buildRevisionTemplate([], '需求分析')).toBe('')
  })
})
