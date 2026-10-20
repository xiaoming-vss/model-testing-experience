import { cleanup, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AccountManagementPage } from './AccountManagementPage'
import { adminApi } from '../api/admin.api'
import type { AdminUser } from '../types'


afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('labels LDAP and pending users while retaining governance actions', async () => {
  const users: AdminUser[] = [
    { userId: '1', name: 'directory-user', authSource: 'ldap', status: 'active', isSuperAdmin: false, mustChangePassword: false },
    { userId: '2', name: 'pending-user', authSource: 'local', status: 'pending_ldap', isSuperAdmin: false, mustChangePassword: false },
  ]
  vi.spyOn(adminApi, 'listUsers').mockResolvedValue(Object.assign([...users], { items: users, total: 2 }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(['user'], { userId: 'admin', name: 'admin', isSuperAdmin: true })
  render(<QueryClientProvider client={client}><MemoryRouter><AccountManagementPage /></MemoryRouter></QueryClientProvider>)
  const name = await screen.findByText('directory-user')
  const row = within(name.closest('tr')!)
  expect(row.getByText('LDAP 用户')).toBeInTheDocument()
  expect(row.queryByText('重置密码')).not.toBeInTheDocument()
  expect(row.queryByText('修改邮箱')).not.toBeInTheDocument()
  expect(row.getByText('禁用')).toBeInTheDocument()
  expect(row.getByText('删除')).toBeInTheDocument()
  const pending = within(screen.getByText('pending-user').closest('tr')!)
  expect(pending.getByText('待 LDAP 关联')).toBeInTheDocument()
  expect(pending.getByText('启用')).toBeInTheDocument()
  expect(pending.getByText('禁用')).toBeInTheDocument()
})
