import { Alert, Button, Form, Input, Typography } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '@/services/api'
import { TestPilotLogo } from '@/shared/components/TestPilotLogo/TestPilotLogo'
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
  const from = (location.state as { from?: Location } | null)?.from?.pathname ?? '/projects'

  const mutation = useMutation({
    mutationFn: async (values: { name: string; password: string; email?: string }) => {
      if (isLogin) {
        return api.login({ name: values.name, password: values.password })
      }
      await api.register(values)
      return null
    },
    onSuccess: (data) => {
      if (isLogin && data) {
        setToken(data.accessToken)
        message.success('登录成功')
        navigate(from, { replace: true })
      } else {
        message.success('注册成功，请登录')
        navigate('/login', { replace: true })
      }
    },
  })

  return (
    <div className="auth-page">
      <main className="auth-main" aria-label={isLogin ? '登录 MTX' : '注册 MTX'}>
        <section className="auth-shell">
          <aside className="auth-brand-panel" aria-label="MTX">
            <TestPilotLogo size={58} title="MTX Logo" />
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

            {mutation.error ? <Alert showIcon type="error" title={getErrorMessage(mutation.error)} /> : null}

            <Form form={form} layout="vertical" onFinish={(values) => mutation.mutate(values)} requiredMark={false} className="auth-form">
              <Form.Item name="name" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
                <Input placeholder="请输入用户名" autoComplete="username" />
              </Form.Item>

              <Form.Item
                name="password"
                label={
                  <span className="auth-password-label">
                    <span>密码</span>
                    {isLogin ? (
                      <Button type="link" className="auth-forgot" onClick={() => message.info('暂未开放')}>
                        忘记密码？
                      </Button>
                    ) : null}
                  </span>
                }
                rules={[{ required: true, message: '请输入密码' }]}
              >
                <Input.Password placeholder="请输入密码" autoComplete={isLogin ? 'current-password' : 'new-password'} />
              </Form.Item>

              {!isLogin ? (
                <Form.Item name="email" label="邮箱">
                  <Input placeholder="请输入邮箱" autoComplete="email" />
                </Form.Item>
              ) : null}

              {isLogin ? (
                <label className="auth-remember">
                  <input type="checkbox" />
                  <span>保持登录</span>
                </label>
              ) : null}

              <Button type="primary" htmlType="submit" block loading={mutation.isPending} className="auth-submit">
                {isLogin ? '登录' : '注册'}
              </Button>
            </Form>

            <div className="auth-switch">
              <Text type="secondary">{isLogin ? '还没有账号？' : '已有账号？'}</Text>
              <Button type="link" onClick={() => navigate(isLogin ? '/register' : '/login')}>
                {isLogin ? '立即注册' : '返回登录'}
              </Button>
            </div>
          </section>
        </section>
        <footer className="auth-footer">© 2026 MTX. 版权所有</footer>
      </main>
    </div>
  )
}
