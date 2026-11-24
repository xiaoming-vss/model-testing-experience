export type InterfaceAuthSummary = {
  hasAuth: boolean
  label: string
  hint: string
}

type SecurityScheme = Record<string, unknown>

const NO_AUTH: InterfaceAuthSummary = {
  hasAuth: false,
  label: '未声明认证',
  hint: '生成 API 用例时不附加认证头。',
}

function isRecord(value: unknown): value is SecurityScheme {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readString(record: SecurityScheme, key: string) {
  const value = record[key]
  return typeof value === 'string' ? value.trim() : ''
}

/** OpenAPI security 中声明的方案名；scheme 详情缺失时仍能提示需要认证。 */
function declaredSchemeNames(security: unknown): string[] {
  if (!Array.isArray(security)) return []
  const names = new Set<string>()
  security.forEach(requirement => {
    if (!isRecord(requirement)) return
    Object.keys(requirement).forEach(name => names.add(name))
  })
  return [...names]
}

function schemeLabel(name: string, scheme: SecurityScheme) {
  const type = readString(scheme, 'type')
  const httpScheme = readString(scheme, 'scheme')
  if (type === 'http') {
    if (httpScheme === 'bearer') return 'Bearer Token'
    if (httpScheme === 'basic') return 'Basic Auth'
    return 'HTTP Auth'
  }
  if (type === 'apiKey') return 'API Key'
  if (type === 'oauth2') return 'OAuth 2.0'
  if (type === 'openIdConnect') return 'OpenID Connect'
  return name || type || '已声明认证'
}

function schemeHint(scheme: SecurityScheme) {
  const type = readString(scheme, 'type')
  const httpScheme = readString(scheme, 'scheme')
  if (type === 'http') {
    if (httpScheme === 'bearer') return 'Authorization: Bearer {token}'
    if (httpScheme === 'basic') return 'Authorization: Basic {credentials}'
    return httpScheme ? `认证方案：${httpScheme}` : '由 HTTP 认证保护。'
  }
  if (type === 'apiKey') {
    const location = readString(scheme, 'in')
    const parameter = readString(scheme, 'name')
    const where =
      location === 'header' ? '请求头'
        : location === 'query' ? '查询参数'
          : location === 'cookie' ? 'Cookie'
            : location
    if (!where && !parameter) return '由 API Key 保护。'
    return `参数位于${where || '请求'}${parameter ? `：${parameter}` : ''}`
  }
  if (type === 'oauth2') return '由 OAuth 2.0 流程获取访问令牌。'
  if (type === 'openIdConnect') return '由 OpenID Connect 流程获取访问令牌。'
  return '生成 API 用例时用于补充认证头。'
}

/**
 * 将 OpenAPI 的 security / securitySchemes 快照压成设置页可读的一行摘要。
 * 原始 JSON 仍由调用方按需展开，不在默认视图里暴露。
 */
export function describeInterfaceAuth(security: unknown, schemes: unknown): InterfaceAuthSummary {
  const entries = isRecord(schemes)
    ? Object.entries(schemes).filter((entry): entry is [string, SecurityScheme] => isRecord(entry[1]))
    : []

  if (entries.length === 0) {
    const names = declaredSchemeNames(security)
    if (names.length === 0) return NO_AUTH
    return {
      hasAuth: true,
      label: names.length === 1 ? names[0] : `${names.length} 种认证`,
      hint:
        names.length === 1
          ? '生成 API 用例时用于补充认证头。'
          : `包含 ${names.join('、')}；生成 API 用例时用于补充认证头。`,
    }
  }

  if (entries.length === 1) {
    const [name, scheme] = entries[0]
    return { hasAuth: true, label: schemeLabel(name, scheme), hint: schemeHint(scheme) }
  }

  const labels = entries.map(([name, scheme]) => schemeLabel(name, scheme))
  return {
    hasAuth: true,
    label: `${labels.length} 种认证`,
    hint: `包含 ${labels.join('、')}；生成 API 用例时按需补充认证头。`,
  }
}
