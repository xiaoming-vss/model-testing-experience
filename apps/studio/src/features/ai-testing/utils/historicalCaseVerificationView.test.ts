import { describe, expect, it } from 'vitest'
import { analysis, frozenInput } from '../components/HistoricalCaseVerificationView/__fixtures__/historicalCaseVerification'
import { batchTitle, buildCaseVerification, caseVerificationCounts, caseRank, decisionMeta, decisionTags, findingTitle } from './historicalCaseVerificationView'

const content = JSON.stringify(analysis)
const material = JSON.stringify(frozenInput)

describe('buildCaseVerification', () => {
  it('按规则批次汇总用例结论，并用冻结输入还原规则原文和用例全文', () => {
    const view = buildCaseVerification(content, material)!
    expect(view.frozen).toBe(true)
    expect(view.batches.map(batch => [batch.id, batch.rule?.changeSummary, batch.effect?.label, batch.historyRequirementId])).toEqual([
      ['batch-1', '管理员账号的失败锁定阈值由 5 次降为 3 次。', '已变更', 'req-old'],
      ['batch-3', '超时自动解锁改由安全管理员手动解锁接管。', '已替代', 'req-old'],
      ['batch-4', '审计字段追加设备信息。', '已补充', ''],
    ])
    const [modified, pending] = view.batches[0].findings
    expect(modified).toMatchObject({
      id: 'batch-1/case-a', decision: { label: '需修改' }, fullCase: false,
      evidence: [{ kind: 'step', position: 1, text: '输入错误密码登录。', expected: '可以继续重试，账号未锁定。' }],
      snapshot: { title: '管理员第 3 次密码校验失败后可重试', suiteId: 'suite-1', module: '登录安全', steps: [{ position: 1 }, { position: 2 }] },
    })
    expect(pending).toMatchObject({ decision: { label: '待确认' } })
    expect(view.decisions).toEqual({ modify: 1, needs_confirmation: 1, invalidate: 1 })
  })

  it('同一条用例的判定标签去重后按处理优先级排序，用例按最需要处理的结论排序', () => {
    const view = buildCaseVerification(content, material)!
    expect(view.cases.map(caseRank)).toEqual([0, 1])
    expect(decisionTags(view.cases[1].findings).map(tag => tag.key)).toEqual(['invalidate'])
    expect(view.cases.map(item => findingTitle(item.findings[0]))).toEqual([
      '管理员第 3 次密码校验失败后可重试', '管理员锁定 15 分钟后自动解锁',
    ])
    expect(batchTitle(view.batches[0])).toBe('管理员账号的失败锁定阈值由 5 次降为 3 次。')
  })

  it('补读全文后的结论替换同批同用例的初次结论，并标记来源', () => {
    const view = buildCaseVerification(content, material)!
    // 夹具里 batch-3 首次为待确认，补读后为建议失效。
    expect(view.batches[1].findings).toHaveLength(1)
    expect(view.batches[1].findings[0]).toMatchObject({
      caseId: 'case-c', decision: { key: 'invalidate', label: '建议失效' }, fullCase: true,
      evidence: [{ kind: 'step', position: 1 }, { kind: 'step', position: 2 }],
    })
  })

  it('维护清单只保留需修改和建议失效的结论', () => {
    const view = buildCaseVerification(content, material)!
    expect(view.cases.map(item => [item.caseId, item.findings.map(finding => `${finding.batch.id}:${finding.decision.key}`)])).toEqual([
      ['case-a', ['batch-1:modify']],
      ['case-c', ['batch-3:invalidate']],
    ])
  })

  it('补测测试点挂到所属规则，保留顺序和编号', () => {
    const view = buildCaseVerification(content, material)!
    expect(view.points.map(item => [item.id, item.title, item.batch.id])).toEqual([
      ['batch-1:firstPass:scenario-1', '再次输入错误密码。 账号未锁定。', 'batch-1'],
      ['batch-4:firstPass:point-1', '验证锁定审计记录包含设备信息。', 'batch-4'],
    ])
  })

  it('冻结输入不可用或类型不符时保留结论，只显示证据位置', () => {
    for (const unavailable of [undefined, '{}', JSON.stringify({ ...frozenInput, artifactType: 'other' })]) {
      const view = buildCaseVerification(content, unavailable)!
      expect(view.frozen).toBe(false)
      expect(view.batches[0]).toMatchObject({ rule: null, effect: null, historyRequirementId: '' })
      expect(view.batches[0].findings[0]).toMatchObject({
        snapshot: null, evidence: [{ kind: 'step', position: 1, text: null, expected: null }],
      })
      // 结论、理由和补测测试点都来自产物本身，不受影响。
      expect(view.findings).toHaveLength(3)
      expect(view.points).toHaveLength(2)
    }
  })

  it('冻结输入里找不到的条目只保留位置，不编造原文', () => {
    const partial = JSON.stringify({ ...frozenInput, fullCases: {} })
    const view = buildCaseVerification(content, partial)!
    expect(view.frozen).toBe(true)
    expect(view.batches[0].rule?.changeSummary).toBe('管理员账号的失败锁定阈值由 5 次降为 3 次。')
    expect(view.batches[0].findings[0].snapshot).toBeNull()
    expect(view.batches[0].findings[0].evidence[0]).toMatchObject({ text: null, expected: null })
  })

  it('未登记的判定不进入审核清单；结构不符的产物返回 null', () => {
    const legacy = JSON.parse(content)
    legacy.batches[0].firstPass.caseFindings[0].decision = 'legacy'
    expect(buildCaseVerification(JSON.stringify(legacy), material)!.cases.map(item => item.caseId)).toEqual(['case-c'])
    expect(decisionMeta(null)).toEqual({ key: '未知', label: '未知', tone: 'info' })
    expect(buildCaseVerification('not json')).toBeNull()
    expect(buildCaseVerification(JSON.stringify({ functionalOverview: {} }))).toBeNull()
  })
})

describe('caseVerificationCounts', () => {
  it('统计待维护用例、待确认和补测测试点', () => {
    expect(caseVerificationCounts(content)).toEqual([[2, '条待维护用例'], [1, '项待确认'], [2, '条补测测试点']])
    expect(caseVerificationCounts(JSON.stringify({ ...analysis, batches: [] }))).toEqual([[0, '条待维护用例'], [0, '项待确认'], [0, '条补测测试点']])
    expect(caseVerificationCounts('not json')).toBeNull()
  })
})
