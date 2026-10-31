import { parse } from 'yaml'
import { toRecord, toRecordArray } from '@/shared/utils/value'

export type ApiConfigRule = {
  name: string
  detail: string
}

export type ApiConfigCaseView = {
  key: string
  name: string
  orderNo?: number
  method: string
  path: string
  headers?: unknown
  query?: unknown
  body?: unknown
  response?: unknown
  extractRules: ApiConfigRule[]
  assertRules: ApiConfigRule[]
  usedVariables: string[]
  extractedVariables: string[]
}

export type ApiConfigDiagramData = {
  cases: ApiConfigCaseView[]
  totalExtractRules: number
  totalAssertRules: number
  authHeaderCount: number
}

function toDisplayText(value: unknown) {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function pickText(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const text = toDisplayText(record[key])
    if (text) return text
  }
  return ''
}

function pickValue(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = record[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return undefined
}

function parseJsonLikeValue(value: unknown) {
  if (typeof value !== 'string') return value
  const trimmed = value.trim()
  if (!trimmed) return value
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return value
  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

export function stringifyCompact(value: unknown) {
  if (value === undefined || value === null || value === '') return ''
  const parsed = parseJsonLikeValue(value)
  if (typeof parsed === 'string') return parsed
  try {
    return JSON.stringify(parsed, null, 2)
  } catch {
    return String(parsed)
  }
}

function collectTemplateVariables(value: unknown) {
  const source = stringifyCompact(value)
  if (!source) return []
  const variables = new Set<string>()
  const pattern = /\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}|\{\s*([A-Za-z_][\w.-]*)\s*\}/g
  let match: RegExpExecArray | null

  while ((match = pattern.exec(source)) !== null) {
    const variable = match[1] || match[2]
    if (variable) variables.add(variable)
  }

  return [...variables]
}

function formatRule(rule: Record<string, unknown>, fallback: string): ApiConfigRule {
  const name = pickText(rule, ['name', 'ruleName', 'varKey', 'targetExpr', 'sourceExpr']) || fallback
  const detailCandidates = [
    pickText(rule, ['sourceExpr', 'targetExpr', 'assertSource']),
    pickText(rule, ['comparator', 'operator']),
    pickText(rule, ['expectedValue', 'value', 'source']),
  ].filter(Boolean)

  return {
    name,
    detail: detailCandidates.join(' / ') || stringifyCompact(rule),
  }
}

export function normalizeApiConfigCases(content?: string): ApiConfigDiagramData | null {
  if (!content?.trim()) return null

  try {
    const parsed = parse(content)
    const entries: Array<{ key: string; value: unknown; index: number }> = []

    if (Array.isArray(parsed)) {
      parsed.forEach((value, index) => entries.push({ key: `case-${index + 1}`, value, index }))
    } else if (parsed && typeof parsed === 'object') {
      const record = parsed as Record<string, unknown>
      const cases = Array.isArray(record.cases) ? record.cases : Array.isArray(record.apiCases) ? record.apiCases : null
      if (cases) {
        cases.forEach((value, index) => entries.push({ key: `case-${index + 1}`, value, index }))
      } else {
        Object.entries(record).forEach(([key, value], index) => entries.push({ key, value, index }))
      }
    }

    const cases = entries
      .map((entry): ApiConfigCaseView | null => {
        const record = toRecord(entry.value)
        if (!record) return null

        const method = pickText(record, ['method', 'httpMethod']).toUpperCase() || 'API'
        const path = pickText(record, ['path', 'urlTemplate', 'url', 'endpoint']) || '-'
        const headers = parseJsonLikeValue(pickValue(record, ['headers', 'headersJson', 'requestHeaders']))
        const query = parseJsonLikeValue(pickValue(record, ['query', 'queryJson', 'params', 'queryParams']))
        const body = parseJsonLikeValue(pickValue(record, ['json', 'bodyJson', 'body', 'bodyText', 'requestBody']))
        const response = parseJsonLikeValue(pickValue(record, ['response', 'responseJson', 'responseBody']))
        const extractRules = toRecordArray(pickValue(record, ['extractRules', 'extract_rules', 'extractors', 'extractions']))
          .map((rule, index) => formatRule(rule, `提取规则 ${index + 1}`))
        const assertRules = toRecordArray(pickValue(record, ['assertRules', 'assert_rules', 'assertions', 'checks']))
          .map((rule, index) => formatRule(rule, `断言规则 ${index + 1}`))
        const extractedVariables = extractRules
          .map((rule) => rule.name)
          .filter(Boolean)
        const usedVariables = [
          ...collectTemplateVariables(path),
          ...collectTemplateVariables(headers),
          ...collectTemplateVariables(query),
          ...collectTemplateVariables(body),
        ]
        const orderText = pickText(record, ['orderNo', 'order', 'sort'])
        const orderNo = Number(orderText)

        return {
          key: `${entry.key}-${entry.index}`,
          name: pickText(record, ['name', 'caseName', 'title']) || entry.key,
          ...(Number.isFinite(orderNo) ? { orderNo } : {}),
          method,
          path,
          ...(headers !== undefined && headers !== null && headers !== '' ? { headers } : {}),
          ...(query !== undefined && query !== null && query !== '' ? { query } : {}),
          ...(body !== undefined && body !== null && body !== '' ? { body } : {}),
          ...(response !== undefined && response !== null && response !== '' ? { response } : {}),
          extractRules,
          assertRules,
          usedVariables: [...new Set(usedVariables)],
          extractedVariables: [...new Set(extractedVariables)],
        }
      })
      .filter((item): item is ApiConfigCaseView => Boolean(item))
      .sort((left, right) => (left.orderNo ?? Number.MAX_SAFE_INTEGER) - (right.orderNo ?? Number.MAX_SAFE_INTEGER))

    if (cases.length === 0) return null

    return {
      cases,
      totalExtractRules: cases.reduce((sum, item) => sum + item.extractRules.length, 0),
      totalAssertRules: cases.reduce((sum, item) => sum + item.assertRules.length, 0),
      authHeaderCount: cases.filter((item) => {
        const headers = toRecord(parseJsonLikeValue(item.headers))
        return Boolean(headers && Object.keys(headers).some((key) => key.toLowerCase().includes('authorization')))
      }).length,
    }
  } catch {
    return null
  }
}
