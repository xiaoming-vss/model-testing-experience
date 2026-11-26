/** 历史用例核验的示例产物与冻结输入，字段按 0.1 契约；只供测试使用。 */

const identity = (artifactType: string) => ({
  schemaVersion: '0.1', artifactType, requirementId: 'req-new', materialSnapshotId: 'mat-1', impactResultId: 'rel-snap-1',
})
const rule = (impactId: string, ruleEffect: string, previousRule: string, currentRule: string | null, changeSummary: string) => ({
  impactId, ruleEffect, changeSummary, previousRule, currentRule,
  scope: { roles: ['管理员'], states: ['账号未锁定'], conditions: ['连续登录失败'] },
})
const fullCase = (caseId: string, suiteId: string, title: string, preconditions: string[], steps: Array<[string, string]>) => ({
  caseId, requirementId: 'req-old', suiteId, caseSnapshotId: `${caseId}-snap-1`, module: '登录安全', title, contentScope: 'full_case',
  preconditions: preconditions.map((text, index) => ({ position: index + 1, text })),
  steps: steps.map(([action, expected], index) => ({ position: index + 1, action, expected })),
})
const cases = {
  'case-a': fullCase('case-a', 'suite-1', '管理员第 3 次密码校验失败后可重试', ['管理员账号连续登录失败 2 次。'],
    [['输入错误密码登录。', '可以继续重试，账号未锁定。'], ['输入正确密码登录。', '登录成功。']]),
  'case-b': fullCase('case-b', 'suite-2', '普通用户连续输错 5 次被锁定', [],
    [['连续 4 次输入错误密码。', '账号未锁定。'], ['第 5 次输入错误密码。', '账号被锁定。']]),
  'case-c': fullCase('case-c', 'suite-2', '管理员锁定 15 分钟后自动解锁', ['管理员账号被锁定。'],
    [['等待 15 分钟。', '锁定状态保持。'], ['使用正确密码登录。', '登录成功。']]),
  'case-d': fullCase('case-d', 'suite-1', '锁定后的验证码引导', ['账号已被锁定。'],
    [['查看是否要求验证码。', '不要求验证码。']]),
}
/** 冻结输入里命中片段只保留命中的步骤，位置沿用完整快照的原编号。 */
const excerpt = (caseId: string, positions: number[]) =>
  ({ ...cases[caseId as keyof typeof cases], contentScope: 'matched_excerpt', steps: cases[caseId as keyof typeof cases].steps.filter(step => positions.includes(step.position)) })
const batch = (batchId: string, impact: ReturnType<typeof rule>, candidateCases: unknown[]) =>
  ({ ...identity('historical_test_case_verification_input'), batchId, impact, candidateCases })

const RULES = {
  impact1: rule('impact-1', 'changed', '管理员连续输错密码 5 次后锁定账号。', '管理员连续输错密码 3 次后锁定账号。', '管理员账号的失败锁定阈值由 5 次降为 3 次。'),
  impact2: rule('impact-2', 'still_applies', '普通用户连续输错密码 5 次后锁定账号。', '普通用户连续输错密码 5 次后锁定账号。', '普通用户的锁定阈值未变，本次沿用该规则。'),
  impact3: rule('impact-3', 'replaced', '管理员账号锁定 15 分钟后自动解锁。', '账号锁定后由安全管理员复核身份并手动解锁。', '超时自动解锁改由安全管理员手动解锁接管。'),
  impact4: rule('impact-4', 'supplemented', '每次登录失败记录账号与 IP。', '每次登录失败记录账号、IP 与设备。', '审计字段追加设备信息。'),
}

export const frozenInput = {
  ...identity('historical_test_case_verification_run_input'),
  batches: [
    batch('batch-1', RULES.impact1, [excerpt('case-a', [1]), excerpt('case-b', [1]), excerpt('case-d', [1])]),
    batch('batch-2', RULES.impact2, [excerpt('case-b', [1, 2])]),
    batch('batch-3', RULES.impact3, [excerpt('case-c', [1])]),
    // 没有命中用例的规则仍可提炼补测场景。
    batch('batch-4', RULES.impact4, []),
  ],
  fullCases: cases,
}

const finding = (caseId: string, decision: string, evidence: Array<[string, number]>, reason: string, modificationHint: string | null = null, needsFullCase = false) =>
  ({ caseId, caseSnapshotId: `${caseId}-snap-1`, decision, evidence: evidence.map(([kind, position]) => ({ kind, position })), reason, modificationHint, needsFullCase })
const scenario = (scenarioId: string, preconditions: string[], action: string, expected: string, reason: string) =>
  ({ scenarioId, preconditions, action, expected, reason })
const pass = (batchId: string, impactId: string, caseFindings: unknown[], supplementalScenarios: unknown[]) =>
  ({ ...identity('historical_test_case_verification'), batchId, impactId, caseFindings, supplementalScenarios })

/** 每批保留首次结果和可选的补读结果；batch-3 的结论在补读全文后由待确认变为建议失效。 */
export const analysis = {
  ...identity('historical_test_case_verification_result'),
  batches: [
    { firstPass: pass('batch-1', 'impact-1', [
      finding('case-a', 'modify', [['step', 1]], '步骤 1 预期第 3 次失败后仍可重试，与本次规则冲突。', '将步骤 1 的预期改为「账号被锁定」。'),
      finding('case-b', 'unaffected', [], '用例验证的是普通用户的锁定阈值，不在本规则适用范围内。'),
      finding('case-d', 'needs_confirmation', [['step', 1]], '本次规则未说明锁定后是否需要验证码，无法判定步骤 1 的预期。'),
    ], [scenario('scenario-1', ['管理员账号连续登录失败 1 次。'], '再次输入错误密码。', '账号未锁定。', '确认第 2 次失败不触发锁定。')]), fullCasePass: null },
    { firstPass: pass('batch-2', 'impact-2', [
      finding('case-b', 'reuse', [['step', 1], ['step', 2]], '步骤 1–2 已覆盖普通用户 5 次失败锁定的阈值与结果。'),
    ], []), fullCasePass: null },
    { firstPass: pass('batch-3', 'impact-3', [
      finding('case-c', 'needs_confirmation', [], '片段只包含等待步骤，无法判断整条用例是否仍有验证价值。', null, true),
    ], []), fullCasePass: pass('batch-3', 'impact-3', [
      finding('case-c', 'invalidate', [['step', 1], ['step', 2]], '整条用例专门验证自动解锁，该行为已由手动解锁接管。'),
    ], []) },
    { firstPass: {
      ...identity('historical_test_case_verification'), schemaVersion: '0.2', batchId: 'batch-4', impactId: 'impact-4',
      caseFindings: [], supplementalPoints: [{ pointId: 'point-1', title: '验证锁定审计记录包含设备信息。' }],
    }, fullCasePass: null },
  ],
}

export const emptyAnalysis = { ...analysis, batches: [] }
