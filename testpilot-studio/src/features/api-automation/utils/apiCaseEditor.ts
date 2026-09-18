import type {
  ApiAssertRule,
  ApiCase,
  ApiCollectionRunItem,
  ApiEnvironment,
  ApiExtractRule,
  CreateApiCasePayload,
  UpdateApiCasePayload,
} from '@/services/api'
import { moveArrayItem } from '@/shared/utils/array'
import { formatOptionalValue, parseMaybeJsonValue } from '@/shared/utils/value'
import { normalizeAssertRuleId, normalizeExtractRuleId, pickCreatedAt } from '@/utils/format'

export const EMPTY_API_CASES: ApiCase[] = []
export const EMPTY_API_ENVIRONMENTS: ApiEnvironment[] = []
export const EMPTY_ASSERT_RULES: ApiAssertRule[] = []
export const EMPTY_EXTRACT_RULES: ApiExtractRule[] = []

export type ApiCaseFormValues = {
  name: string
  method: ApiCase['method']
  path: string
  description?: string
  headers?: Array<{ enabled?: boolean; key?: string; value?: string }>
  query?: Array<{ enabled?: boolean; key?: string; value?: string }>
  bodyType?: ApiCase['bodyType']
  bodyJson?: string
  bodyText?: string
  timeoutMs?: number
  enabled?: boolean
  continueOnFailure?: boolean
}

export function createDefaultCaseFormValues(): ApiCaseFormValues {
  return {
    name: '',
    method: 'POST',
    path: '',
    description: '',
    headers: [{ enabled: false, key: '', value: '' }],
    query: [{ enabled: false, key: '', value: '' }],
    bodyType: 'none',
    bodyJson: '',
    bodyText: '',
    timeoutMs: 30000,
    enabled: true,
    continueOnFailure: false,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function normalizeKeyValueRows(rows: Array<{ enabled?: boolean; key?: string; value?: string }>) {
  return rows.length > 0 ? [...rows, { enabled: false, key: '', value: '' }] : [{ enabled: false, key: '', value: '' }]
}

function pickStringField(source: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = source[key]
    if (typeof value === 'string') return value
    if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  }
  return ''
}

function parseKeyValueObject(value: Record<string, unknown>) {
  const entries = Object.entries(value).map(([key, itemValue]) => {
    if (isRecord(itemValue)) {
      return {
        enabled: itemValue.enabled === undefined ? true : Boolean(itemValue.enabled),
        key,
        value: pickStringField(itemValue, 'value', 'values', 'defaultValue', 'default_value'),
      }
    }

    return {
      enabled: true,
      key,
      value: itemValue == null ? '' : String(itemValue),
    }
  })

  return normalizeKeyValueRows(entries)
}

function parseKeyValueArray(value: unknown[]) {
  const entries = value
    .filter(isRecord)
    .map((item) => ({
      enabled: item.enabled === undefined ? true : Boolean(item.enabled),
      key: pickStringField(item, 'key', 'name', 'header', 'paramKey', 'param_key'),
      value: pickStringField(item, 'value', 'values', 'paramValue', 'param_value'),
    }))
    .filter((item) => item.key || item.value)

  return normalizeKeyValueRows(entries)
}

export function parseKeyValueJson(value?: unknown) {
  if (!value) return [{ enabled: false, key: '', value: '' }]

  if (Array.isArray(value)) return parseKeyValueArray(value)
  if (isRecord(value)) return parseKeyValueObject(value)

  try {
    const parsed = JSON.parse(String(value)) as unknown
    return parseKeyValueJson(parsed)
  } catch {
    return [{ enabled: false, key: '', value: '' }]
  }
}

export function stringifyKeyValuePairs(items?: Array<{ enabled?: boolean; key?: string; value?: string }>) {
  const filtered = (items ?? []).filter((item) => item.enabled !== false && item.key?.trim())
  if (filtered.length === 0) return ''

  return JSON.stringify(
    filtered.reduce<Record<string, string>>((result, item) => {
      result[item.key!.trim()] = item.value ?? ''
      return result
    }, {}),
  )
}

function normalizeText(value?: string) {
  return value ?? ''
}

export function serializeCaseValues(values: ApiCaseFormValues): CreateApiCasePayload {
  return {
    name: values.name,
    method: values.method,
    urlTemplate: values.path,
    description: values.description,
    headersJson: stringifyKeyValuePairs(values.headers),
    queryJson: stringifyKeyValuePairs(values.query),
    bodyType: values.bodyType,
    bodyJson: values.bodyJson,
    bodyText: values.bodyText,
    timeoutMs: values.timeoutMs,
    enabled: values.enabled,
    continueOnFailure: values.continueOnFailure,
  }
}

export function buildCaseFormValues(apiCase: ApiCase): ApiCaseFormValues {
  const defaults = createDefaultCaseFormValues()

  return {
    ...defaults,
    name: apiCase.name ?? defaults.name,
    method: apiCase.method ?? defaults.method,
    path: apiCase.urlTemplate ?? apiCase.url_template ?? defaults.path,
    description: apiCase.description ?? defaults.description,
    headers: parseKeyValueJson(apiCase.headersJson ?? apiCase.headers_json ?? apiCase.headers),
    query: parseKeyValueJson(apiCase.queryJson ?? apiCase.query_json ?? apiCase.query),
    bodyType: apiCase.bodyType ?? apiCase.body_type ?? defaults.bodyType,
    bodyJson: apiCase.bodyJson ?? apiCase.body_json ?? defaults.bodyJson,
    bodyText: apiCase.bodyText ?? apiCase.body_text ?? defaults.bodyText,
    timeoutMs: apiCase.timeoutMs ?? apiCase.timeout_ms ?? defaults.timeoutMs,
    enabled: apiCase.enabled ?? defaults.enabled,
    continueOnFailure: apiCase.continueOnFailure ?? apiCase.continue_on_failure ?? defaults.continueOnFailure,
  }
}

export function buildApiCaseUpdatePayload(apiCase: ApiCase, values: ApiCaseFormValues): UpdateApiCasePayload {
  const currentValues = buildCaseFormValues(apiCase)
  const nextValues = serializeCaseValues(values)
  const payload: UpdateApiCasePayload = {}

  if (currentValues.name !== values.name) payload.name = nextValues.name
  if (currentValues.method !== values.method) payload.method = nextValues.method
  if (currentValues.path !== values.path) payload.urlTemplate = nextValues.urlTemplate
  if (normalizeText(currentValues.description) !== normalizeText(values.description)) payload.description = nextValues.description ?? ''
  if (normalizeText(stringifyKeyValuePairs(currentValues.headers)) !== normalizeText(nextValues.headersJson)) payload.headersJson = nextValues.headersJson ?? ''
  if (normalizeText(stringifyKeyValuePairs(currentValues.query)) !== normalizeText(nextValues.queryJson)) payload.queryJson = nextValues.queryJson ?? ''
  if (currentValues.bodyType !== values.bodyType) payload.bodyType = nextValues.bodyType
  if (normalizeText(currentValues.bodyJson) !== normalizeText(values.bodyJson)) payload.bodyJson = nextValues.bodyJson ?? ''
  if (normalizeText(currentValues.bodyText) !== normalizeText(values.bodyText)) payload.bodyText = nextValues.bodyText ?? ''
  if (currentValues.timeoutMs !== values.timeoutMs) payload.timeoutMs = nextValues.timeoutMs
  if (currentValues.enabled !== values.enabled) payload.enabled = nextValues.enabled
  if (currentValues.continueOnFailure !== values.continueOnFailure) payload.continueOnFailure = nextValues.continueOnFailure

  return payload
}

export function mergeApiCaseWithFormValues(apiCase: ApiCase | null | undefined, values: ApiCaseFormValues): ApiCase {
  const serializedValues = serializeCaseValues(values)

  return {
    ...(apiCase ?? {
      name: values.name,
      method: values.method ?? 'POST',
      urlTemplate: values.path,
    }),
    name: values.name,
    description: values.description,
    method: values.method,
    urlTemplate: values.path,
    headersJson: serializedValues.headersJson,
    queryJson: serializedValues.queryJson,
    bodyType: values.bodyType,
    bodyJson: values.bodyJson,
    bodyText: values.bodyText,
    timeoutMs: values.timeoutMs,
    enabled: values.enabled,
    continueOnFailure: values.continueOnFailure,
  }
}

export function mergeDefinedApiCaseFields(baseCase: ApiCase, nextCase: ApiCase): ApiCase {
  const mergedCase = { ...baseCase } as Record<string, unknown>
  ;(Object.keys(nextCase) as Array<keyof ApiCase>).forEach((key) => {
    const value = nextCase[key]
    if (value !== undefined) mergedCase[key] = value
  })
  return mergedCase as ApiCase
}

export function getCaseId(apiCase: ApiCase) {
  return apiCase.caseId ?? apiCase.case_id ?? ''
}

export function getCollectionRunItemKey(item: ApiCollectionRunItem, index: number) {
  return item.itemId || item.caseRunId || `${item.caseId ?? 'case'}-${item.orderNo ?? index}-${index}`
}

export function getCaseDisplayPath(urlTemplate: string) {
  const value = urlTemplate.trim()
  if (!value) return ''

  if (/^https?:\/\//i.test(value)) {
    try {
      const parsed = new URL(value)
      return `${parsed.pathname}${parsed.search}${parsed.hash}` || '/'
    } catch {
      return value
    }
  }

  return value
}

function getCaseOrderNo(apiCase: ApiCase) {
  return apiCase.orderNo ?? apiCase.order_no ?? Number.MAX_SAFE_INTEGER
}

function getCaseCreatedTime(apiCase: ApiCase) {
  const createdAt = pickCreatedAt(apiCase)
  const timestamp = createdAt ? new Date(createdAt).getTime() : 0
  return Number.isNaN(timestamp) ? 0 : timestamp
}

export function sortCasesByOrderNo(cases: ApiCase[]) {
  return [...cases].sort(
    (left, right) =>
      getCaseOrderNo(left) - getCaseOrderNo(right) ||
      getCaseCreatedTime(right) - getCaseCreatedTime(left) ||
      getCaseId(left).localeCompare(getCaseId(right)),
  )
}

export { formatOptionalValue, moveArrayItem, parseMaybeJsonValue }

export function sortRulesByOrderNo<T extends { orderNo?: number; createdAt?: string; created_at?: string }>(rules: T[]) {
  return [...rules].sort((left, right) => {
    const leftOrderNo = left.orderNo ?? Number.MAX_SAFE_INTEGER
    const rightOrderNo = right.orderNo ?? Number.MAX_SAFE_INTEGER
    if (leftOrderNo !== rightOrderNo) return leftOrderNo - rightOrderNo

    const leftCreatedTime = left.createdAt ?? left.created_at ?? ''
    const rightCreatedTime = right.createdAt ?? right.created_at ?? ''
    return new Date(leftCreatedTime).getTime() - new Date(rightCreatedTime).getTime()
  })
}

export function getAssertRuleId(rule: ApiAssertRule) {
  return normalizeAssertRuleId(rule)
}

export function getExtractRuleId(rule: ApiExtractRule) {
  return normalizeExtractRuleId(rule)
}
