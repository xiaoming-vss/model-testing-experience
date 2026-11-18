import { useState } from 'react'
import type { AuthMethod } from '../types'
import { ThemeSelect } from '@/shared/components/ThemeSelect'
import { Alert, Button, Form, Input, Radio, Typography } from 'antd'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '@/services/api'
import { MtxLogo } from '@/shared/components/MtxLogo/MtxLogo'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { cx } from '@/shared/utils/cx'
import { useAuthStore } from '../store/auth.store'
import styles from '@/shared/styles/account.module.css'

const { Text } = Typography

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const navigate = useNavigate()
  const location = useLocation()
  const setToken = useAuthStore((state) => state.setToken)
  const [form] = Form.useForm()
  const isLogin = mode === 'login'
  const [chosenMethod, setChosenMethod] = useState<AuthMethod>()
  const configQuery = useQuery({ queryKey: ['authConfig'], queryFn: api.getAuthConfig, retry: false })
  const ldapEnabled = configQuery.data?.ldapEnabled === true
  const registrationEnabled = configQuery.isSuccess && configQuery.data.registrationEnabled
  const authMethod: AuthMethod = ldapEnabled ? (chosenMethod ?? 'ldap') : 'local'
  const adminOnly = !configQuery.isSuccess || configQuery.data.localLoginAdminOnly
  const from = (location.state as { from?: Location } | null)?.from?.pathname ?? '/projects'

  const mutation = useMutation({
    mutationFn: async (values: { name: string; password: string; email?: string }) => {
      if (isLogin) {
        return api.login({ name: values.name, password: values.password, authMethod })
      }
      if (!registrationEnabled) throw new Error('当前不允许自助注册')
      await api.register({
        name: values.name,
        password: values.password,
        email: values.email ?? '',
      })
      return null
    },
    onSuccess: (data) => {
      if (isLogin && data) {
        setToken(data.accessToken)
        message.success('登录成功')
        navigate(data.mustChangePassword ? '/change-password' : from, { replace: true })
      } else {
        message.success('注册成功，请登录')
        navigate('/login', { replace: true })
      }
    },
  })

  return (
    <div className={cx('auth-page', styles.page, 'relative grid min-h-screen place-items-center overflow-hidden px-6 py-12 text-[var(--app-auth-text)] [background:linear-gradient(180deg,var(--app-auth-gradient-start),var(--app-auth-gradient-end)),var(--app-profile-surface)] max-narrow:px-4 max-narrow:py-6')}>
      <div className="fixed right-4 top-4 z-10"><ThemeSelect /></div>
      <main className="relative z-[1] flex w-full max-w-[930px] flex-col items-center gap-6 max-narrow:max-w-[430px]" aria-label={isLogin ? '登录 MTX' : '注册 MTX'}>
        <section className={cx('auth-shell', styles.shell, 'grid min-h-[620px] w-full grid-cols-[408px_minmax(0,1fr)] overflow-hidden max-narrow:min-h-0 max-narrow:grid-cols-1')}>
          <aside className={cx('auth-brand-panel', styles.brandPanel, 'flex min-w-0 flex-col border-r border-[var(--app-auth-panel-divider)] [background:linear-gradient(90deg,var(--app-auth-aside-bg),var(--app-glass-surface-36)),var(--app-glass-surface-24)] px-14 pt-28 pb-[58px] max-narrow:px-7 max-narrow:pt-[34px] max-narrow:pb-7')} aria-label="MTX">
            <MtxLogo size={58} title="MTX Logo" />
            <div className="mt-6 max-narrow:mt-[18px]">
              <strong className="auth-brand-name block font-sans text-[46px] leading-[54px] text-[var(--app-auth-text)] [font-weight:750] max-narrow:text-[38px] max-narrow:leading-[44px]">MTX</strong>
              <span className="auth-brand-subtitle mt-1 block font-sans text-[13px] leading-5 text-[var(--app-auth-text-secondary)]">Model Testing Experience</span>
              <p className="mt-[30px] text-[15px] leading-6 text-[var(--app-auth-text-secondary)] max-narrow:mt-5">让模型贯穿测试设计与执行</p>
            </div>
            <div className="mt-auto grid w-full max-narrow:hidden" aria-hidden="true">
              <span className={cx('flex min-h-[50px] items-center gap-3 border-b border-[var(--app-glass-border-strong)] text-xs text-[var(--app-auth-text-muted)]')}><i className="h-2 w-2 flex-none rounded-full bg-[var(--app-auth-dot-primary)]" />项目总览</span>
              <span className={cx('flex min-h-[50px] items-center gap-3 border-b border-[var(--app-glass-border-strong)] text-xs text-[var(--app-auth-text-muted)]')}><i className="h-2 w-2 flex-none rounded-full bg-[var(--app-auth-dot-secondary)]" />AI 测试</span>
              <span className={cx('flex min-h-[50px] items-center gap-3 border-b border-[var(--app-glass-border-strong)] text-xs text-[var(--app-auth-text-muted)]')}><i className="h-2 w-2 flex-none rounded-full bg-[var(--app-auth-dot-neutral)]" />基础服务</span>
            </div>
          </aside>

          <section className="flex min-w-0 flex-col px-[86px] pt-[120px] pb-[54px] max-narrow:px-7 max-narrow:pt-[34px] max-narrow:pb-[30px]">
            <div className="mb-[30px] w-full">
              <h1 className={cx(styles.title, 'm-0 text-[24px] font-bold leading-[34px]')}>{isLogin ? '欢迎回来' : '创建账号'}</h1>
              <Text className="text-sm leading-[22px] text-[var(--app-auth-text-secondary)]">{isLogin ? '登录后继续你的测试设计工作' : '创建账号，开始你的模型测试体验'}</Text>
            </div>

            {configQuery.isError ? <Alert showIcon type="warning" title="无法读取登录配置，暂不开放注册" description="系统管理员仍可使用本地登录。" action={<Button onClick={() => { void configQuery.refetch() }}>重试</Button>} /> : null}
            {isLogin && ldapEnabled ? <Radio.Group
              aria-label="登录方式"
              className="mb-4"
              value={authMethod}
              disabled={mutation.isPending}
              onChange={(event) => { setChosenMethod(event.target.value as AuthMethod); form.setFieldValue('password', ''); mutation.reset() }}
              options={[{ value: 'ldap', label: 'LDAP 登录' }, { value: 'local', label: '本地登录' }]}
              optionType="button"
            /> : null}
            {isLogin && authMethod === 'local' && adminOnly ? <Text className="mb-4 block">本地登录仅系统管理员使用</Text> : null}
            {!isLogin && !registrationEnabled ? <Alert type="info" showIcon title={configQuery.isPending ? '正在读取注册配置' : '当前不开放自助注册'} /> : null}
            {mutation.error ? <Alert showIcon type="error" title={getErrorMessage(mutation.error)} /> : null}

            {isLogin || registrationEnabled ? <Form form={form} layout="vertical" onFinish={(values) => mutation.mutate(values)} requiredMark={false} className={cx('auth-form', styles.form, 'w-full')}>
              <Form.Item name="name" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
                <Input placeholder="请输入用户名" autoComplete="username" />
              </Form.Item>

              <Form.Item
                name="password"
                label="密码"
                rules={[
                  { required: true, message: '请输入密码' },
                  ...(!isLogin ? [{ min: 10, message: '密码至少需要 10 个字符' }] : []),
                ]}
              >
                <Input.Password placeholder="请输入密码" autoComplete={isLogin ? 'current-password' : 'new-password'} />
              </Form.Item>

              {!isLogin ? (
                <Form.Item
                  name="email"
                  label="邮箱"
                  rules={[{ required: true, message: '请输入邮箱' }]}
                >
                  <Input placeholder="请输入邮箱" autoComplete="email" />
                </Form.Item>
              ) : (
                <Text type="secondary" className="-mt-1 mb-5 block text-xs">
                  {authMethod === 'ldap' ? '密码问题请到公司统一账号系统处理' : adminOnly ? '管理员密码丢失请联系运维恢复' : '忘记密码请联系系统管理员重置'}
                </Text>
              )}

              <Button type="primary" htmlType="submit" block loading={mutation.isPending} className={cx('auth-submit', styles.submit)}>
                {isLogin ? '登录' : '注册'}
              </Button>
            </Form> : null}

            {!isLogin || registrationEnabled ? <div className={cx('auth-switch', styles.switch, 'mt-[30px] flex items-center justify-center gap-1.5 border-t border-[var(--app-glass-border-strong)] pt-[22px] text-xs')}>
              <Text type="secondary" className="text-[var(--app-auth-text-muted)]">{isLogin ? '还没有账号？' : '已有账号？'}</Text>
              <Button type="link" onClick={() => navigate(isLogin ? '/register' : '/login')}>
                {isLogin ? '立即注册' : '返回登录'}
              </Button>
            </div> : null}
          </section>
        </section>
        <footer className="auth-footer text-center text-xs leading-5 text-[var(--app-auth-meta)]">© 2026 MTX. 版权所有</footer>
      </main>
    </div>
  )
}
