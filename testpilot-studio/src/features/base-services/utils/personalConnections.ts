export function normalizeInstanceUrl(value: string) {
  try {
    const url = new URL(value)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return ''
    return `${url.origin}${url.pathname.replace(/\/+$/, '')}`
  } catch { return '' }
}
export function personalConnectionForInstance<T extends { connectionId: string; baseUrl: string; status: string }>(connections: T[], instance: string, selected?: string) {
  const normalized = normalizeInstanceUrl(instance)
  if (!normalized) return undefined
  const candidates = connections.filter(c => c.status === 'active' && normalizeInstanceUrl(c.baseUrl) === normalized)
  return selected ? candidates.find(c => c.connectionId === selected) : candidates.length === 1 ? candidates[0] : undefined
}
