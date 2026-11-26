import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from './functionalOutput'

export type HistoricalTone = 'ok' | 'info' | 'warn' | 'review' | 'danger'
export type HistoricalEnum = { key: string; label: string; tone: HistoricalTone }
/** 规则的适用范围；三个维度都可以为空，表示材料未列明。 */
export type RuleScope = { roles: string[]; states: string[]; conditions: string[] }
type EnumMeta = { readonly label: string; readonly tone: HistoricalTone }

/** 关系类型取本次需求对历史需求的主要动作，规则效果按单条规则记录；文案依据 Skill 对各枚举的定义。 */
export const RELATION_TYPE = {
  depends_on: { label: '沿用规则', tone: 'ok' },
  supplements: { label: '补充规则', tone: 'info' },
  changes: { label: '规则变更', tone: 'warn' },
  replaces: { label: '替代规则', tone: 'review' },
} as const
export type RelationType = keyof typeof RELATION_TYPE

export const RULE_EFFECT = {
  still_applies: { label: '仍然适用', tone: 'ok' },
  supplemented: { label: '已补充', tone: 'info' },
  changed: { label: '已变更', tone: 'warn' },
  replaced: { label: '已替代', tone: 'review' },
  retired: { label: '已取消', tone: 'danger' },
} as const
export const RULE_EFFECT_ORDER = Object.keys(RULE_EFFECT) as Array<keyof typeof RULE_EFFECT>

export const REVIEW_STATUS = {
  proposed: { label: '依据充分', tone: 'ok' },
  needs_confirmation: { label: '待确认', tone: 'warn' },
} as const
export type ReviewStatus = keyof typeof REVIEW_STATUS

/** 与材料整理条目的状态用语保持一致。 */
const ITEM_STATUS = {
  confirmed: { label: '明确', tone: 'ok' },
  unconfirmed: { label: '待确认', tone: 'warn' },
  conflicting: { label: '有冲突', tone: 'danger' },
  example: { label: '示例', tone: 'info' },
} as const

export type HistoricalItemView = {
  id: string
  /** 冻结输入不可用或条目不在其中时为空串，界面只显示条目引用。 */
  text: string
  functionName: string
  sectionTitle: string
  status: HistoricalEnum | null
}
export type HistoricalRelationView = {
  id: string
  requirementId: string
  snapshotId: string
  name: string
  sprintName: string
  type: HistoricalEnum
  impacts: HistoricalImpactView[]
}
export type HistoricalQuestionView = { id: string; question: string; impact?: HistoricalImpactView }
export type HistoricalImpactView = {
  id: string
  effect: HistoricalEnum
  status: HistoricalEnum
  scope: RuleScope
  previousRule: string
  /** 规则取消（retired）时为 null。 */
  currentRule: string | null
  summary: string
  historical: HistoricalItemView[]
  current: HistoricalItemView[]
  questions: HistoricalQuestionView[]
  relation: HistoricalRelationView
}
export type HistoricalKnownRelation = { from: string; to: string; type: HistoricalEnum }
export type HistoricalRelationData = {
  relations: HistoricalRelationView[]
  impacts: HistoricalImpactView[]
  questions: HistoricalQuestionView[]
  knownRelations: HistoricalKnownRelation[]
}
export type RequirementSummary = { name: string; sprintName: string }

/** 未登记的枚举值保留原文，不猜测含义。 */
function meta(table: Record<string, EnumMeta>, value: unknown): HistoricalEnum {
  const key = toDisplayText(value)
  if (key && Object.prototype.hasOwnProperty.call(table, key)) {
    return { key, label: table[key].label, tone: table[key].tone }
  }
  return { key: key || '未知', label: key || '未知', tone: 'info' }
}

/** 规则效果的文案与色调；历史需求关联和历史用例核验共用。 */
export const ruleEffectMeta = (value: unknown) => meta(RULE_EFFECT, value)

/** 解析 JSON 文本；无法解析或不是对象时返回 null。 */
export function parseJsonRecord(text?: string | null) {
  try { return toRecord(JSON.parse(text || '')) } catch { return null }
}

export function textList(value: unknown) {
  return Array.isArray(value) ? value.map(toDisplayText).filter(Boolean) : []
}

function itemViews(ids: unknown, items: Map<string, Record<string, unknown>>): HistoricalItemView[] {
  return textList(ids).map((id) => {
    const item = items.get(id)
    return item
      ? {
          id,
          text: toDisplayText(item.text),
          functionName: toDisplayText(item.functionName),
          sectionTitle: toDisplayText(item.sectionTitle),
          status: meta(ITEM_STATUS, item.status),
        }
      : { id, text: '', functionName: '', sectionTitle: '', status: null }
  })
}

type FrozenItems = Pick<HistoricalRelationData, 'knownRelations'> & {
  current: Map<string, Record<string, unknown>>
  historical: Map<string, Map<string, Record<string, unknown>>>
}

/** 只读取本次冻结的历史关联输入；类型不符时视为不可用，界面退回为只显示条目引用。 */
function frozenItems(materialContent?: string | null): FrozenItems {
  const input = parseJsonRecord(materialContent)
  if (!input || toDisplayText(input.artifactType) !== 'historical_requirement_relation_input') {
    return { current: new Map(), historical: new Map(), knownRelations: [] }
  }
  const index = (material: Record<string, unknown> | null) =>
    new Map(toRecordArray(material?.items).map((item) => [toDisplayText(item.itemId), item]))
  return {
    current: index(toRecord(input.currentRequirement)),
    historical: new Map(toRecordArray(input.historicalRequirements).map((material) => [
      toDisplayText(material.requirementId),
      index(material),
    ])),
    knownRelations: toRecordArray(input.knownRelations).map((edge) => ({
      from: toDisplayText(edge.fromRequirementId),
      to: toDisplayText(edge.toRequirementId),
      type: meta(RELATION_TYPE, edge.relationType),
    })),
  }
}

/**
 * 历史需求关联产物的读取口径：界面只呈现产物与冻结输入里已有的字段，不补造结论。
 * 结构不符（例如旧内容）时返回 null，由宿主提示切换到 JSON。
 */
export function buildHistoricalRelationView(
  content: string,
  materialContent?: string | null,
  requirementOf: (id: string) => RequirementSummary = (id) => ({ name: id, sprintName: '' }),
): HistoricalRelationData | null {
  const output = parseJsonRecord(content)
  if (!output || !Array.isArray(output.relations) || !Array.isArray(output.openQuestions)) return null
  const frozen = frozenItems(materialContent)
  const impacts: HistoricalImpactView[] = []
  const relations = toRecordArray(output.relations).map((relation, relationIndex): HistoricalRelationView => {
    const requirementId = toDisplayText(relation.historicalRequirementId)
    const summary = requirementOf(requirementId)
    const row: HistoricalRelationView = {
      id: toDisplayText(relation.relationId) || `relation-${relationIndex + 1}`,
      requirementId,
      snapshotId: toDisplayText(relation.historicalMaterialSnapshotId),
      name: summary.name || requirementId,
      sprintName: summary.sprintName,
      type: meta(RELATION_TYPE, relation.relationType),
      impacts: [],
    }
    const empty = new Map<string, Record<string, unknown>>()
    row.impacts = toRecordArray(relation.impacts).map((impact, impactIndex): HistoricalImpactView => {
      const scope = toRecord(impact.scope)
      const view: HistoricalImpactView = {
        id: toDisplayText(impact.impactId) || `${row.id}-${impactIndex + 1}`,
        effect: meta(RULE_EFFECT, impact.ruleEffect),
        status: meta(REVIEW_STATUS, impact.reviewStatus),
        scope: {
          roles: textList(scope?.roles),
          states: textList(scope?.states),
          conditions: textList(scope?.conditions),
        },
        previousRule: toDisplayText(impact.previousRule),
        currentRule: toDisplayText(impact.currentRule) || null,
        summary: toDisplayText(impact.changeSummary),
        historical: itemViews(impact.historicalItemIds, frozen.historical.get(requirementId) ?? empty),
        current: itemViews(impact.currentItemIds, frozen.current),
        questions: [],
        relation: row,
      }
      impacts.push(view)
      return view
    })
    return row
  })
  // 产物没有问题编号，按输出顺序编号作为界面内的稳定标识。
  const questions = output.openQuestions.map((entry, index): HistoricalQuestionView => {
    const record = toRecord(entry)
    const impactId = toDisplayText(record?.impactId)
    const impact = impactId ? impacts.find((item) => item.id === impactId) : undefined
    return { id: `Q${index + 1}`, question: toDisplayText(record?.question), impact }
  })
  questions.forEach((question) => question.impact?.questions.push(question))
  return { relations, impacts, questions, knownRelations: frozen.knownRelations }
}

/** 侧栏「内容概况」：只统计产物里真实存在的对象。 */
export function historicalRelationCounts(content: string): Array<[value: number, unit: string]> | null {
  const view = buildHistoricalRelationView(content)
  return view
    ? [
        [view.relations.length, '条关联'],
        [view.impacts.length, '项规则影响'],
        [view.questions.length, '个待确认'],
      ]
    : null
}
