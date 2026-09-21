import { formatStructuredContent } from '@/shared/utils/value'

type GeneratedCaseImportStats = {
  moduleCount: number
  caseCount: number
  moduleNames: string[]
}

function parseJsonLikeContent(value?: unknown) {
  if (value === undefined || value === null || value === '') return undefined
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return undefined
  }
}

export function getOutputRepairProgress(summary: unknown): string | null {
  const parsed = parseJsonLikeContent(summary)
  const progress = parsed && typeof parsed === 'object' ? parsed.outputValidation : undefined
  if (!progress || progress.status !== 'repairing' || !Number.isInteger(progress.repairAttempt) || progress.repairAttempt < 1) return null
  const stage = { requirement_analysis: '需求分析', case_names: '测试点', detailed_cases: '详细用例', relation_analysis: '图谱分析' }[progress.stage as 'requirement_analysis' | 'case_names' | 'detailed_cases' | 'relation_analysis']
  if (!stage) return null
  return `${stage}${typeof progress.module === 'string' && progress.module ? ` / ${progress.module}` : ''}：输出校验未通过，正在进行第 ${progress.repairAttempt}/2 次自动修复`
}

export function getGeneratedCaseImportStats(content?: unknown): GeneratedCaseImportStats {
  const parsed = parseJsonLikeContent(content)
  const cases = Array.isArray(parsed)
    ? parsed
    : parsed && typeof parsed === 'object' && Array.isArray((parsed as Record<string, unknown>).cases)
      ? (parsed as Record<string, unknown>).cases as unknown[]
      : []
  const moduleNames = new Set<string>()

  cases.forEach((item) => {
    if (!item || typeof item !== 'object') {
      moduleNames.add('未分组')
      return
    }
    const moduleName = toDisplayText((item as Record<string, unknown>).case_module) || '未分组'
    moduleNames.add(moduleName)
  })

  return {
    moduleCount: moduleNames.size,
    caseCount: cases.length,
    moduleNames: [...moduleNames],
  }
}

export function getConfigStageFieldContent(configJson?: unknown, fieldKey?: string) {
  if (!fieldKey) return ''
  const parsed = parseJsonLikeContent(configJson)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return ''
  const record = parsed as Record<string, unknown>
  const directFieldContent = record[fieldKey]
  if (directFieldContent !== undefined && directFieldContent !== null && directFieldContent !== '') {
    return formatStructuredContent(directFieldContent)
  }

  if (isDirectStageConfigContent(record, fieldKey)) {
    return formatStructuredContent(record)
  }

  return ''
}

function isDirectStageConfigContent(record: Record<string, unknown>, fieldKey: string) {
  if (fieldKey === 'caseNames') {
    return Array.isArray(record.categories)
  }

  if (fieldKey === 'requirementAnalysis') {
    return Boolean(
      record.Platform_core_functions ||
      record.Target_understanding ||
      record.Risk_point_prediction ||
      record.function_flow ||
      record.Scene_Design ||
      record.functionalOverview ||
      record.businessRules ||
      record.scenarioFactors ||
      record.scenarioBreakdown ||
      record.openQuestions,
    )
  }

  return false
}

export function isJsonText(content?: string) {
  if (!content?.trim()) return false
  try {
    JSON.parse(content)
    return true
  } catch {
    return false
  }
}

export function toDisplayText(value: unknown) {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const record = value as Record<string, unknown>
    const namedValue = record.case_name ?? record.test_point ?? record.name ?? record.title
    if (namedValue !== undefined && namedValue !== null && namedValue !== '') return toDisplayText(namedValue)
  }
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function toTextList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(toDisplayText).filter(Boolean)
  }
  const text = toDisplayText(value)
  return text ? [text] : []
}

export function toCaseNamePointList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(toDisplayText).filter(Boolean)
  }
  const text = toDisplayText(value)
  return text ? [text] : []
}

export type RequirementAnalysisSection = {
  functionalOverview?: unknown
  businessRules?: unknown
  scenarioFactors?: unknown
  scenarioBreakdown?: unknown
  openQuestions?: unknown
  Platform_core_functions?: unknown
  Target_understanding?: unknown
  Risk_point_prediction?: unknown
  function_flow?: unknown
  Scene_Design?: unknown
}

export function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

export function toRecordArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
}

export function formatTextList(value: unknown) {
  return toTextList(value).join('\n')
}

export function formatRoleConcerns(value: unknown) {
  return toRecordArray(value)
    .map((item) => {
      const role = toDisplayText(item.role)
      const concern = toDisplayText(item.concern)
      if (role && concern) return `${role}：${concern}`
      return role || concern || toDisplayText(item)
    })
    .filter(Boolean)
    .join('\n')
}

export type GeneratedTestCase = {
  moduleName: string
  displayName: string
  tagFields: Array<{ key: string; label: string; value: string }>
  detailFields: Array<{ key: string; label: string; value: string }>
}

type GeneratedCaseModuleGroup = {
  moduleName: string
  cases: GeneratedTestCase[]
}

const MODULE_FIELD_CANDIDATES = ['case_module', 'module', 'module_name', 'moduleName', 'group', 'category']

const NAME_FIELD_CANDIDATES = ['Case Title', 'case_title', 'case_name', 'name', 'title', 'caseName', 'test_point', 'testPoint', 'scenario', 'description']

const TAG_FIELD_CANDIDATES = ['case_id', 'caseId', 'priority', 'case_type', 'caseType', 'type', 'level', 'severity']

export const CASE_ID_FIELDS = ['case_id', 'caseId']

export function formatCaseIdTag(value: string) {
  return value.length > 8 ? `${value.slice(0, 8)}…` : value
}

const FIELD_LABEL_MAP: Record<string, string> = {
  case_id: '用例编号',
  caseId: '用例编号',
  case_name: '用例名称',
  case_title: '用例名称',
  'Case Title': '用例名称',
  name: '用例名称',
  title: '用例名称',
  caseName: '用例名称',
  test_point: '测试点',
  testPoint: '测试点',
  scenario: '场景',
  description: '描述',
  preconditions: '前置条件',
  precondition: '前置条件',
  preCondition: '前置条件',
  steps: '测试步骤',
  test_steps: '测试步骤',
  testSteps: '测试步骤',
  operation: '操作步骤',
  expected_results: '预期结果',
  expectedResult: '预期结果',
  expectedResults: '预期结果',
  expected_result: '预期结果',
  priority: '优先级',
  case_type: '用例类型',
  caseType: '用例类型',
  type: '类型',
  level: '级别',
  severity: '严重程度',
  case_module: '模块',
  module: '模块',
  module_name: '模块',
  moduleName: '模块',
  group: '分组',
  category: '分类',
  order: '序号',
  orderNo: '序号',
  remark: '备注',
  note: '备注',
}

function pickFirstField(record: Record<string, unknown>, candidates: string[]): string {
  for (const key of candidates) {
    const val = toDisplayText(record[key])
    if (val) return val
  }
  return ''
}

function isTagField(key: string, value: string): boolean {
  if (TAG_FIELD_CANDIDATES.includes(key)) return true
  if (value.length <= 12 && /^P[1-4]$/.test(value)) return true
  if (value.length <= 8 && /^\d+$/.test(value)) return true
  return false
}

function formatFieldLabel(key: string): string {
  if (FIELD_LABEL_MAP[key]) return FIELD_LABEL_MAP[key]
  return key.replace(/[_-]/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function parseGeneratedCases(content?: string): GeneratedCaseModuleGroup[] {
  if (!content?.trim()) return []
  try {
    const parsed = JSON.parse(content)
    const rawCases: unknown[] = Array.isArray(parsed)
      ? parsed
      : parsed && typeof parsed === 'object' && Array.isArray((parsed as Record<string, unknown>).cases)
        ? (parsed as Record<string, unknown>).cases as unknown[]
        : []
    if (rawCases.length === 0) return []

    const moduleMap = new Map<string, GeneratedTestCase[]>()
    rawCases.forEach((item) => {
      if (!item || typeof item !== 'object') {
        const group = moduleMap.get('未分组') ?? []
        group.push({ moduleName: '未分组', displayName: toDisplayText(item) || '未命名用例', tagFields: [], detailFields: [] })
        moduleMap.set('未分组', group)
        return
      }
      const record = item as Record<string, unknown>
      const moduleName = pickFirstField(record, MODULE_FIELD_CANDIDATES) || '未分组'
      const displayName = pickFirstField(record, NAME_FIELD_CANDIDATES) || '未命名用例'

      const tagFields: Array<{ key: string; label: string; value: string }> = []
      const detailFields: Array<{ key: string; label: string; value: string }> = []
      const nameKey = NAME_FIELD_CANDIDATES.find((k) => toDisplayText(record[k]))
      const moduleKey = MODULE_FIELD_CANDIDATES.find((k) => toDisplayText(record[k]))

      Object.entries(record).forEach(([key, rawValue]) => {
        if (key === nameKey || key === moduleKey) return
        const value = toDisplayText(rawValue)
        if (!value) return
        if (isTagField(key, value)) {
          tagFields.push({ key, label: formatFieldLabel(key), value })
        } else {
          detailFields.push({ key, label: formatFieldLabel(key), value })
        }
      })

      const testCase: GeneratedTestCase = { moduleName, displayName, tagFields, detailFields }
      const group = moduleMap.get(moduleName) ?? []
      group.push(testCase)
      moduleMap.set(moduleName, group)
    })

    return [...moduleMap.entries()].map(([moduleName, cases]) => ({ moduleName, cases }))
  } catch {
    return []
  }
}

export function parseRequirementAnalysisContent(content: string): RequirementAnalysisSection | null {
  if (!content.trim()) return null

  try {
    const parsed = JSON.parse(content)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed as RequirementAnalysisSection
  } catch {
    return null
  }
}
