import type {
  CreateMonitoringConnectionPayload,
  MonitoringAuthPayload,
  MonitoringAuthType,
  MonitoringConnection,
  UpdateMonitoringConnectionPayload,
} from '../types'

export type MonitoringConnectionFormValues = {
  name: string
  remoteWriteUrl: string
  remoteWriteAuthType: MonitoringAuthType
  remoteWriteUsername?: string
  remoteWritePassword?: string
  remoteWriteToken?: string
  remoteWriteHeadersJson?: string
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

function authPayload(
  values: MonitoringConnectionFormValues,
  editing: MonitoringConnection | null,
): MonitoringAuthPayload | undefined {
  const type = values.remoteWriteAuthType
  const existingType = editing?.remoteWriteAuthType
  const hasExisting = Boolean(editing?.hasRemoteWriteCredentials)
  if (type === 'none') {
    return editing && existingType === 'none' ? undefined : { type: 'none' }
  }
  if (type === 'basic') {
    const username = (values.remoteWriteUsername || '').trim()
    const password = values.remoteWritePassword || ''
    if (editing && type === existingType && hasExisting && !password) return undefined
    if (!username) throw new Error('Basic 认证必须填写用户名')
    if (!password) throw new Error('Basic 认证必须填写密码')
    return { type, username, password }
  }
  if (type === 'bearer') {
    const token = values.remoteWriteToken || ''
    if (editing && type === existingType && hasExisting && !token) return undefined
    if (!token) throw new Error('Bearer 认证必须填写 Token')
    return { type, token }
  }
  const headersJson = values.remoteWriteHeadersJson
  if (editing && type === existingType && hasExisting && !headersJson?.trim()) return undefined
  const headers = parseHeaders(headersJson)
  if (Object.keys(headers).length === 0) throw new Error('Headers 认证至少需要一个 Header')
  return { type, headers }
}

export function buildMonitoringConnectionPayload(
  values: MonitoringConnectionFormValues,
  editing: MonitoringConnection | null,
): CreateMonitoringConnectionPayload | UpdateMonitoringConnectionPayload {
  const remoteWriteAuth = authPayload(values, editing)
  return {
    name: values.name.trim(),
    remoteWriteUrl: values.remoteWriteUrl.trim(),
    ...(remoteWriteAuth ? { remoteWriteAuth } : {}),
    enabled: values.enabled,
  }
}
