import { ApiError } from '@/services/api'
import { getErrorMessage } from '@/utils/format'
import type {
  ApiInterface,
  CreateApiInterfacePayload,
  InterfaceRow,
} from '../types'
import {
  jsonText,
  parseJsonText,
  pathParameterNames,
  splitTags,
} from './interfaceForm'

export type JsonTexts = {
  bodySchema: string
  bodyExample: string
  responseSchema: string
  responseExample: string
}

export const EMPTY_JSON_TEXTS: JsonTexts = {
  bodySchema: '',
  bodyExample: '',
  responseSchema: '',
  responseExample: '',
}

export function enabledCount(rows: InterfaceRow[]) {
  return rows.filter(row => row.enabled && row.name.trim()).length
}

export function jsonTextsOf(data: ApiInterface): JsonTexts {
  return {
    bodySchema: jsonText(data.bodySchema),
    bodyExample: jsonText(data.bodyExample),
    responseSchema: jsonText(data.responseSchema),
    responseExample: jsonText(data.responseExample),
  }
}

export function buildPayload(
  draft: ApiInterface,
  tagsText: string,
  jsonTexts: JsonTexts,
): CreateApiInterfacePayload {
  const name = draft.name.trim()
  if (!name) throw new Error('请填写接口名称')
  const path = draft.path.trim()
  if (!path) throw new Error('请填写接口路径')

  const pathParams = cleanRows(draft.pathParams, 'Path 参数', true)
  const queryParams = cleanRows(draft.queryParams, 'Query 参数', false)
  const headers = cleanRows(draft.headers, '请求头', false)
  validatePathRows(path, pathParams)

  const hasJsonBody = draft.bodyType === 'json' || draft.bodyType === 'form'
  const bodySchema = hasJsonBody ? parseEditorJson(jsonTexts.bodySchema, '请求体 Schema') : null
  const bodyExample = hasJsonBody ? parseEditorJson(jsonTexts.bodyExample, '请求体示例') : null
  const responseSchema = parseEditorJson(jsonTexts.responseSchema, '响应 Schema')
  const responseExample = parseEditorJson(jsonTexts.responseExample, '响应示例')
  const tags = splitTags(tagsText)
  const description = draft.description.trim()
  const responseDescription = draft.responseDescription.trim()

  if (description.length > 1024) throw new Error('接口描述不能超过 1024 个字符')
  if (responseDescription.length > 512) throw new Error('响应说明不能超过 512 个字符')
  if (tags.length > 20) throw new Error('标签不能超过 20 个')
  if (draft.bodyText.length > 20000) throw new Error('Raw 请求体不能超过 20000 个字符')
  for (const [label, rows] of [
    ['请求头', headers],
    ['Path 参数', pathParams],
    ['Query 参数', queryParams],
  ] as const) {
    if (rows.length > 200) throw new Error(`${label}不能超过 200 行`)
  }

  return {
    name,
    method: draft.method,
    path,
    description,
    tags,
    headers,
    pathParams,
    queryParams,
    bodyType: draft.bodyType,
    // Hidden editors for raw/none body types must not block saving their stale text.
    bodySchema,
    bodyExample,
    bodyText: draft.bodyType === 'raw' ? draft.bodyText : '',
    responseStatus: draft.responseStatus,
    responseDescription,
    responseSchema,
    responseExample,
    requirementIds: draft.requirements.map(requirement => requirement.requirementId),
  }
}

function cleanRows(rows: InterfaceRow[], label: string, forceRequired: boolean): InterfaceRow[] {
  const kept = rows.filter(
    row => row.name.trim() || row.example.trim() || row.description.trim(),
  )
  const missingName = kept.find(row => !row.name.trim())
  if (missingName) throw new Error(`${label}中存在未填写名称的行`)
  const seen = new Set<string>()
  return kept.map(row => {
    const rowName = row.name.trim()
    const identity = label === '请求头' ? rowName.toLowerCase() : rowName
    if (seen.has(identity)) throw new Error(`${label}名称重复：${rowName}`)
    seen.add(identity)
    return {
      ...row,
      name: rowName,
      required: forceRequired ? true : row.required,
      example: row.example,
      description: row.description.trim(),
    }
  })
}

function validatePathRows(path: string, rows: InterfaceRow[]) {
  const expected = new Set(pathParameterNames(path))
  const actual = new Set(rows.map(row => row.name))
  const missing = [...expected].filter(name => !actual.has(name))
  const extra = [...actual].filter(name => !expected.has(name))
  if (!missing.length && !extra.length) return
  const parts: string[] = []
  if (missing.length) parts.push(`缺少 ${missing.join('、')}`)
  if (extra.length) parts.push(`多余 ${extra.join('、')}`)
  throw new Error(`Path 参数与路径占位符不一致（${parts.join('；')}）`)
}

function parseEditorJson(text: string, label: string): unknown {
  const parsed = parseJsonText(text)
  if (!parsed.valid) throw new Error(`${label}格式错误：${parsed.error}`)
  return parsed.value
}

export function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return getErrorMessage(error)
}
