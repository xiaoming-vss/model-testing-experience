import { describe, expect, it } from 'vitest'
import { analysis, frozenInput } from '../components/HistoricalRelationView/__fixtures__/historicalRelation'
import { buildHistoricalRelationView, historicalRelationCounts } from './historicalRelationView'

const content = JSON.stringify(analysis)
const material = JSON.stringify(frozenInput)
const names = (id: string) => ({ name: `名称：${id}`, sprintName: '第 18 迭代' })

describe('buildHistoricalRelationView', () => {
  it('按历史需求汇总规则影响，并用冻结输入还原两侧条目原文', () => {
    const view = buildHistoricalRelationView(content, material, names)!
    expect(view.relations.map((relation) => [relation.id, relation.name, relation.sprintName, relation.type.label])).toEqual([
      ['rel-1', '名称：req-old', '第 18 迭代', '规则变更'],
      ['rel-2', '名称：req-mid', '第 18 迭代', '补充规则'],
    ])
    const [impact, retired] = view.relations[0].impacts
    expect(impact.historical[0]).toMatchObject({
      id: '1-3-1', text: '管理员连续输错密码 5 次后锁定账号。', functionName: '管理员登录', status: { label: '明确' },
    })
    expect(impact.current[0]).toMatchObject({ id: '1-3-1', status: { label: '明确' } })
    expect(retired).toMatchObject({
      effect: { label: '已取消' }, status: { label: '待确认' }, currentRule: null, scope: { states: ['账号已锁定'] },
    })
    // 冻结输入里找不到的条目只保留引用，不编造原文。
    expect(retired.historical).toEqual([{ id: 'missing', text: '', functionName: '', sectionTitle: '', status: null }])
    expect(view.knownRelations).toEqual([{ from: 'req-mid', to: 'req-old', type: { key: 'supplements', label: '补充规则', tone: 'info' } }])
  })

  it('把待确认问题挂到对应规则，未定位的问题保持独立', () => {
    const view = buildHistoricalRelationView(content, material)!
    expect(view.questions.map((question) => [question.id, question.question, question.impact?.id])).toEqual([
      ['Q1', '邮件自助解锁是否一并取消？', 'imp-2'],
      ['Q2', '是否涉及第三方登录？', undefined],
    ])
    expect(view.relations[0].impacts[1].questions.map((question) => question.id)).toEqual(['Q1'])
    expect(view.relations[0].impacts[0].questions).toEqual([])
  })

  it('冻结输入不可用或类型不符时只保留条目引用', () => {
    for (const unavailable of [undefined, '{}', JSON.stringify({ ...frozenInput, artifactType: 'other' })]) {
      const view = buildHistoricalRelationView(content, unavailable)!
      expect(view.relations[0].impacts[0].current[0]).toMatchObject({ id: '1-3-1', text: '', status: null })
      expect(view.knownRelations).toEqual([])
    }
  })

  it('未登记的枚举值保留原文；未提供需求名称时回退为需求 ID', () => {
    const unknown = JSON.stringify({ ...analysis, relations: [{ ...analysis.relations[0], relationType: 'legacy_kind' }] })
    const view = buildHistoricalRelationView(unknown)!
    expect(view.relations[0].type).toEqual({ key: 'legacy_kind', label: 'legacy_kind', tone: 'info' })
    expect(view.relations[0].name).toBe('req-old')
  })

  it('结构不符的产物返回 null', () => {
    expect(buildHistoricalRelationView('not json')).toBeNull()
    expect(buildHistoricalRelationView(JSON.stringify({ functionalOverview: { purpose: '旧内容' } }))).toBeNull()
    expect(buildHistoricalRelationView(JSON.stringify({ relations: [] }))).toBeNull()
  })

  it('空关联结果保留已发现的待确认问题', () => {
    const view = buildHistoricalRelationView(JSON.stringify({ ...analysis, relations: [] }))!
    expect(view.relations).toEqual([])
    expect(view.questions.map((question) => question.id)).toEqual(['Q1', 'Q2'])
  })
})

describe('historicalRelationCounts', () => {
  it('统计关联、规则影响和待确认', () => {
    expect(historicalRelationCounts(content)).toEqual([[2, '条关联'], [3, '项规则影响'], [2, '个待确认']])
    expect(historicalRelationCounts('not json')).toBeNull()
  })
})
