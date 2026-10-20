import { Alert, Button, Form, Input, Typography } from 'antd'
import { LockOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import '@/features/profile/pages/ProfilePage.css'
import '@/features/auth/styles/change-password.css'

const { Title, Paragraph } = Typography

export function ChangePasswordPage() {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const [form] = Form.useForm()
  const forced = Boolean(user?.mustChangePassword ?? user?.must_change_password)

  const mutation = useMutation({
    mutationFn: api.changePassword,
    onSuccess: () => {
      message.success('密码已修改，请使用新密码重新登录')
      logout()
      navigate('/login', { replace: true })
    },
  })

  if (user?.authSource === 'ldap') {
    return <Alert showIcon type="info" title="LDAP 密码由公司统一账号系统管理" />
  }

  return (
    <main className="profile-settings profile-settings-change-password">
      <div className="profile-settings-container">
        <header className="profile-settings-heading">
          <Title level={2}>{forced ? '首次登录请修改密码' : '修改密码'}</Title>
          <Paragraph type="secondary">
            {forced
              ? '系统管理员账号首次登录必须修改初始密码，修改成功后需要重新登录。'
              : '修改成功后所有已登录会话都会失效，需要使用新密码重新登录。'}
          </Paragraph>
        </header>
        <div className="profile-settings-grid">
          <section className="profile-settings-panel" aria-labelledby="change-password-heading">
            <header className="profile-settings-panel-heading">
              <Title level={3} id="change-password-heading">密码</Title>
              <Paragraph type="secondary">新密码至少 10 个字符，不能与当前密码相同。</Paragraph>
            </header>
            {mutation.error ? <Alert className="profile-settings-error" showIcon type="error" title={getErrorMessage(mutation.error)} /> : null}
            <Form
              form={form}
              layout="vertical"
              onFinish={(values) => mutation.mutate({ oldPassword: values.oldPassword, newPassword: values.newPassword })}
              requiredMark={false}
              className="profile-settings-form"
            >
              <div className="profile-settings-fields">
                <Form.Item name="oldPassword" label="当前密码" rules={[{ required: true, message: '请输入当前密码' }]}>
                  <Input.Password placeholder="请输入当前密码" autoComplete="current-password" prefix={<LockOutlined />} />
                </Form.Item>
                <Form.Item name="newPassword" label="新密码" rules={[{ required: true, message: '请输入新密码' }, { min: 10, message: '密码至少需要 10 个字符' }]}>
                  <Input.Password placeholder="请输入新密码" autoComplete="new-password" prefix={<LockOutlined />} />
                </Form.Item>
                <Form.Item
                  name="confirmPassword"
                  label="确认新密码"
                  dependencies={['newPassword']}
                  rules={[
                    { required: true, message: '请再次输入新密码' },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        if (!value || getFieldValue('newPassword') === value) return Promise.resolve()
                        return Promise.reject(new Error('两次输入的密码不一致'))
                      },
                    }),
                  ]}
                >
                  <Input.Password placeholder="请再次输入新密码" autoComplete="new-password" prefix={<LockOutlined />} />
                </Form.Item>
              </div>
              <div className="profile-settings-actions">
                <Button type="primary" htmlType="submit" loading={mutation.isPending}>修改密码并重新登录</Button>
              </div>
            </Form>
          </section>
        </div>
      </div>
    </main>
  )
}
