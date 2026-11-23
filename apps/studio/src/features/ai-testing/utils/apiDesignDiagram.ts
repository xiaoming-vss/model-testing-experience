import { toRecord, toRecordArray } from '@/shared/utils/value'

const SECTION_LABELS: Record<string, string> = {
  headers: '请求头',
  path_params: '路径参数',
  query: '查询参数',
  json: 'body',
  data: '表单',
}

const CATEGORY_LABELS: Record<string, string> = {
  positive: '正向',
  negative: '反向',
  boundary: '边界',
}

const REASON_META: Record<string, { label: string; description: string }> = {
  soft_cap: { label: '数量上限', description: '同类约束已达到生成数量上限' },
  low_value: { label: '价值较低', description: '场景价值较低，暂不生成用例' },
  duplicate: { label: '重复覆盖', description: '已有用例覆盖了相同约束' },
  not_verifiable: { label: '不可验证', description: '当前执行环境无法自动验证' },
}

const ASSERT_SOURCE_LABELS: Record<string, string> = {
  body_jsonpath: 'JSONPath',
  status_code: '状态码',
  header: '响应头',
  response_header: '响应头',
}

const COMPARATOR_LABELS: Record<string, string> = {
  exists: '存在',
  equals: '等于',
  notEquals: '不等于',
  greaterThan: '大于',
  lessThan: '小于',
  contains: '包含',
  matches: '匹配',
}

const PATCH_OP_LABELS: Record<string, string> = {
  add: '新增',
  remove: '删除',
  replace: '改为',
}

const UNCOVERED_KIND_LABELS: Record<string, string> = {
  constraint: '约束',
  required: '必传',
  type: '类型',
}

export type ApiDesignPatchOpView = {
  key: string
  op: string
  opLabel: string
  target: string
  valueLabel: string
}

export type ApiDesignAssertionView = {
  key: string
  source: string
  sourceLabel: string
  target: string
  comparator: string
  comparatorLabel: string
  expected: string
  hasExpected: boolean
}

export type ApiDesignCaseView = {
  key: string
  id: string
  title: string
  category: string
  categoryLabel: string
  priority: string
  intent: string
  statusClass: string
  basisLabel: string
  patchOps: ApiDesignPatchOpView[]
  assertions: ApiDesignAssertionView[]
}

export type ApiDesignUncoveredView = {
  key: string
  kindLabel: string
  fieldLabel: string
  constraint: string
  reason: string
  reasonLabel: string
  reasonDescription: string
}

export type ApiDesignInterfaceView = {
  key: string
  name: string
  label: string
  method: string
  path: string
  cases: ApiDesignCaseView[]
  categoryCounts: Record<string, number>
  uncovered: ApiDesignUncoveredView[]
}

export type ApiDesignDiagramData = {
  interfaces: ApiDesignInterfaceView[]
  totalCases: number
  totalUncovered: number
  categoryCounts: Record<string, number>
}

function text(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function pointerPath(pointer: string) {
  if (!pointer.startsWith('/')) return pointer
  return pointer
    .split('/')
    .slice(1)
    .map(token => token.replace(/~1/g, '/').replace(/~0/g, '~'))
    .reduce((result, token) => result + (/^\d+$/.test(token) ? `[${token}]` : `.${token}`), '')
}

function sectionLabel(section: string) {
  return SECTION_LABELS[section] ?? section
}

function targetLabel(section: string, pointer: string) {
  const label = sectionLabel(section)
  const path = pointerPath(pointer)
  if (!label) return path.replace(/^\./, '')
  return `${label}${path}`
}

function formatValue(value: unknown) {
  if (value === undefined) return ''
  if (typeof value === 'string') return JSON.stringify(value)
  if (value === null) return 'null'
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function normalizePatchOps(section: string, raw: unknown): ApiDesignPatchOpView[] {
  return toRecordArray(raw).flatMap((item, index) => {
    const record = toRecord(item)
    if (!record) return []
    const op = text(record.op)
    const target = targetLabel(section, text(record.path))
    const valueLabel = op === 'remove' ? '' : formatValue(record.value)
    return [{
      key: `${section}-${index}`,
      op,
      opLabel: PATCH_OP_LABELS[op] ?? (op || '变更'),
      target,
      valueLabel,
    }]
  })
}

function basisLabel(basis: Record<string, unknown>) {
  const kind = text(basis.kind)
  if (kind === 'positive' || !kind) return '正向全参数基线'
  const field = targetLabel(text(basis.section), text(basis.field))
  const constraint = text(basis.constraint)
  if (kind === 'required') return `${field} · 必传`
  if (kind === 'type') return `${field} · 类型 ${constraint}`
  return [field, constraint].filter(Boolean).join(' · ') || kind
}

function normalizeAssertion(raw: unknown, index: number, caseKey: string): ApiDesignAssertionView | null {
  const record = toRecord(raw)
  if (!record) return null
  const source = text(record.assertSource)
  const comparator = text(record.comparator)
  const expectedValue = record.expectedValue
  return {
    key: `${caseKey}-assert-${index}`,
    source,
    sourceLabel: ASSERT_SOURCE_LABELS[source] ?? (source || '断言'),
    target: text(record.targetExpr),
    comparator,
    comparatorLabel: COMPARATOR_LABELS[comparator] ?? comparator,
    expected: formatValue(expectedValue),
    hasExpected: expectedValue !== undefined && expectedValue !== null && expectedValue !== '',
  }
}

function normalizeCase(raw: unknown, index: number): ApiDesignCaseView | null {
  const record = toRecord(raw)
  if (!record) return null
  const title = text(record.title) || text(record.id) || `用例 ${index + 1}`
  const category = text(record.category) || 'positive'
  const key = text(record.id) || `case-${index + 1}`
  const patch = toRecord(record.patch) ?? {}
  const expected = toRecord(record.expected) ?? {}
  const basis = toRecord(record.basis) ?? {}
  return {
    key,
    id: text(record.id),
    title,
    category,
    categoryLabel: CATEGORY_LABELS[category] ?? category,
    priority: text(record.priority),
    intent: text(record.intent),
    statusClass: text(expected.statusClass),
    basisLabel: basisLabel(basis),
    patchOps: Object.entries(patch).flatMap(([section, value]) => normalizePatchOps(section, value)),
    assertions: toRecordArray(expected.assertions).flatMap((item, assertionIndex) => {
      const view = normalizeAssertion(item, assertionIndex, key)
      return view ? [view] : []
    }),
  }
}

function normalizeUncovered(raw: unknown, index: number): ApiDesignUncoveredView | null {
  const record = toRecord(raw)
  if (!record) return null
  const reason = text(record.reason)
  const reasonMeta = REASON_META[reason] ?? { label: reason || '未说明', description: '' }
  return {
    key: `uncovered-${index + 1}`,
    kindLabel: UNCOVERED_KIND_LABELS[text(record.kind)] ?? (text(record.kind) || '约束'),
    fieldLabel: targetLabel(text(record.section), text(record.field)),
    constraint: text(record.constraint),
    reason,
    reasonLabel: reasonMeta.label,
    reasonDescription: reasonMeta.description,
  }
}

export function normalizeApiDesign(content?: string): ApiDesignDiagramData | null {
  if (!content?.trim()) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(content)
  } catch {
    return null
  }
  const root = toRecord(parsed)
  const interfaces = toRecord(root?.interfaces)
  if (!interfaces) return null

  const categoryCounts: Record<string, number> = { positive: 0, negative: 0, boundary: 0 }
  const views = Object.entries(interfaces).map(([name, value], interfaceIndex): ApiDesignInterfaceView => {
    const record = toRecord(value) ?? {}
    const interfaceCategoryCounts: Record<string, number> = { positive: 0, negative: 0, boundary: 0 }
    const cases = toRecordArray(record.cases).flatMap((item, index) => {
      const view = normalizeCase(item, index)
      if (view) {
        categoryCounts[view.category] = (categoryCounts[view.category] ?? 0) + 1
        interfaceCategoryCounts[view.category] = (interfaceCategoryCounts[view.category] ?? 0) + 1
      }
      return view ? [view] : []
    })
    return {
      key: `${name}-${interfaceIndex}`,
      name,
      label: name,
      method: text(record.method).toUpperCase() || 'API',
      path: text(record.path) || '-',
      cases,
      categoryCounts: interfaceCategoryCounts,
      uncovered: toRecordArray(record.uncovered).flatMap((item, index) => {
        const view = normalizeUncovered(item, index)
        return view ? [view] : []
      }),
    }
  })
  if (views.length === 0) return null
  return {
    interfaces: views,
    totalCases: views.reduce((sum, item) => sum + item.cases.length, 0),
    totalUncovered: views.reduce((sum, item) => sum + item.uncovered.length, 0),
    categoryCounts,
  }
}
