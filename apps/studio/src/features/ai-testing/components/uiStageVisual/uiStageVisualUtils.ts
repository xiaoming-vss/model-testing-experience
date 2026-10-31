import { parseUiCaseCandidate, type UiCandidateStepView } from '../../utils/uiCaseCandidate'

export type SurfacePage = {
  pageId: string
  title: string
  route: string
}

export type SurfaceCondition = {
  description: string
  sourceRef?: string
}

export type SurfaceLocator = {
  locatorType?: string
  locatorValue?: string
  stability?: string
  confirmed?: boolean
  reason?: string
  evidenceType?: string
}

export type SurfaceControl = {
  controlId: string
  pageId: string
  name: string
  type: string
  typeLabel: string
  visibleText: string
  sourceRef: string
  containerId: string
  conditions: SurfaceCondition[]
  locators: SurfaceLocator[]
  uniqueness: string
  extra: Record<string, unknown>
}

export type SurfaceUnknown = {
  topic: string
  reason: string
  sourceRef: string
  affectedIds: string[]
}

export type SurfaceInteraction = {
  interactionId: string
  controlId: string
  description: string
  effect: string
  targetId: string
}

export type SurfaceData = {
  pages: SurfacePage[]
  controls: SurfaceControl[]
  unknowns: SurfaceUnknown[]
  interactions: SurfaceInteraction[]
}

export type DesignAction = {
  actionId: string
  operation: string
  target: string
  value: string
  status: string
  reason: string
  sourceQuote: string
}

export type DesignExpectation = {
  expectationId: string
  assertion: string
  target: string
  value: string
  status: string
  reason: string
  sourceQuote: string
}

export type DesignStep = {
  sourceStepNo: number
  sourceAction: string
  actions: DesignAction[]
  expectations: DesignExpectation[]
}

export type DesignCase = {
  caseId: string
  name: string
  goal: string
  sourceTitle: string
  coverage: string
  preconditions: string[]
  limitations: string[]
  steps: DesignStep[]
}

export type DesignData = {
  cases: DesignCase[]
  assertions: string[]
  operations: string[]
}

export type YamlMissing = {
  fields: string[]
  operation: string
  target: string
  value: string
  reason: string
}

export type YamlStep = {
  orderNo: number
  name: string
  keyword: string
  locatorType: string
  locatorValue: string
  operationValue: string
  missing: YamlMissing[]
}

export type YamlCase = {
  name: string
  enabled: boolean
  steps: YamlStep[]
  missingSteps: number
  completionIssues: string[]
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

export function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : []
}

export function asString(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

export function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return fallback
}

function jsonArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

export function parseSurface(raw: string): SurfaceData | null {
  let parsed: Record<string, unknown> | null
  try {
    parsed = asRecord(JSON.parse(raw))
  } catch {
    return null
  }
  if (!parsed) return null

  const pages = asArray<Record<string, unknown>>(parsed.pages).flatMap((page) => {
    const pageId = asString(page.pageId)
    if (!pageId) return []
    return [{
      pageId,
      title: asString(page.title) || pageId,
      route: asString(page.route) || '—',
    }]
  })

  const controls = asArray<Record<string, unknown>>(parsed.controls).flatMap((control, index) => {
    const controlId = asString(control.controlId)
    if (!controlId) return []
    const conditions = jsonArray(control.conditions).flatMap((condition) => {
      const record = asRecord(condition)
      const description = asString(record?.description)
      return description ? [{ description, sourceRef: asString(record?.sourceRef) || undefined }] : []
    })
    const locators = jsonArray(control.locatorCandidates).flatMap((candidate) => {
      const record = asRecord(candidate)
      const locatorValue = asString(record?.locatorValue)
      if (!record || !locatorValue) return []
      return [{
        locatorType: asString(record.locatorType) || undefined,
        locatorValue,
        stability: asString(record.stability) || undefined,
        confirmed: record.confirmed === true,
        reason: asString(record.reason) || undefined,
        evidenceType: asString(record.evidenceType) || undefined,
      }]
    })
    return [{
      controlId,
      pageId: asString(control.pageId),
      name: asString(control.semanticName) || asString(control.visibleText) || controlId || `控件 ${index + 1}`,
      type: asString(control.controlType) || asString(control.role) || 'unknown',
      typeLabel: controlTypeLabel(asString(control.controlType) || asString(control.role)),
      visibleText: asString(control.visibleText),
      sourceRef: asString(control.sourceRef),
      containerId: asString(control.containerId),
      conditions,
      locators,
      uniqueness: asString(control.uniqueness) || 'unknown',
      extra: asRecord(control.extra) ?? {},
    }]
  })

  const unknowns = asArray<Record<string, unknown>>(parsed.unknowns).flatMap((unknown) => {
    const topic = asString(unknown.topic)
    if (!topic) return []
    return [{
      topic,
      reason: asString(unknown.reason),
      sourceRef: asString(unknown.sourceRef),
      affectedIds: asArray<unknown>(unknown.affectedIds).map(asString).filter(Boolean),
    }]
  })

  const interactions = asArray<Record<string, unknown>>(parsed.interactions).flatMap((interaction) => {
    const interactionId = asString(interaction.interactionId)
    if (!interactionId) return []
    return [{
      interactionId,
      controlId: asString(interaction.controlId),
      description: asString(interaction.description),
      effect: asString(interaction.effect),
      targetId: asString(interaction.targetId),
    }]
  })

  return { pages, controls, unknowns, interactions }
}

export function controlTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    button: '按钮',
    input: '输入框',
    textarea: '多行文本',
    select: '下拉',
    columnHeader: '表头',
    tableCell: '单元格',
    tab: '页签',
    pagination: '分页',
    checkbox: '勾选框',
    dateRange: '日期范围',
    readOnlyText: '只读文本',
    menuItem: '菜单项',
  }
  return labels[type] ?? type ?? '控件'
}

export function parseDesign(raw: string): DesignData | null {
  let parsed: Record<string, unknown> | null
  try {
    parsed = asRecord(JSON.parse(raw))
  } catch {
    return null
  }
  if (!parsed) return null

  const cases = asArray<Record<string, unknown>>(parsed.cases).flatMap((candidate, index) => {
    const caseId = asString(candidate.caseId) || `case-${index + 1}`
    const steps = asArray<Record<string, unknown>>(candidate.steps).map((step, stepIndex) => ({
      sourceStepNo: asNumber(step.sourceStepNo, stepIndex + 1),
      sourceAction: asString(step.sourceAction),
      actions: asArray<Record<string, unknown>>(step.actions).map((action, actionIndex) => ({
        actionId: asString(action.actionId) || `A${stepIndex + 1}-${actionIndex + 1}`,
        operation: asString(action.operation) || '操作',
        target: asString(action.target),
        value: asString(action.value),
        status: asString(action.status) || 'included',
        reason: asString(action.reason),
        sourceQuote: asString(action.sourceQuote),
      })),
      expectations: asArray<Record<string, unknown>>(step.expectations).map((expectation, expectationIndex) => ({
        expectationId: asString(expectation.expectationId) || `E${stepIndex + 1}-${expectationIndex + 1}`,
        assertion: asString(expectation.assertion) || '断言',
        target: asString(expectation.target),
        value: asString(expectation.value),
        status: asString(expectation.status) || 'included',
        reason: asString(expectation.reason),
        sourceQuote: asString(expectation.sourceQuote),
      })),
    }))
    return [{
      caseId,
      name: asString(candidate.name) || `UI 场景 ${index + 1}`,
      goal: asString(candidate.goal),
      sourceTitle: asString(candidate.sourceTitle),
      coverage: asString(candidate.coverage) || 'partial',
      preconditions: asArray<unknown>(candidate.preconditions).map(asString).filter(Boolean),
      limitations: asArray<unknown>(candidate.limitations).map(asString).filter(Boolean),
      steps,
    }]
  })

  const capabilities = asRecord(parsed.capabilities)
  return {
    cases,
    assertions: asArray<unknown>(capabilities?.assertions).map(asString).filter(Boolean),
    operations: asArray<unknown>(capabilities?.operations).map(asString).filter(Boolean),
  }
}

function normalizeMissing(value: unknown): YamlMissing[] {
  return asArray<Record<string, unknown>>(value).flatMap((entry) => {
    const reason = asString(entry.reason)
    const fields = asArray<unknown>(entry.fields).map(asString).filter(Boolean)
    if (!reason && fields.length === 0) return []
    return [{
      fields,
      operation: asString(entry.operation),
      target: asString(entry.target),
      value: asString(entry.value),
      reason,
    }]
  })
}

function yamlStep(step: UiCandidateStepView): YamlStep {
  const missing = normalizeMissing(step.extraFields.missingFields)
  const bindings = asRecord(step.extraFields.dataBindings)
  const unresolved = bindings ? Object.keys(bindings).filter(field => step[field as keyof UiCandidateStepView] == null) : []
  if (unresolved.length) missing.push({ fields: unresolved, operation: '补充关联数据', target: '关联测试数据', value: '', reason: '关联数据尚未提供，请核对 YAML 中的 dataRequirements 与 dataBindings。' })
  return {
    orderNo: asNumber(step.orderNo),
    name: asString(step.stepName) || '未命名步骤',
    keyword: asString(step.keyword) || 'step',
    locatorType: asString(step.locatorType),
    locatorValue: asString(step.locatorValue),
    operationValue: asString(step.operationValue),
    missing,
  }
}

export function parseYaml(raw: string): { cases: YamlCase[]; error?: string } {
  const parsed = parseUiCaseCandidate(raw)
  if (parsed.error) return { cases: [], error: parsed.error }
  const cases = parsed.cases.map((candidate, index) => {
    const steps = candidate.steps.map(yamlStep)
    const requirements = asArray<Record<string, unknown>>(candidate.extraFields.dataRequirements)
    const completionIssues = requirements.filter(item => {
      const fields = asRecord(item.fields) ?? {}
      return Object.values(fields).some(field => asRecord(field)?.value == null)
        || (asArray(item.conditions).length > 0 && item.confirmed !== true)
    }).map(item => `待补数据或准备条件：${asString(item.title)}`)
    completionIssues.push(...asArray<Record<string, unknown>>(candidate.extraFields.designConflicts)
      .map(item => `设计冲突：${asString(item.reason)}`))
    return {
      name: candidate.name || `UI 用例 ${index + 1}`,
      enabled: candidate.enabled ?? true,
      steps,
      missingSteps: steps.filter(step => step.missing.length > 0).length,
      completionIssues,
    }
  })
  return { cases }
}

export function isExcludedStatus(status: string): boolean {
  return status === 'excluded'
}

export function stepHasExcluded(step: DesignStep): boolean {
  return step.actions.some(action => isExcludedStatus(action.status))
    || step.expectations.some(expectation => isExcludedStatus(expectation.status))
}
