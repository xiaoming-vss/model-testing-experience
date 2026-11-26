export function parseMaybeJsonValue(value: unknown) {
  if (typeof value !== 'string') return value
  if (!value.trim()) return ''

  try {
    return JSON.parse(value) as unknown
  } catch {
    return value
  }
}

export function prettyPrintValue(value: unknown) {
  const normalized = parseMaybeJsonValue(value)

  if (normalized === '' || normalized === undefined || normalized === null) {
    return ''
  }

  if (typeof normalized === 'string') {
    return normalized
  }

  try {
    return JSON.stringify(normalized, null, 2)
  } catch {
    return String(normalized)
  }
}

export function formatOptionalValue(value: unknown) {
  if (value === undefined || value === null || value === '') return '-'
  return String(value)
}

export function formatStructuredContent(value?: unknown) {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

export function toRecordArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
}

export function parseJsonRecord(value: unknown): Record<string, unknown> | null {
  try {
    return toRecord(typeof value === 'string' ? JSON.parse(value) as unknown : value)
  } catch {
    return null
  }
}

export function isJsonText(value?: string, { allowEmpty = true }: { allowEmpty?: boolean } = {}) {
  if (!value?.trim()) return allowEmpty
  try {
    JSON.parse(value)
    return true
  } catch {
    return false
  }
}

export function formatBytes(bytes: number, fractionDigits = 2) {
  if (!Number.isFinite(bytes) || bytes < 0) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(fractionDigits)} KB`
  return `${(bytes / 1024 / 1024).toFixed(fractionDigits)} MB`
}

export async function copyText(text: string, options: { success?: string } = {}) {
  const { message } = await import('./feedback')
  try {
    await navigator.clipboard.writeText(text)
    message.success(options.success ?? '已复制')
    return true
  } catch {
    message.error('复制失败，请重试或手动复制')
    return false
  }
}
