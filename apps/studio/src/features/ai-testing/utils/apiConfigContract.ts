import { stringifyCompact, type ApiConfigCaseView } from './apiConfigDiagram'

/** 一行接口契约字段：叶子字段或可展开的对象/数组节点。 */
export type ApiConfigFieldView = {
  key: string
  name: string
  path: string
  depth: number
  ancestorPaths: string[]
  kind: 'field' | 'object' | 'array'
  type: string
  value: string
  required: boolean
  optional: boolean
  defaultValue: string
  enumValue: string
  constraints: string[]
  description: string
  keyExtraction: boolean
  childCount: number
}

export type ParsedApiConfigField = Pick<
  ApiConfigFieldView,
  'type' | 'value' | 'required' | 'optional' | 'defaultValue' | 'enumValue' | 'constraints' | 'description' | 'keyExtraction'
>

export type ApiConfigContractView = {
  headers: ApiConfigFieldView[]
  pathParams: ApiConfigFieldView[]
  query: ApiConfigFieldView[]
  body: ApiConfigFieldView[]
  bodyLabel: string
  rawBody?: string
  response: ApiConfigFieldView[]
  requestFieldCount: number
  responseFieldCount: number
  totalFieldCount: number
  keyExtractions: ApiConfigFieldView[]
  authHeader: ApiConfigFieldView | null
  usedVariables: string[]
}

const TYPE_NAMES = new Set([
  'string', 'integer', 'number', 'boolean', 'object', 'array', 'date', 'datetime', 'file', 'uuid', 'null', 'any',
])

const CONSTRAINT_PREFIX = /^(?:必传|可选|default\s*:|enum\s*:|maxLength\s*:|minLength\s*:|minimum\s*:|maximum\s*:|min\s*:|max\s*:|format\s*:|pattern\s*:|unique\s*:|nullable\b|允许任意)/i

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

/** 逗号也会出现在 enum 值里；只在下一段是已知约束时才断开。 */
function splitConstraints(raw: string) {
  const parts = raw.replace(/，/g, ',').split(',').map((item) => item.trim()).filter(Boolean)
  const merged: string[] = []
  for (const part of parts) {
    const previous = merged[merged.length - 1]
    if (previous && /^enum\s*:/i.test(previous) && !CONSTRAINT_PREFIX.test(part)) {
      merged[merged.length - 1] = `${previous},${part}`
    } else {
      merged.push(part)
    }
  }
  return merged
}

function emptyField(): ParsedApiConfigField {
  return {
    type: 'value',
    value: '',
    required: false,
    optional: false,
    defaultValue: '',
    enumValue: '',
    constraints: [],
    description: '',
    keyExtraction: false,
  }
}

export function parseApiConfigFieldDescriptor(raw: unknown): ParsedApiConfigField {
  if (typeof raw !== 'string') {
    if (raw === undefined || raw === null) return emptyField()
    return {
      ...emptyField(),
      type: typeof raw === 'number' ? 'number' : typeof raw === 'boolean' ? 'boolean' : 'value',
      value: String(raw),
    }
  }

  const source = raw.trim()
  if (!source) return emptyField()

  let head = source
  let rawDescription = ''
  const hashMatch = source.match(/\s#\s*/)
  if (hashMatch?.index !== undefined) {
    head = source.slice(0, hashMatch.index).trim()
    rawDescription = source.slice(hashMatch.index + hashMatch[0].length).trim()
  }

  let type = 'value'
  let value = ''
  let optionText = ''
  const typeMatch = head.match(/^([A-Za-z_][\w<>[\]]*)\s*(?:\((.*)\))?\s*$/)
  if (typeMatch && TYPE_NAMES.has(typeMatch[1].split('<')[0].toLowerCase())) {
    type = typeMatch[1]
    optionText = typeMatch[2] ?? ''
  } else {
    value = head
  }

  const options = splitConstraints(optionText)
    .map((item) => item.replace(/\[(?:必传|可选|关键提取)\]/g, '').trim())
    .filter(Boolean)
  const required = options.includes('必传') || /\[必传\]/.test(rawDescription)
  const optional = !required && (options.includes('可选') || /\[可选\]/.test(rawDescription))
  const defaultValue = options.find((item) => /^default\s*:/i.test(item))?.replace(/^default\s*:\s*/i, '') ?? ''
  const enumValue = options.find((item) => /^enum\s*:/i.test(item))?.replace(/^enum\s*:\s*/i, '') ?? ''
  const constraints = options.filter((item) => {
    return item !== '必传' && item !== '可选' && !/^default\s*:/i.test(item) && !/^enum\s*:/i.test(item)
  })
  const keyExtraction = /\[关键提取\]/.test(rawDescription)
  const description = rawDescription
    .replace(/\[(?:必传|可选|关键提取)\]/g, '')
    .replace(/^[\s,，;；]+|[\s,，;；]+$/g, '')

  return {
    type,
    value,
    required,
    optional,
    defaultValue,
    enumValue,
    constraints,
    description,
    keyExtraction,
  }
}

function fieldRow(name: string, path: string, depth: number, ancestorPaths: string[], parsed: ParsedApiConfigField): ApiConfigFieldView {
  return {
    key: path,
    name,
    path,
    depth,
    ancestorPaths,
    kind: 'field',
    childCount: 0,
    ...parsed,
  }
}

function containerRow(
  name: string,
  path: string,
  depth: number,
  ancestorPaths: string[],
  kind: 'object' | 'array',
  childCount: number,
): ApiConfigFieldView {
  return {
    key: path,
    name,
    path,
    depth,
    ancestorPaths,
    kind,
    type: kind,
    value: '',
    required: false,
    optional: false,
    defaultValue: '',
    enumValue: '',
    constraints: [],
    description: '',
    keyExtraction: false,
    childCount,
  }
}

function flattenObject(value: Record<string, unknown>, prefix: string, depth: number, ancestorPaths: string[]): ApiConfigFieldView[] {
  return Object.entries(value).flatMap(([name, child]) => {
    const path = prefix ? `${prefix}.${name}` : name
    if (isPlainObject(child)) {
      const childKeys = Object.keys(child)
      if (!childKeys.length) {
        return [fieldRow(name, path, depth, ancestorPaths, { ...emptyField(), type: 'object' })]
      }
      return [
        containerRow(name, path, depth, ancestorPaths, 'object', childKeys.length),
        ...flattenObject(child, path, depth + 1, [...ancestorPaths, path]),
      ]
    }
    if (Array.isArray(child)) {
      const firstObject = child.find(isPlainObject)
      if (!firstObject || !Object.keys(firstObject).length) {
        return [fieldRow(name, path, depth, ancestorPaths, {
          ...emptyField(),
          type: 'array',
          value: `[${child.length}]`,
          constraints: [`${child.length} 个元素`],
        })]
      }
      return [
        containerRow(name, path, depth, ancestorPaths, 'array', Object.keys(firstObject).length),
        ...flattenObject(firstObject, `${path}[]`, depth + 1, [...ancestorPaths, path]),
      ]
    }
    return [fieldRow(name, path, depth, ancestorPaths, parseApiConfigFieldDescriptor(child))]
  })
}

function flattenRoot(value: unknown): ApiConfigFieldView[] {
  if (isPlainObject(value)) return flattenObject(value, '', 0, [])
  if (!Array.isArray(value)) return []
  const firstObject = value.find(isPlainObject)
  if (!firstObject || !Object.keys(firstObject).length) {
    return [fieldRow('items', '[]', 0, [], {
      ...emptyField(),
      type: 'array',
      value: `[${value.length}]`,
      constraints: [`${value.length} 个元素`],
    })]
  }
  return [
    containerRow('items', '[]', 0, [], 'array', Object.keys(firstObject).length),
    ...flattenObject(firstObject, '[]', 1, ['[]']),
  ]
}

function flattenHeaders(value: unknown): ApiConfigFieldView[] {
  if (!isPlainObject(value)) return []
  return Object.entries(value).map(([name, raw]) => {
    return fieldRow(name, name, 0, [], parseApiConfigFieldDescriptor(raw))
  })
}

function countLeaves(rows: ApiConfigFieldView[]) {
  return rows.filter((row) => row.kind === 'field').length
}

export function buildApiConfigContract(apiCase: ApiConfigCaseView): ApiConfigContractView {
  const headers = flattenHeaders(apiCase.headers)
  const pathParams = flattenRoot(apiCase.pathParams)
  const query = flattenRoot(apiCase.query)
  const body = flattenRoot(apiCase.body)
  const response = flattenRoot(apiCase.response)
  const bodyIsScalar = apiCase.body !== undefined && apiCase.body !== null && apiCase.body !== ''
    && !isPlainObject(apiCase.body) && !Array.isArray(apiCase.body)
  const rawBody = bodyIsScalar ? stringifyCompact(apiCase.body) : ''
  const requestFieldCount = headers.length + countLeaves(pathParams) + countLeaves(query)
    + (body.length ? countLeaves(body) : rawBody ? 1 : 0)
  const responseFieldCount = countLeaves(response)
  const keyExtractions = response.filter((row) => row.kind === 'field' && row.keyExtraction)

  return {
    headers,
    pathParams,
    query,
    body,
    bodyLabel: apiCase.bodyLabel ?? 'Body',
    ...(rawBody ? { rawBody } : {}),
    response,
    requestFieldCount,
    responseFieldCount,
    totalFieldCount: requestFieldCount + responseFieldCount,
    keyExtractions,
    authHeader: headers.find((row) => row.name.toLowerCase().includes('authorization')) ?? null,
    usedVariables: apiCase.usedVariables,
  }
}
