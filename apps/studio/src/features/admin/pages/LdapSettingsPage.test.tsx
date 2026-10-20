import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { ldapApi, type LdapSettings } from '../api/ldap.api'
import { LdapSettingsPage } from './LdapSettingsPage'

const settings: LdapSettings = {
  generation: 2, source: 'database', passwordConfigured: true,
  config: {
    enabled: false, server_url: 'ldap://directory.test', start_tls: true, allow_insecure_connection: false,
    tls_ca_file: '', tls_ca_pem: '', bind_dn: 'uid=reader,dc=test', user_search_base: 'dc=test',
    user_search_filter: '(uid={username})', access_group_dn: 'cn=users,dc=test', username_attribute: 'uid',
    email_attribute: 'mail', external_id_attribute: 'entryUUID', group_member_attribute: 'memberUid',
    group_member_value_type: 'username', timeout_seconds: 5, login_timeout_seconds: 30,
    reconcile_interval_seconds: 300, auto_link_by_username: false, token_expire_hours: 12,
    directory_rules_verified: true, active_user_filter: '(state=active)', disabled_user_filter: '(state=disabled)',
  },
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })
function renderPage() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><LdapSettingsPage /></QueryClientProvider>)
}
it('loads masked password and tests without saving', async () => {
  vi.spyOn(api, 'getUser').mockResolvedValue({ name: 'root', isSuperAdmin: true })
  vi.spyOn(ldapApi, 'get').mockResolvedValue(settings)
  const check = vi.spyOn(ldapApi, 'test').mockResolvedValue({ connected: true, message: '连接通过' })
  const save = vi.spyOn(ldapApi, 'save')
  renderPage()
  expect(await screen.findByLabelText('查询密码')).toHaveValue('')
  await userEvent.click(screen.getByRole('button', { name: '检查连接' }))
  await screen.findByText('连接通过')
  expect(check).toHaveBeenCalledOnce()
  expect(save).not.toHaveBeenCalled()
})
it('requires confirmation to enable and saves generation', async () => {
  vi.spyOn(api, 'getUser').mockResolvedValue({ name: 'root', isSuperAdmin: true })
  vi.spyOn(ldapApi, 'get').mockResolvedValue(settings)
  const save = vi.spyOn(ldapApi, 'save').mockResolvedValue({ ...settings, source: 'database', generation: 3, config: { ...settings.config, enabled: true } })
  renderPage()
  await screen.findByLabelText('查询密码')
  await userEvent.click(screen.getByRole('switch', { name: '启用 LDAP' }))
  await userEvent.click(screen.getByRole('button', { name: '保存并生效' }))
  expect(await screen.findByText('确认启用 LDAP')).toBeInTheDocument()
  expect(save).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '确认并保存' }))
  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ generation: 2, config: expect.objectContaining({ enabled: true }) })))
})
it('ordinary accounts cannot load settings', async () => {
  vi.spyOn(api, 'getUser').mockResolvedValue({ name: 'ordinary', isSuperAdmin: false })
  const get = vi.spyOn(ldapApi, 'get')
  renderPage()
  expect(await screen.findByText('仅系统管理员可以管理 LDAP')).toBeInTheDocument()
  expect(get).not.toHaveBeenCalled()
})
