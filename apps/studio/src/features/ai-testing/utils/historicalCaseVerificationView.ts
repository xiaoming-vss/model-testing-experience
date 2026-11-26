import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from './functionalOutput'
import { parseJsonRecord, ruleEffectMeta, textList, type HistoricalEnum, type HistoricalTone, type RuleScope } from './historicalRelationView'

export type DecisionTone = HistoricalTone | 'plain'
export type DecisionMeta = { key: string; label: string; tone: DecisionTone }

/** 文案取自默认 Skill 对各判定的定义。琥珀色给了「需修改」，「待确认」因此使用评审紫。 */
export const CASE_DECISION = {
  reuse: { label: '可复用', tone: 'ok' },
  modify: { label: '需修改', tone: 'warn' },
  invalidate: { label: '建议失效', tone: 'danger' },
  unaffected: { label: '不受影响', tone: 'plain' },
  needs_confirmation: { label: '待确认', tone: 'review' },
} as const
export type CaseDecision = keyof typeof CASE_DECISION
export const MAINTENANCE_DECISIONS = ['modify', 'invalidate'] as const
export type MaintenanceDecision = typeof MAINTENANCE_DECISIONS[number]
export const REVIEW_DECISIONS = [...MAINTENANCE_DECISIONS, 'needs_confirmation'] as const

export function decisionMeta(value: unknown): DecisionMeta {
  const key = toDisplayText(value)
  if (key && Object.prototype.hasOwnProperty.call(CASE_DECISION, key)) {
    return { key, ...CASE_DECISION[key as CaseDecision] }
  }
  return { key: key || '未知', label: key || '未知', tone: 'info' }
}
export const isMaintenanceDecision = (decision: string) => MAINTENANCE_DECISIONS.some(key => key === decision)
export const decisionRank = (decision?: string) => {
  const rank = REVIEW_DECISIONS.findIndex(key => key === decision)
  return rank < 0 ? REVIEW_DECISIONS.length : rank
}

export type CaseSnapshotView = {
  caseId: string
  requirementId: string
  suiteId: string
  module: string
  title: string
  preconditions: Array<{ position: number; text: string }>
  steps: Array<{ position: number; action: string; expected: string }>
}
/** text 为前置条件原文或步骤操作；expected 仅步骤有值。两者都为 null 表示冻结输入里找不到原文。 */
export type EvidenceView = { kind: 'precondition' | 'step'; position: number; text: string | null; expected: string | null }
export type VerificationRuleView = { changeSummary: string; previousRule: string; currentRule: string | null; scope: RuleScope }
export type VerificationBatchView = {
  id: string
  impactId: string
  /** 冻结输入不可用时没有规则原文，列表回退为「规则 + 影响项 ID」。 */
  rule: VerificationRuleView | null
  effect: HistoricalEnum | null
  /** 规则所属的历史需求；批次没有命中用例时无法从冻结输入得知。 */
  historyRequirementId: string
  findings: CaseFindingView[]
  points: SupplementalPointView[]
}
export type CaseFindingView = {
  id: string
  caseId: string
  caseSnapshotId: string
  decision: DecisionMeta
  evidence: EvidenceView[]
  reason: string
  modificationHint: string | null
  /** 结论来自补读全文后的结果。 */
  fullCase: boolean
  snapshot: CaseSnapshotView | null
  batch: VerificationBatchView
}
export type SupplementalPointView = {
  id: string
  order: number
  title: string
  batch: VerificationBatchView
}
export type VerificationCaseView = { caseId: string; findings: CaseFindingView[] }

/** 规则在界面上的名称：冻结输入不可用时回退为「规则 + 影响项 ID」。 */
export const batchTitle = (batch: VerificationBatchView) => batch.rule?.changeSummary ?? `规则 ${batch.impactId}`
export const findingTitle = (finding: CaseFindingView) => finding.snapshot?.title ?? finding.caseId
/** 同一条用例在各规则下的判定标签，去重后按处理优先级排序。 */
export const decisionTags = (findings: CaseFindingView[]) => [...new Map(findings.map(finding => [finding.decision.key, finding.decision])).values()]
  .sort((a, b) => decisionRank(a.key) - decisionRank(b.key))
/** 用例在历史用例列表里的先后：先列最需要处理的用例。 */
export const caseRank = (item: VerificationCaseView) => decisionRank(decisionTags(item.findings)[0]?.key)
export type CaseVerificationData = {
  frozen: boolean
  batches: VerificationBatchView[]
  findings: CaseFindingView[]
  points: SupplementalPointView[]
  cases: VerificationCaseView[]
  decisions: Record<string, number>
}

type FrozenInput = {
  batches: Array<{ id: string; effect: unknown; rule: VerificationRuleView | null; historyRequirementId: string }>
  cases: Map<string, CaseSnapshotView>
}

function snapshotOf(caseId: string, value: unknown): CaseSnapshotView | null {
  const record = toRecord(value)
  if (!record) return null
  return {
    caseId,
    requirementId: toDisplayText(record.requirementId),
    suiteId: toDisplayText(record.suiteId),
    module: toDisplayText(record.module),
    title: toDisplayText(record.title) || caseId,
    preconditions: toRecordArray(record.preconditions).map(item => ({ position: Number(item.position), text: toDisplayText(item.text) })),
    steps: toRecordArray(record.steps).map(item => ({ position: Number(item.position), action: toDisplayText(item.action), expected: toDisplayText(item.expected) })),
  }
}

/** 只读取本次冻结的核验输入；类型不符时视为不可用，界面退回为只显示结论和证据位置。 */
function frozenInput(materialContent?: string | null): FrozenInput | null {
  const input = parseJsonRecord(materialContent)
  if (!input || toDisplayText(input.artifactType) !== 'historical_test_case_verification_run_input') return null
  return {
    batches: toRecordArray(input.batches).map((batch) => {
      const impact = toRecord(batch.impact)
      const scope = toRecord(impact?.scope)
      return {
        id: toDisplayText(batch.batchId),
        effect: impact?.ruleEffect,
        // 同一批候选用例都绑定在该规则所属的历史需求下。
        historyRequirementId: toDisplayText(toRecordArray(batch.candidateCases)[0]?.requirementId),
        rule: impact
          ? {
              changeSummary: toDisplayText(impact.changeSummary),
              previousRule: toDisplayText(impact.previousRule),
              currentRule: toDisplayText(impact.currentRule) || null,
              scope: { roles: textList(scope?.roles), states: textList(scope?.states), conditions: textList(scope?.conditions) },
            }
          : null,
      }
    }),
    cases: new Map(Object.entries(toRecord(input.fullCases) ?? {}).flatMap(([caseId, value]) => {
      const snapshot = snapshotOf(caseId, value)
      return snapshot ? [[caseId, snapshot] as const] : []
    })),
  }
}

function evidenceOf(item: Record<string, unknown>, snapshot: CaseSnapshotView | null): EvidenceView[] {
  return toRecordArray(item.evidence).map((entry) => {
    const kind = entry.kind === 'precondition' ? 'precondition' : 'step'
    const position = Number(entry.position)
    const precondition = kind === 'precondition' ? snapshot?.preconditions.find(line => line.position === position) : undefined
    const step = kind === 'step' ? snapshot?.steps.find(line => line.position === position) : undefined
    return { kind, position, text: precondition?.text || step?.action || null, expected: step?.expected || null }
  })
}

/**
 * 历史用例核验产物的读取口径：界面只呈现产物与冻结输入里已有的字段，不补造结论。
 * 结构不符（例如旧内容）时返回 null，由宿主提示切换到 JSON。
 */
export function buildCaseVerification(content: string, materialContent?: string | null): CaseVerificationData | null {
  const output = parseJsonRecord(content)
  if (!output || !Array.isArray(output.batches)) return null
  const input = frozenInput(materialContent)
  const frozen: FrozenInput = input ?? { batches: [], cases: new Map() }
  const findings: CaseFindingView[] = []
  const points: SupplementalPointView[] = []
  const pointKeys = new Set<string>()
  const caseById = new Map<string, VerificationCaseView>()
  const batches: VerificationBatchView[] = []
  toRecordArray(output.batches).forEach((entry, index) => {
    // 补读结论替换同批同用例的初次结论，所以后一轮覆盖前一轮。
    const passes = [entry.firstPass, entry.fullCasePass].map(toRecord).filter((pass): pass is Record<string, unknown> => Boolean(pass))
    const [firstPass] = passes
    if (!firstPass) return
    const id = toDisplayText(firstPass.batchId) || `batch-${index + 1}`
    const source = frozen.batches.find(batch => batch.id === id)
    if (source?.effect === 'still_applies') return
    const batch: VerificationBatchView = {
      id,
      impactId: toDisplayText(firstPass.impactId),
      rule: source?.rule ?? null,
      effect: source ? ruleEffectMeta(source.effect) : null,
      historyRequirementId: source?.historyRequirementId ?? '',
      findings: [],
      points: [],
    }
    batches.push(batch)
    const merged = new Map<string, CaseFindingView>()
    passes.forEach((pass, passIndex) => toRecordArray(pass.caseFindings).forEach((item) => {
      const caseId = toDisplayText(item.caseId)
      const evidence = evidenceOf(item, frozen.cases.get(caseId) ?? null)
      merged.set(caseId, {
        id: `${id}/${caseId}`,
        caseId,
        caseSnapshotId: toDisplayText(item.caseSnapshotId),
        decision: decisionMeta(item.decision),
        evidence,
        reason: toDisplayText(item.reason),
        modificationHint: toDisplayText(item.modificationHint) || null,
        fullCase: passIndex > 0,
        snapshot: frozen.cases.get(caseId) ?? null,
        batch,
      })
    }))
    merged.forEach((finding) => {
      const maintenance = isMaintenanceDecision(finding.decision.key)
      if (!maintenance && finding.decision.key !== 'needs_confirmation') return
      batch.findings.push(finding)
      findings.push(finding)
      if (!maintenance) return
      const existing = caseById.get(finding.caseId)
      if (existing) existing.findings.push(finding)
      else caseById.set(finding.caseId, { caseId: finding.caseId, findings: [finding] })
    })
    passes.forEach((pass, passIndex) => {
      const legacy = pass.schemaVersion !== '0.2'
      const passName = passIndex === 0 ? 'firstPass' : 'fullCasePass'
      for (const item of toRecordArray(legacy ? pass.supplementalScenarios : pass.supplementalPoints)) {
        const title = legacy
          ? [toDisplayText(item.action), toDisplayText(item.expected)].filter(Boolean).join(' ')
          : toDisplayText(item.title).trim()
        const key = JSON.stringify([batch.impactId, title])
        if (!title || pointKeys.has(key)) continue
        pointKeys.add(key)
        const pointId = toDisplayText(legacy ? item.scenarioId : item.pointId)
        const view: SupplementalPointView = {
          id: `${id}:${passName}:${pointId}`,
          order: points.length + 1,
          title,
          batch,
        }
        batch.points.push(view)
        points.push(view)
      }
    })
  })
  const decisions: Record<string, number> = {}
  findings.forEach((finding) => { decisions[finding.decision.key] = (decisions[finding.decision.key] ?? 0) + 1 })
  return { frozen: input !== null, batches, findings, points, cases: [...caseById.values()], decisions }
}

/** 侧栏「内容概况」：只统计产物里真实存在的对象。 */
export function caseVerificationCounts(content: string, materialContent?: string | null): Array<[value: number, unit: string]> | null {
  const view = buildCaseVerification(content, materialContent)
  return view
    ? [[view.cases.length, '条待维护用例'], [view.decisions.needs_confirmation ?? 0, '项待确认'], [view.points.length, '条补测测试点']]
    : null
}
