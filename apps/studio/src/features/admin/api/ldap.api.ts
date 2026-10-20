import { request } from '@/shared/api/request'

export type LdapConfig = {
  enabled: boolean
  server_url: string
  start_tls: boolean
  allow_insecure_connection: boolean
  tls_ca_file: string
  tls_ca_pem: string
  bind_dn: string
  bind_password?: string
  user_search_base: string
  user_search_filter: string
  access_group_dn: string
  username_attribute: string
  email_attribute: string
  external_id_attribute: string
  group_member_attribute: string
  group_member_value_type: string
  timeout_seconds: number
  login_timeout_seconds: number
  reconcile_interval_seconds: number
  auto_link_by_username: boolean
  token_expire_hours: number
  directory_rules_verified: boolean
  active_user_filter: string
  disabled_user_filter: string
}
export type LdapSettings = {
  generation: number
  source: 'database'
  passwordConfigured: boolean
  config: LdapConfig
}
export type LdapTest = { connected: boolean; message: string; userFound?: boolean; eligible?: boolean; emailPresent?: boolean }
export const ldapApi = {
  get: () => request<LdapSettings>('/v1/admin/ldap'),
  save: (body: { generation: number; config: LdapConfig; clearPassword: boolean }) =>
    request<LdapSettings>('/v1/admin/ldap', { method: 'PUT', body: JSON.stringify(body) }),
  test: (body: { config: LdapConfig; username?: string; clearPassword: boolean }) =>
    request<LdapTest>('/v1/admin/ldap/test', { method: 'POST', body: JSON.stringify(body) }),
}
