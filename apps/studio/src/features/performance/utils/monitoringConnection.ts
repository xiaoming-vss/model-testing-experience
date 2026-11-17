import type {
  CreateMonitoringConnectionPayload,
  MonitoringAuthPayload,
  MonitoringAuthType,
  MonitoringConnection,
  UpdateMonitoringConnectionPayload,
} from '../types'

export type MonitoringConnectionFormValues = {
  name: string
  queryUrl: string
  remoteWriteUrl: string
  queryAuthType: MonitoringAuthType
  queryUsername?: string
  queryPassword?: string
  queryToken?: string
  queryHeadersJson?: string
  remoteWriteAuthType: MonitoringAuthType
  remoteWriteUsername?: string
  remoteWritePassword?: string
  remoteWriteToken?: string
  remoteWriteHeadersJson?: string
  grafanaUrl?: string
  grafanaDashboardUid?: string
  defaultFiltersJson?: string
  enabled: boolean
}

function parseJsonObject(value: string, message: string) {
  let parsed: unknown
  try {
    parsed = JSON.parse(value)
  } catch {
    throw new Error(message)
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error(message)
  return parsed as Record<string, unknown>
}

function parseHeaders(value: string | undefined) {
  if (!value?.trim()) return {}
  const parsed = parseJsonObject(value, '认证 Headers 必须是 JSON 对象')
  const headers: Record<string, string> = {}
  for (const [name, headerValue] of Object.entries(parsed)) {
    if (typeof headerValue !== 'string') throw new Error('认证 Headers 的值必须是字符串')
    headers[name] = headerValue
  }
  return headers
}

function parseFilters(value: string | undefined) {
  if (!value?.trim()) return {}
  return parseJsonObject(value, '默认筛选必须是 JSON 对象')
}

function authPayload(
  prefix: 'query' | 'remoteWrite',
  values: MonitoringConnectionFormValues,
  editing: MonitoringConnection | null,
): MonitoringAuthPayload | undefined {
  const type = values[`${prefix}AuthType`]
  const existingType = editing?.[`${prefix}AuthType`]
  const hasExisting = prefix === 'query'
    ? Boolean(editing?.hasQueryCredentials)
    : Boolean(editing?.hasRemoteWriteCredentials)
  if (type === 'none') {
    return editing && existingType === 'none' ? undefined : { type: 'none' }
  }
  if (type === 'basic') {
    const username = (values[`${prefix}Username`] || '').trim()
    const password = values[`${prefix}Password`] || ''
    if (editing && type === existingType && hasExisting && !password) return undefined
    if (!username) throw new Error('Basic 认证必须填写用户名')
    if (!password) throw new Error('Basic 认证必须填写密码')
    return { type, username, password }
  }
  if (type === 'bearer') {
    const token = values[`${prefix}Token`] || ''
    if (editing && type === existingType && hasExisting && !token) return undefined
    if (!token) throw new Error('Bearer 认证必须填写 Token')
    return { type, token }
  }
  const headersJson = values[`${prefix}HeadersJson`]
  if (editing && type === existingType && hasExisting && !headersJson?.trim()) return undefined
  const headers = parseHeaders(headersJson)
  if (Object.keys(headers).length === 0) throw new Error('Headers 认证至少需要一个 Header')
  return { type, headers }
}

export function buildMonitoringConnectionPayload(
  values: MonitoringConnectionFormValues,
  editing: MonitoringConnection | null,
): CreateMonitoringConnectionPayload | UpdateMonitoringConnectionPayload {
  const queryAuth = authPayload('query', values, editing)
  const remoteWriteAuth = authPayload('remoteWrite', values, editing)
  return {
    name: values.name.trim(),
    queryUrl: values.queryUrl.trim(),
    remoteWriteUrl: values.remoteWriteUrl.trim(),
    ...(queryAuth ? { queryAuth } : {}),
    ...(remoteWriteAuth ? { remoteWriteAuth } : {}),
    grafanaUrl: values.grafanaUrl?.trim() || '',
    grafanaDashboardUid: values.grafanaDashboardUid?.trim() || '',
    defaultFilters: parseFilters(values.defaultFiltersJson),
    enabled: values.enabled,
  }
}
