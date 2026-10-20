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
import { useAuthStore } from '../store/auth.store'

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
    <div className="auth-page">
      <div className="auth-theme-select"><ThemeSelect /></div>
      <main className="auth-main" aria-label={isLogin ? '登录 MTX' : '注册 MTX'}>
        <section className="auth-shell">
          <aside className="auth-brand-panel" aria-label="MTX">
            <MtxLogo size={58} title="MTX Logo" />
            <div className="auth-brand-copy">
              <strong className="auth-brand-name">MTX</strong>
              <span className="auth-brand-subtitle">Model Testing Experience</span>
              <p>让模型贯穿测试设计与执行</p>
            </div>
            <div className="auth-capability-list" aria-hidden="true">
              <span><i className="auth-dot auth-dot-blue" />项目总览</span>
              <span><i className="auth-dot auth-dot-teal" />AI 测试</span>
              <span><i className="auth-dot" />基础服务</span>
            </div>
          </aside>

          <section className="auth-form-panel">
            <div className="auth-title">
              <h1>{isLogin ? '欢迎回来' : '创建账号'}</h1>
              <Text>{isLogin ? '登录后继续你的测试设计工作' : '创建账号，开始你的模型测试体验'}</Text>
            </div>

            {configQuery.isError ? <Alert showIcon type="warning" title="无法读取登录配置，暂不开放注册" description="系统管理员仍可使用本地登录。" action={<Button onClick={() => { void configQuery.refetch() }}>重试</Button>} /> : null}
            {isLogin && ldapEnabled ? <Radio.Group
              aria-label="登录方式"
              className="auth-method-switch"
              value={authMethod}
              disabled={mutation.isPending}
              onChange={(event) => { setChosenMethod(event.target.value as AuthMethod); form.setFieldValue('password', ''); mutation.reset() }}
              options={[{ value: 'ldap', label: 'LDAP 登录' }, { value: 'local', label: '本地登录' }]}
              optionType="button"
            /> : null}
            {isLogin && authMethod === 'local' && adminOnly ? <Text className="auth-login-hint">本地登录仅系统管理员使用</Text> : null}
            {!isLogin && !registrationEnabled ? <Alert type="info" showIcon title={configQuery.isPending ? '正在读取注册配置' : '当前不开放自助注册'} /> : null}
            {mutation.error ? <Alert showIcon type="error" title={getErrorMessage(mutation.error)} /> : null}

            {isLogin || registrationEnabled ? <Form form={form} layout="vertical" onFinish={(values) => mutation.mutate(values)} requiredMark={false} className="auth-form">
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
                <Text type="secondary" className="auth-forgot-hint">
                  {authMethod === 'ldap' ? '密码问题请到公司统一账号系统处理' : adminOnly ? '管理员密码丢失请联系运维恢复' : '忘记密码请联系系统管理员重置'}
                </Text>
              )}

              <Button type="primary" htmlType="submit" block loading={mutation.isPending} className="auth-submit">
                {isLogin ? '登录' : '注册'}
              </Button>
            </Form> : null}

            {!isLogin || registrationEnabled ? <div className="auth-switch">
              <Text type="secondary">{isLogin ? '还没有账号？' : '已有账号？'}</Text>
              <Button type="link" onClick={() => navigate(isLogin ? '/register' : '/login')}>
                {isLogin ? '立即注册' : '返回登录'}
              </Button>
            </div> : null}
          </section>
        </section>
        <footer className="auth-footer">© 2026 MTX. 版权所有</footer>
      </main>
    </div>
  )
}
