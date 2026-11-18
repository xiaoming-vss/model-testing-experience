import { parseDocument } from 'yaml'
import {
  perfLoadFormError,
  readPerfLoadFromYaml,
  serializePerfLoad,
  type PerfLoadFormValues,
} from './perfLoadModel'

export type PerfHttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS'
export type PerfFailurePolicy = 'abort_iteration' | 'continue' | 'abort_test'
export type PerfCheckType = 'status' | 'json' | 'header' | 'body'
export type PerfCheckOp = 'eq' | 'ne' | 'exists' | 'regex' | 'contains' | 'in' | 'gte' | 'lte'
export type PerfExtractSource = 'json' | 'header' | 'regex'
export type PerfDataStrategy = 'unique_per_iteration' | 'per_vu' | 'random' | 'cycle'
export type PerfExhaustedPolicy = 'cycle' | 'fail'
export type PerfBodyMode = 'none' | 'json' | 'text'
export type PerfBodyContentType = 'json' | 'form'

export type PerfHeaderRow = { id: string; name: string; value: string }
export type PerfCheckRow = {
  id: string
  type: PerfCheckType
  op: PerfCheckOp
  path: string
  name: string
  pattern: string
  value: string
}
export type PerfExtractRow = {
  id: string
  name: string
  source: PerfExtractSource
  path: string
  pattern: string
  group: number
}
export type PerfStepFormValues = {
  id: string
  name: string
  method: PerfHttpMethod
  path: string
  headers: PerfHeaderRow[]
  bodyMode: PerfBodyMode
  bodyContentType: PerfBodyContentType
  bodyText: string
  checks: PerfCheckRow[]
  extract: PerfExtractRow[]
  onFailure: PerfFailurePolicy
  thinkTimeMs: number
}
export type PerfDataEntryFormValues = {
  id: string
  name: string
  source: string
  rows?: Record<string, string>[]
  strategy: PerfDataStrategy
  onExhausted: PerfExhaustedPolicy
}
export type PerfCaseFormValues = {
  name: string
  load: PerfLoadFormValues
  steps: PerfStepFormValues[]
  data: PerfDataEntryFormValues[]
}

const HTTP_METHODS: PerfHttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
const CHECK_TYPES: PerfCheckType[] = ['status', 'json', 'header', 'body']
const CHECK_OPS: PerfCheckOp[] = ['eq', 'ne', 'exists', 'regex', 'contains', 'in', 'gte', 'lte']
const STATUS_CHECK_OPS: PerfCheckOp[] = ['eq', 'ne', 'gte', 'lte']
const EXTRACT_SOURCES: PerfExtractSource[] = ['json', 'header', 'regex']
const DATA_STRATEGIES: PerfDataStrategy[] = ['unique_per_iteration', 'per_vu', 'random', 'cycle']
const EXHAUSTED_POLICIES: PerfExhaustedPolicy[] = ['cycle', 'fail']

let idSequence = 0
function formId(prefix: string) {
  idSequence += 1
  return `${prefix}-${idSequence}`
}

function toRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function stringValue(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function numberValue(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value) ? value as T : fallback
}

function parseYamlRoot(yamlText: string): Record<string, unknown> | null {
  try {
    const document = parseDocument(yamlText)
    if (document.errors.length > 0) return null
    return toRecord(document.toJS())
  } catch {
    return null
  }
}

export function createPerfHeaderRow(): PerfHeaderRow {
  return { id: formId('header'), name: '', value: '' }
}

export function createPerfCheckRow(): PerfCheckRow {
  return { id: formId('check'), type: 'status', op: 'eq', path: '', name: '', pattern: '', value: '200' }
}

export function createPerfExtractRow(): PerfExtractRow {
  return { id: formId('extract'), name: '', source: 'json', path: '', pattern: '', group: 1 }
}

export function createPerfStep(overrides: Partial<PerfStepFormValues> = {}): PerfStepFormValues {
  return {
    id: formId('step'),
    name: '',
    method: 'GET',
    path: '/',
    headers: [],
    bodyMode: 'none',
    bodyContentType: 'json',
    bodyText: '',
    checks: [createPerfCheckRow()],
    extract: [],
    onFailure: 'abort_iteration',
    thinkTimeMs: 0,
    ...overrides,
  }
}

export function createPerfDataEntry(overrides: Partial<PerfDataEntryFormValues> = {}): PerfDataEntryFormValues {
  return {
    id: formId('data'),
    name: '',
    source: '',
    strategy: 'unique_per_iteration',
    onExhausted: 'cycle',
    ...overrides,
  }
}

function readHeaders(value: unknown): PerfHeaderRow[] {
  const record = toRecord(value)
  if (!record) return []
  return Object.entries(record).map(([name, rowValue]) => ({
    id: formId('header'),
    name,
    value: String(rowValue ?? ''),
  }))
}

function readChecks(value: unknown): PerfCheckRow[] {
  if (!Array.isArray(value)) return []
  return value.map(item => {
    const row = toRecord(item)
    const type = pick(row?.type, CHECK_TYPES, 'status')
    const op = type === 'status' && !STATUS_CHECK_OPS.includes(pick(row?.op, CHECK_OPS, 'eq'))
      ? 'eq'
      : pick(row?.op, CHECK_OPS, 'eq')
    return {
      id: formId('check'),
      type,
      op,
      path: stringValue(row?.path),
      name: stringValue(row?.name),
      pattern: stringValue(row?.pattern),
      value: row?.value === undefined || row?.value === null ? '' : String(row.value),
    }
  })
}

function readExtract(value: unknown): PerfExtractRow[] {
  if (!Array.isArray(value)) return []
  return value.map(item => {
    const row = toRecord(item)
    return {
      id: formId('extract'),
      name: stringValue(row?.name),
      source: pick(row?.from, EXTRACT_SOURCES, 'json'),
      path: stringValue(row?.path),
      pattern: stringValue(row?.pattern),
      group: numberValue(row?.group, 1),
    }
  })
}

function readSteps(value: unknown): PerfStepFormValues[] {
  if (!Array.isArray(value)) return []
  return value.map(item => {
    const step = toRecord(item)
    const contentType = stringValue(step?.contentType)
    const body = step?.body
    const bodyMode: PerfBodyMode = body === undefined || body === null
      ? 'none'
      : contentType === 'text' ? 'text' : 'json'
    return {
      id: formId('step'),
      name: stringValue(step?.name),
      method: pick(step?.method, HTTP_METHODS, 'GET'),
      path: stringValue(step?.path),
      headers: readHeaders(step?.headers),
      bodyMode,
      bodyContentType: contentType === 'form' ? 'form' : 'json',
      bodyText: bodyMode === 'text'
        ? String(body ?? '')
        : bodyMode === 'json' ? JSON.stringify(body, null, 2) : '',
      checks: readChecks(step?.checks),
      extract: readExtract(step?.extract),
      onFailure: pick(step?.onFailure, ['abort_iteration', 'continue', 'abort_test'] as const, 'abort_iteration'),
      thinkTimeMs: numberValue(step?.thinkTimeMs, 0),
    }
  })
}

function readData(value: unknown): PerfDataEntryFormValues[] {
  if (!Array.isArray(value)) return []
  return value.map(item => {
    const entry = toRecord(item)
    return {
      id: formId('data'),
      name: stringValue(entry?.name),
      source: stringValue(entry?.source),
      rows: Array.isArray(entry?.rows)
        ? entry.rows.map(row => toRecord(row) ?? {}).map(row => Object.fromEntries(
          Object.entries(row).map(([key, rowValue]) => [key, String(rowValue ?? '')]),
        ))
        : undefined,
      strategy: pick(entry?.strategy, DATA_STRATEGIES, 'unique_per_iteration'),
      onExhausted: pick(entry?.onExhausted, EXHAUSTED_POLICIES, 'cycle'),
    }
  })
}

export function readPerfCaseForm(
  yamlText: string,
  summary: { name: string },
): PerfCaseFormValues | null {
  const root = parseYamlRoot(yamlText)
  const caseNode = toRecord(root?.case)
  const load = readPerfLoadFromYaml(yamlText)
  if (!caseNode || !load) return null
  return {
    name: stringValue(caseNode.name).trim() || summary.name,
    load,
    steps: readSteps(caseNode.steps),
    data: readData(caseNode.data),
  }
}

function checkToYaml(row: PerfCheckRow): Record<string, unknown> {
  const check: Record<string, unknown> = { type: row.type, op: row.op }
  if (row.type === 'json') check.path = row.path
  if (row.type === 'header') check.name = row.name
  if (row.op === 'regex' || row.op === 'contains') {
    check.pattern = row.pattern
  } else if (row.op !== 'exists') {
    if (row.type === 'status' || row.op === 'gte' || row.op === 'lte') {
      check.value = Number(row.value)
    } else if (row.op === 'in') {
      try {
        check.value = JSON.parse(row.value)
      } catch {
        check.value = row.value.split(',').map(item => item.trim()).filter(Boolean)
      }
    } else {
      let value: unknown = row.value
      try {
        value = JSON.parse(row.value)
      } catch {
        // 非 JSON 标量按普通字符串提交，例如正则或中文文本。
      }
      check.value = value
    }
  }
  return check
}

function extractToYaml(row: PerfExtractRow): Record<string, unknown> {
  const extract: Record<string, unknown> = { name: row.name, from: row.source }
  if (row.source === 'json' || row.source === 'header') extract.path = row.path
  if (row.source === 'regex') {
    extract.pattern = row.pattern
    extract.group = row.group
  }
  return extract
}

function stepToYaml(step: PerfStepFormValues): Record<string, unknown> {
  const output: Record<string, unknown> = {
    name: step.name,
    method: step.method,
    path: step.path,
  }
  const headers = Object.fromEntries(
    step.headers.filter(row => row.name.trim()).map(row => [row.name.trim(), row.value]),
  )
  if (Object.keys(headers).length > 0) output.headers = headers
  if (step.bodyMode !== 'none') {
    output.contentType = step.bodyMode === 'text' ? 'text' : step.bodyContentType
    if (step.bodyMode === 'text') {
      output.body = step.bodyText
    } else {
      try {
        output.body = JSON.parse(step.bodyText)
      } catch {
        output.body = step.bodyText
      }
    }
  }
  if (step.checks.length > 0) output.checks = step.checks.map(checkToYaml)
  if (step.extract.length > 0) output.extract = step.extract.map(extractToYaml)
  if (step.onFailure !== 'abort_iteration') output.onFailure = step.onFailure
  if (step.thinkTimeMs > 0) output.thinkTimeMs = Math.max(0, Math.round(step.thinkTimeMs))
  return output
}

function dataToYaml(entry: PerfDataEntryFormValues): Record<string, unknown> {
  const output: Record<string, unknown> = { name: entry.name }
  if (entry.rows && entry.rows.length > 0) {
    output.rows = entry.rows
  } else {
    output.source = entry.source
  }
  output.strategy = entry.strategy
  output.onExhausted = entry.onExhausted
  return output
}

export function updatePerfCaseInYaml(yamlText: string, form: PerfCaseFormValues): string {
  try {
    const document = parseDocument(yamlText)
    if (document.errors.length > 0) return yamlText
    document.setIn(['case', 'name'], form.name.trim())
    document.setIn(['case', 'load'], serializePerfLoad(form.load))
    document.setIn(['case', 'steps'], form.steps.map(stepToYaml))
    if (form.data.length > 0) {
      document.setIn(['case', 'data'], form.data.map(dataToYaml))
    } else {
      document.deleteIn(['case', 'data'])
    }
    return document.toString({ indent: 2, lineWidth: 0 }).trimEnd()
  } catch {
    return yamlText
  }
}

export function variablesBeforeStep(steps: PerfStepFormValues[], stepIndex: number): string[] {
  const names = new Set<string>()
  steps.slice(0, stepIndex).forEach(step => {
    step.extract.forEach(item => { if (item.name.trim()) names.add(item.name.trim()) })
  })
  return Array.from(names)
}

export function perfCaseFormErrors(form: PerfCaseFormValues): string[] {
  const errors: string[] = []
  if (!form.name.trim()) errors.push('用例名称不能为空')
  const loadError = perfLoadFormError(form.load, form.steps.length)
  if (loadError) errors.push(loadError)
  if (form.steps.length === 0) errors.push('至少需要一个 API 步骤')

  const stepNames = new Set<string>()
  form.steps.forEach((step, index) => {
    const label = `步骤 ${index + 1}`
    if (!step.name.trim()) errors.push(`${label}：步骤名称不能为空`)
    if (stepNames.has(step.name.trim())) errors.push(`${label}：步骤名称重复`)
    stepNames.add(step.name.trim())
    if (!step.path.trim()) errors.push(`${label}：请求路径不能为空`)
    if (step.bodyMode === 'json' && step.bodyText.trim()) {
      try {
        JSON.parse(step.bodyText)
      } catch {
        errors.push(`${label}：请求体不是合法 JSON`)
      }
    }
    const headerNames = new Set<string>()
    step.headers.forEach(header => {
      const name = header.name.trim()
      if (!name) return
      if (headerNames.has(name)) errors.push(`${label}：请求头 ${name} 重复`)
      headerNames.add(name)
    })
    step.extract.forEach(item => {
      if (!item.name.trim()) errors.push(`${label}：提取变量名不能为空`)
      if (item.source !== 'regex' && !item.path.trim()) errors.push(`${label}：提取变量 ${item.name || '未命名'} 缺少路径`)
      if (item.source === 'regex' && !item.pattern.trim()) errors.push(`${label}：提取变量 ${item.name || '未命名'} 缺少正则`)
    })
    step.checks.forEach((check, checkIndex) => {
      const checkLabel = `${label} 校验 ${checkIndex + 1}`
      if (check.type === 'json' && !check.path.trim()) errors.push(`${checkLabel}：JSON 路径不能为空`)
      if (check.type === 'header' && !check.name.trim()) errors.push(`${checkLabel}：响应头名称不能为空`)
      if ((check.op === 'regex' || check.op === 'contains') && !check.pattern.trim()) errors.push(`${checkLabel}：匹配内容不能为空`)
      if ((check.type === 'status' || check.op === 'gte' || check.op === 'lte') && !Number.isFinite(Number(check.value))) {
        errors.push(`${checkLabel}：校验值必须是数字`)
      }
    })
  })

  const dataNames = new Set<string>()
  form.data.forEach((entry, index) => {
    const label = `数据 ${index + 1}`
    if (!entry.name.trim()) errors.push(`${label}：数据名不能为空`)
    if (dataNames.has(entry.name.trim())) errors.push(`${label}：数据名重复`)
    dataNames.add(entry.name.trim())
    if (!entry.source.trim() && (!entry.rows || entry.rows.length === 0)) errors.push(`${label}：需要选择数据文件或提供内嵌数据`)
  })

  return errors
}
