import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { api } from '@/services/api'
import { AuthPage } from './AuthPage'
import { useAuthStore } from '../store/auth.store'
import { ProfilePage } from '@/features/profile/pages/ProfilePage'

function page(mode: 'login' | 'register' = 'login') {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><AuthPage mode={mode} /></MemoryRouter>
  </QueryClientProvider>)
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); useAuthStore.setState({ user: null }) })

describe('LDAP authentication UI', () => {
  it('defaults to LDAP, sends explicit method, and clears password when changing entry', async () => {
    vi.spyOn(api, 'getAuthConfig').mockResolvedValue({ ldapEnabled: true, registrationEnabled: false, localLoginAdminOnly: true })
    const login = vi.spyOn(api, 'login').mockRejectedValue(new Error('凭据错误'))
    page()
    expect(await screen.findByRole('radio', { name: 'LDAP 登录' })).toBeChecked()
    expect(screen.queryByText('立即注册')).not.toBeInTheDocument()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('用户名'), 'alice')
    await user.type(screen.getByLabelText('密码'), 'directory-password')
    await user.click(screen.getByRole('button', { name: '登 录' }))
    await waitFor(() => expect(login).toHaveBeenCalledWith({ name: 'alice', password: 'directory-password', authMethod: 'ldap' }))
    await screen.findByText('凭据错误')
    await user.click(screen.getByText('本地登录'))
    expect(screen.getByLabelText('密码')).toHaveValue('')
    expect(screen.getByText('本地登录仅系统管理员使用')).toBeInTheDocument()
  })

  it('blocks direct registration when LDAP is enabled', async () => {
    vi.spyOn(api, 'getAuthConfig').mockResolvedValue({ ldapEnabled: true, registrationEnabled: false, localLoginAdminOnly: true })
    page('register')
    expect(await screen.findByText('当前不开放自助注册')).toBeInTheDocument()
    expect(screen.queryByLabelText('密码')).not.toBeInTheDocument()
    expect(screen.getByText('返回登录')).toBeInTheDocument()
  })

  it('configuration failure keeps local admin login and hides registration', async () => {
    vi.spyOn(api, 'getAuthConfig').mockRejectedValue(new Error('offline'))
    page()
    expect(await screen.findByText('无法读取登录配置，暂不开放注册')).toBeInTheDocument()
    expect(screen.getByLabelText('用户名')).toBeInTheDocument()
    expect(screen.getByText('本地登录仅系统管理员使用')).toBeInTheDocument()
    expect(screen.queryByText('立即注册')).not.toBeInTheDocument()
  })

  it('LDAP profile remains read-only independently of login configuration', () => {
    useAuthStore.setState({ user: { name: 'alice', email: 'alice@test', authSource: 'ldap' } })
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><ProfilePage /></MemoryRouter></QueryClientProvider>)
    expect(screen.getByText('LDAP 用户')).toBeInTheDocument()
    expect(screen.getByLabelText('邮箱')).toBeDisabled()
    expect(screen.queryByText('保存修改')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('当前密码')).not.toBeInTheDocument()
  })
})
