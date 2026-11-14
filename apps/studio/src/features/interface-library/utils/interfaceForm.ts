import type { ApiInterface, InterfaceRow } from '../types'

export const INTERFACE_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'] as const
export const ROW_TYPES = ['string', 'integer', 'number', 'boolean', 'array', 'object', 'file'] as const
export const BODY_TYPES = [
  { value: 'json', label: 'JSON' },
  { value: 'form', label: 'Form' },
  { value: 'raw', label: 'Raw' },
  { value: 'none', label: 'None' },
] as const

export function methodTone(method: string) {
  return INTERFACE_METHODS.includes(method as (typeof INTERFACE_METHODS)[number])
    ? method.toLowerCase()
    : 'other'
}

export function blankRow(): InterfaceRow {
  return {
    enabled: true,
    name: '',
    type: 'string',
    required: false,
    example: '',
    description: '',
  }
}

export function blankInterface(appId: string): ApiInterface {
  return {
    interfaceId: '',
    appId,
    appName: '',
    name: '',
    method: 'GET',
    path: '',
    description: '',
    tags: [],
    headers: [],
    pathParams: [],
    queryParams: [],
    bodyType: 'none',
    bodySchema: null,
    bodyExample: null,
    bodyText: '',
    responseStatus: 200,
    responseDescription: '',
    responseSchema: null,
    responseExample: null,
    enabled: true,
    sourceType: 'manual',
    version: 1,
    requirements: [],
    source: { type: 'manual', name: '', url: '', version: '', importedAt: null },
  }
}

export function pathParameterNames(path: string): string[] {
  const names: string[] = []
  for (const match of path.matchAll(/\{([^{}]+)\}/g)) {
    const name = match[1].trim()
    if (name && !names.includes(name)) names.push(name)
  }
  return names
}

/** Keep path parameter rows in step with the path placeholders. */
export function syncPathParams(path: string, rows: InterfaceRow[]): InterfaceRow[] {
  const names = pathParameterNames(path)
  const byName = new Map(rows.filter(row => row.name).map(row => [row.name, row]))
  return names.map(name => {
    const existing = byName.get(name)
    return existing
      ? { ...existing, required: true }
      : { ...blankRow(), name, required: true }
  })
}

export function jsonText(value: unknown) {
  if (value === null || value === undefined) return ''
  return JSON.stringify(value, null, 2)
}

export function parseJsonText(text: string):
  | { valid: true; value: unknown }
  | { valid: false; error: string } {
  if (!text.trim()) return { valid: true, value: null }
  try {
    return { valid: true, value: JSON.parse(text) }
  } catch (error) {
    return {
      valid: false,
      error: error instanceof Error ? error.message : 'JSON 格式不正确',
    }
  }
}

export function splitTags(value: string) {
  return value
    .split(/[,，]/)
    .map(tag => tag.trim())
    .filter(Boolean)
}

export function sameRows(left: InterfaceRow[], right: InterfaceRow[]) {
  return JSON.stringify(left) === JSON.stringify(right)
}
