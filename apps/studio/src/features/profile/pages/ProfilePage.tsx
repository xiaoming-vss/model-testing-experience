import { Alert, Avatar, Button, Form, Input, Tag, Typography } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage, normalizeUserName } from '@/utils/format'

import './ProfilePage.css'

const { Text, Title, Paragraph } = Typography

export function ProfilePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)
  const logout = useAuthStore((state) => state.logout)
  const [profileForm] = Form.useForm()
  const [passwordForm] = Form.useForm()
  const isLdap = user?.authSource === 'ldap'
  const isSuperAdmin = Boolean(user?.isSuperAdmin ?? user?.is_super_admin)

  useEffect(() => {
    if (user) profileForm.setFieldsValue(user)
  }, [profileForm, user])

  const updateMutation = useMutation({
    mutationFn: api.updateUser,
    onSuccess: (updated) => {
      message.success('用户信息已更新')
      setUser(updated)
      queryClient.invalidateQueries({ queryKey: ['user'] })
    },
  })

  const passwordMutation = useMutation({
    mutationFn: api.changePassword,
    onSuccess: () => {
      message.success('密码已修改，请使用新密码重新登录')
      logout()
      navigate('/login', { replace: true })
    },
  })

  return (
    <main className="profile-settings">
      <div className="profile-settings-container">
        <header className="profile-settings-heading">
          <Title level={2}>个人设置</Title>
        </header>

        <div className="profile-settings-grid">
          <aside className="profile-settings-identity" aria-label="当前登录账号">
            <Avatar size={112} icon={<UserOutlined />} className="profile-settings-avatar" />
            <Title level={3}>{normalizeUserName(user)}</Title>
            {isLdap ? <Tag color="blue">LDAP 用户</Tag> : null}
            {isSuperAdmin ? <Tag color="gold">系统管理员</Tag> : null}
            <Text type="secondary">{user?.email || '未设置邮箱'}</Text>
            <div className="profile-settings-identity-footer">
              <UserOutlined />
              <span>当前登录账号</span>
            </div>
          </aside>

          <section className="profile-settings-panel" aria-labelledby="profile-account-heading">
            <header className="profile-settings-panel-heading">
              <Title level={3} id="profile-account-heading">账号信息</Title>
              <Paragraph type="secondary">{isLdap ? '用户名和邮箱由公司目录管理，登录时同步，平台不可修改。' : '用户名创建后不可修改，邮箱用于平台内展示与后续通知。'}</Paragraph>
            </header>
            {updateMutation.error ? <Alert className="profile-settings-error" showIcon type="error" title={getErrorMessage(updateMutation.error)} /> : null}
            <Form form={profileForm} layout="vertical" onFinish={(values) => !isLdap && updateMutation.mutate({ email: values.email })} requiredMark={false} className="profile-settings-form">
              <div className="profile-settings-fields">
                <Form.Item name="name" label="用户名">
                  <Input placeholder="用户名" maxLength={50} disabled />
                </Form.Item>
                <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }]}>
                  <Input placeholder="请输入邮箱" maxLength={100} disabled={isLdap} />
                </Form.Item>
              </div>
              {!isLdap ? <div className="profile-settings-actions">
                <Button disabled={updateMutation.isPending} onClick={() => user && profileForm.setFieldsValue(user)}>重置</Button>
                <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>保存修改</Button>
              </div> : null}
            </Form>
          </section>

          {isLdap ? <Alert type="info" showIcon title="LDAP 密码由公司统一账号系统管理" /> : <section className="profile-settings-panel profile-settings-password-panel" aria-labelledby="profile-password-heading">
            <header className="profile-settings-panel-heading">
              <Title level={3} id="profile-password-heading">修改密码</Title>
              <Paragraph type="secondary">修改成功后所有已登录会话都会失效，需要使用新密码重新登录。</Paragraph>
            </header>
            {passwordMutation.error ? <Alert className="profile-settings-error" showIcon type="error" title={getErrorMessage(passwordMutation.error)} /> : null}
            <Form form={passwordForm} layout="vertical" onFinish={(values) => passwordMutation.mutate({ oldPassword: values.oldPassword, newPassword: values.newPassword })} requiredMark={false} className="profile-settings-form">
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
                <Button type="primary" htmlType="submit" loading={passwordMutation.isPending}>修改密码</Button>
              </div>
            </Form>
          </section>}
        </div>
      </div>
    </main>
  )
}
