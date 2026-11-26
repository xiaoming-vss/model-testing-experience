import { describe, expect, it } from 'vitest'
import { analysis } from '../components/HistoricalRelationView/__fixtures__/historicalRelation'
import { analysis as verification } from '../components/HistoricalCaseVerificationView/__fixtures__/historicalCaseVerification'
import { stageContentStats } from './stageContentStats'

const material = JSON.stringify({
  functions: [
    { sections: [{ items: [{ text: 'a' }, { text: 'b' }] }, { items: [] }] },
    { sections: '不是数组' },
    null,
  ],
  questions: [{}, {}],
})

describe('stageContentStats', () => {
  it('材料整理按原有口径统计章节、规则和待确认', () => {
    expect(stageContentStats('extracting_text', material)).toEqual([[2, '个章节'], [2, '条规则'], [2, '个待确认']])
    expect(stageContentStats('extracting_text', JSON.stringify({ functions: [] }))).toBeNull()
  })

  it('历史需求关联统计关联、规则影响和待确认', () => {
    expect(stageContentStats('historical_requirement_relations', JSON.stringify(analysis))).toEqual([[2, '条关联'], [3, '项规则影响'], [2, '个待确认']])
  })

  it('历史用例核验统计待维护用例、待确认和补测测试点', () => {
    expect(stageContentStats('historical_test_case_verification', JSON.stringify(verification))).toEqual([[2, '条待维护用例'], [1, '项待确认'], [2, '条补测测试点']])
  })

  it('其他阶段、空内容和无法解析的内容不统计', () => {
    expect(stageContentStats('requirement_review', material)).toBeNull()
    expect(stageContentStats('extracting_text', '')).toBeNull()
    expect(stageContentStats('extracting_text', 'not json')).toBeNull()
  })
})
