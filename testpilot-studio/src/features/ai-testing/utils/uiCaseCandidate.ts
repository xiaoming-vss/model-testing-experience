import { parse } from 'yaml'

const caseFieldNames = new Set(['name', 'enabled', 'orderNo', 'stepsJson'])
export const uiCaseStepFieldNames = [
  'orderNo',
  'stepName',
  'keyword',
  'locatorType',
  'locatorValue',
  'operationValue',
  'continueOnFailure',
  'enabled',
] as const

const stepFieldNames = new Set<string>(uiCaseStepFieldNames)

export type UiCandidateStepView = Record<string, unknown> & {
  extraFields: Record<string, unknown>
}

export type UiCandidateCaseView = {
  name?: string
  enabled?: boolean
  orderNo?: number
  steps: UiCandidateStepView[]
  extraFields: Record<string, unknown>
}

export type UiCandidateParseResult = {
  rawYaml: string
  cases: UiCandidateCaseView[]
  error?: string
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function extraFields(record: Record<string, unknown>, knownFields: Set<string>) {
  return Object.fromEntries(Object.entries(record).filter(([key]) => !knownFields.has(key)))
}

function candidateCaseItems(value: unknown): unknown[] {
  if (Array.isArray(value)) return value
  const root = asRecord(value)
  if (!root) return []

  // UI 用例导入的标准结构允许最外层直接是一条用例对象。
  if (Object.keys(root).some((key) => caseFieldNames.has(key))) return [root]

  // 兼容生成任务历史上使用过的包装结构。
  for (const key of ['cases', 'uiCases', 'items']) {
    if (Array.isArray(root[key])) return root[key]
  }
  return []
}

function candidateSteps(value: unknown): unknown[] {
  if (Array.isArray(value)) return value
  if (typeof value !== 'string' || !value.trim()) return []
  try {
    const parsedSteps = parse(value)
    return Array.isArray(parsedSteps) ? parsedSteps : []
  } catch {
    return []
  }
}

export function parseUiCaseCandidate(rawYaml: string): UiCandidateParseResult {
  try {
    const rawCases = candidateCaseItems(parse(rawYaml))
    const cases = rawCases.flatMap((candidate): UiCandidateCaseView[] => {
      const caseRecord = asRecord(candidate)
      if (!caseRecord) return []
      const rawSteps = candidateSteps(caseRecord.stepsJson)
      const steps = rawSteps.flatMap((step): UiCandidateStepView[] => {
        const stepRecord = asRecord(step)
        if (!stepRecord) return []
        return [{ ...stepRecord, extraFields: extraFields(stepRecord, stepFieldNames) }]
      })
      return [{
        name: typeof caseRecord.name === 'string' ? caseRecord.name : undefined,
        enabled: typeof caseRecord.enabled === 'boolean' ? caseRecord.enabled : undefined,
        orderNo: typeof caseRecord.orderNo === 'number' ? caseRecord.orderNo : undefined,
        steps,
        extraFields: extraFields(caseRecord, caseFieldNames),
      }]
    })
    return { rawYaml, cases }
  } catch (error) {
    return {
      rawYaml,
      cases: [],
      error: error instanceof Error ? error.message : 'YAML 解析失败',
    }
  }
}
