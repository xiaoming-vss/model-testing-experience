import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from './functionalOutput'

export const SCOPE_CATEGORIES = [
  { key: 'testObjects', label: '测试对象', unit: '测试对象', hint: '识别需要关注的业务对象与操作', tone: 'blue' },
  { key: 'impactAreas', label: '影响范围', unit: '影响范围', hint: '从变更出发，梳理已知业务关联和影响', tone: 'purple' },
  { key: 'risks', label: '风险', unit: '风险', hint: '可能影响业务判断或测试覆盖的因素', tone: 'red' },
  { key: 'openQuestions', label: '待确认', unit: '待确认问题', hint: '材料未明确、需要进一步确认的事项', tone: 'amber' },
] as const

export type ScopeCategoryKey = (typeof SCOPE_CATEGORIES)[number]['key']
export type ScopeCategoryTone = (typeof SCOPE_CATEGORIES)[number]['tone']
export type ScopeStatusKey = 'confirmed' | 'inferred' | 'unconfirmed'
export type ScopeStatusTone = 'ok' | 'info' | 'warn'

export const SCOPE_STATUS: Record<ScopeStatusKey, { label: string; tone: ScopeStatusTone }> = {
  confirmed: { label: '明确', tone: 'ok' },
  inferred: { label: '推测', tone: 'info' },
  unconfirmed: { label: '待确认', tone: 'warn' },
}

export type ScopeEntryView = {
  id: string
  title: string
  type: string
  narrative: string
  status: ScopeStatusKey
  sourceBlockIds: string[]
  sourceQuestionIds: string[]
  relationIds: Partial<Record<ScopeCategoryKey, string[]>>
  group: string
}

export type ScopeCategoryView = {
  key: ScopeCategoryKey
  label: string
  unit: string
  hint: string
  tone: ScopeCategoryTone
  items: ScopeEntryView[]
  statusCounts: Record<ScopeStatusKey, number>
  groups: Array<{ label: string; items: ScopeEntryView[] }>
}

export type ScopeMaterialBlockView = {
  id: string
  sourceId: string
  sourceName: string
  sourceType: string
  locator: string
  kind: string
  content: Record<string, unknown>
}

export type TestScopeView = {
  categories: Record<ScopeCategoryKey, ScopeCategoryView>
  itemById: Record<ScopeCategoryKey, Map<string, ScopeEntryView>>
  blockById: Map<string, ScopeMaterialBlockView>
  sourceQuestionById: Map<string, string>
}

export type ScopeRelationRow = {
  label: string
  category: ScopeCategoryKey
  items: ScopeEntryView[]
}

const RELATION_FIELDS: Record<ScopeCategoryKey, Array<{ label: string; target: ScopeCategoryKey }>> = {
  testObjects: [
    { label: '影响范围', target: 'impactAreas' },
    { label: '风险', target: 'risks' },
    { label: '待确认', target: 'openQuestions' },
  ],
  impactAreas: [
    { label: '测试对象', target: 'testObjects' },
    { label: '风险', target: 'risks' },
    { label: '待确认', target: 'openQuestions' },
  ],
  risks: [
    { label: '测试对象', target: 'testObjects' },
    { label: '影响范围', target: 'impactAreas' },
    { label: '待确认', target: 'openQuestions' },
  ],
  openQuestions: [
    { label: '测试对象', target: 'testObjects' },
    { label: '影响范围', target: 'impactAreas' },
    { label: '风险', target: 'risks' },
  ],
}

const TEST_OBJECT_GROUP_ORDER = ['页面与操作', '数据与产物', '流程与异常', '存量与配置', '其他'] as const

const TEST_OBJECT_GROUP_RULES: Array<{ label: (typeof TEST_OBJECT_GROUP_ORDER)[number]; pattern: RegExp }> = [
  { label: '存量与配置', pattern: /存量|历史|迁移|配置|开关|角色|权限|人员/ },
  { label: '页面与操作', pattern: /页面|入口|用户操作|交互|界面/ },
  { label: '流程与异常', pattern: /流程|阶段|状态|异常|恢复|前置|规则|校验|阻断|服务/ },
  { label: '数据与产物', pattern: /数据|产物|对象|记录|文件|报告|文本|字段|参数|边界/ },
]

function refIds(record: Record<string, unknown>, field: string) {
  return Array.isArray(record[field]) ? record[field].map(toDisplayText).filter(Boolean) : []
}

function statusOf(record: Record<string, unknown>): ScopeStatusKey {
  const value = toDisplayText(record.basisStatus)
  return value === 'confirmed' || value === 'inferred' || value === 'unconfirmed' ? value : 'unconfirmed'
}

export function testObjectGroup(type: string) {
  return TEST_OBJECT_GROUP_RULES.find((rule) => rule.pattern.test(type))?.label ?? '其他'
}

function riskNarrative(status: ScopeStatusKey) {
  if (status === 'confirmed') return '材料直接描述了该风险，生成用例时需要覆盖对应触发条件和结果。'
  if (status === 'inferred') return '该风险由材料中的关联信息推断，需人工确认后再作为事实使用。'
  return '材料未明确该风险，保留为待确认项。'
}

function entryTitle(category: ScopeCategoryKey, record: Record<string, unknown>) {
  const value = category === 'testObjects'
    ? record.name
    : category === 'impactAreas'
      ? record.area
      : category === 'risks'
        ? record.description
        : record.question
  return toDisplayText(value) || '未命名'
}

function entryNarrative(category: ScopeCategoryKey, record: Record<string, unknown>, status: ScopeStatusKey) {
  if (category === 'testObjects') return toDisplayText(record.description) || '未记录描述'
  if (category === 'impactAreas') return toDisplayText(record.impact) || '未记录影响'
  if (category === 'risks') return riskNarrative(status)
  return '材料未对这个问题给出明确结论，建议在生成用例前补充确认。'
}

function forwardRelationIds(category: ScopeCategoryKey, record: Record<string, unknown>) {
  const relationIds: Partial<Record<ScopeCategoryKey, string[]>> = {}
  if (category === 'impactAreas') relationIds.testObjects = refIds(record, 'testObjectIds')
  if (category === 'risks') {
    relationIds.testObjects = refIds(record, 'testObjectIds')
    relationIds.impactAreas = refIds(record, 'impactAreaIds')
  }
  if (category === 'openQuestions') {
    relationIds.testObjects = refIds(record, 'testObjectIds')
    relationIds.impactAreas = refIds(record, 'impactAreaIds')
    relationIds.risks = refIds(record, 'riskIds')
  }
  return relationIds
}

function addRelation(entry: ScopeEntryView | undefined, target: ScopeCategoryKey, id: string) {
  if (!entry) return
  const current = entry.relationIds[target] || []
  if (!current.includes(id)) current.push(id)
  entry.relationIds[target] = current
}

function statusCounts(items: ScopeEntryView[]) {
  const counts: Record<ScopeStatusKey, number> = { confirmed: 0, inferred: 0, unconfirmed: 0 }
  items.forEach((item) => { counts[item.status] += 1 })
  return counts
}

/**
 * 统一测试范围产物的读取口径：
 * - 范围分析只携带对象/影响/风险/待确认及材料引用，界面不补造不存在的字段；
 * - 测试对象按 type 关键词归入四个浏览分组，type 原文仍保留在详情；
 * - 反向关联（例如某对象被哪些风险引用）由程序从正向引用推导。
 */
export function buildTestScopeView(analysis: Record<string, unknown>, materialContent?: string): TestScopeView {
  const material = (() => {
    try { return toRecord(JSON.parse(materialContent || '')) } catch { return null }
  })()
  const materialSources = new Map(toRecordArray(material?.sources).map((source) => [toDisplayText(source.id), source]))
  const materialQuestions = new Map(toRecordArray(material?.questions).map((question) => [toDisplayText(question.id), toDisplayText(question.question)]))
  const blockById = new Map<string, ScopeMaterialBlockView>()
  toRecordArray(material?.materialBlocks).forEach((block, index) => {
    const sourceId = toDisplayText(block.sourceId)
    const source = materialSources.get(sourceId)
    const id = toDisplayText(block.id) || `材料块 ${index + 1}`
    blockById.set(id, {
      id,
      sourceId,
      sourceName: toDisplayText(source?.name) || '材料原文',
      sourceType: toDisplayText(source?.type),
      locator: toDisplayText(block.locator) || `材料块 ${index + 1}`,
      kind: toDisplayText(block.kind) || 'paragraph',
      content: toRecord(block.content) ?? {},
    })
  })

  const itemById: Record<ScopeCategoryKey, Map<string, ScopeEntryView>> = {
    testObjects: new Map(),
    impactAreas: new Map(),
    risks: new Map(),
    openQuestions: new Map(),
  }

  const itemsByCategory = {} as Record<ScopeCategoryKey, ScopeEntryView[]>
  SCOPE_CATEGORIES.forEach((category) => {
    const records = toRecordArray(analysis[category.key])
    const items = records.map((record, index): ScopeEntryView => {
      const id = toDisplayText(record.id) || String(index + 1)
      const status = category.key === 'openQuestions' ? 'unconfirmed' : statusOf(record)
      const type = category.key === 'testObjects' ? toDisplayText(record.type) : ''
      return {
        id,
        title: entryTitle(category.key, record),
        type,
        narrative: entryNarrative(category.key, record, status),
        status,
        sourceBlockIds: refIds(record, 'sourceBlockIds'),
        sourceQuestionIds: category.key === 'openQuestions' ? refIds(record, 'sourceQuestionIds') : [],
        relationIds: forwardRelationIds(category.key, record),
        group: category.key === 'testObjects' ? testObjectGroup(type) : '',
      }
    })
    itemsByCategory[category.key] = items
    items.forEach((item) => itemById[category.key].set(item.id, item))
  })

  itemsByCategory.impactAreas.forEach((impact) => {
    (impact.relationIds.testObjects || []).forEach((id) => addRelation(itemById.testObjects.get(id), 'impactAreas', impact.id));
  })
  itemsByCategory.risks.forEach((risk) => {
    (risk.relationIds.testObjects || []).forEach((id) => addRelation(itemById.testObjects.get(id), 'risks', risk.id));
    (risk.relationIds.impactAreas || []).forEach((id) => addRelation(itemById.impactAreas.get(id), 'risks', risk.id));
  })
  itemsByCategory.openQuestions.forEach((question) => {
    (question.relationIds.testObjects || []).forEach((id) => addRelation(itemById.testObjects.get(id), 'openQuestions', question.id));
    (question.relationIds.impactAreas || []).forEach((id) => addRelation(itemById.impactAreas.get(id), 'openQuestions', question.id));
    (question.relationIds.risks || []).forEach((id) => addRelation(itemById.risks.get(id), 'openQuestions', question.id));
  })

  const categories = {} as Record<ScopeCategoryKey, ScopeCategoryView>
  SCOPE_CATEGORIES.forEach((category) => {
    const items = itemsByCategory[category.key]
    const groups = category.key === 'testObjects'
      ? TEST_OBJECT_GROUP_ORDER
        .map((label) => ({ label, items: items.filter((item) => item.group === label) }))
        .filter((group) => group.items.length > 0)
      : []
    categories[category.key] = {
      key: category.key,
      label: category.label,
      unit: category.unit,
      hint: category.hint,
      tone: category.tone,
      items,
      statusCounts: statusCounts(items),
      groups,
    }
  })

  return { categories, itemById, blockById, sourceQuestionById: materialQuestions }
}

export function relationRows(entry: ScopeEntryView, category: ScopeCategoryKey, view: TestScopeView): ScopeRelationRow[] {
  return RELATION_FIELDS[category].flatMap((relation) => {
    const targetItems = (entry.relationIds[relation.target] || [])
      .map((id) => view.itemById[relation.target].get(id))
      .filter((item): item is ScopeEntryView => Boolean(item))
    return targetItems.length ? [{ label: relation.label, category: relation.target, items: targetItems }] : []
  })
}

export function questionRelatedCounts(category: ScopeCategoryView) {
  const objects = new Set<string>()
  const impacts = new Set<string>()
  const risks = new Set<string>()
  category.items.forEach((question) => {
    (question.relationIds.testObjects || []).forEach((id) => objects.add(id));
    (question.relationIds.impactAreas || []).forEach((id) => impacts.add(id));
    (question.relationIds.risks || []).forEach((id) => risks.add(id));
  })
  return { objects: objects.size, impacts: impacts.size, risks: risks.size }
}
