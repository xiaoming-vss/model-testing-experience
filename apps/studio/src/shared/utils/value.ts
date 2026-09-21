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
