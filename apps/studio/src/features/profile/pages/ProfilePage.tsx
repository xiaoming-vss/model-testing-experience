import { Alert, Avatar, Button, Form, Input, Tag, Typography } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage, normalizeUserName } from '@/utils/format'

import accountStyles from '@/shared/styles/account.module.css'

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
  const isSuperAdmin = Boolean(user?.isSuperAdmin)

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
    <main className={`profile-settings ${accountStyles.profileRoot} min-h-[calc(100dvh_-_64px)] px-[var(--app-page-gutter)] pt-12 pb-16 max-narrow-md:pt-8 max-narrow-md:pb-8 max-narrow-sm:pt-6 max-narrow-sm:pb-10`}>
      <div className="profile-settings-container mx-auto max-w-[1200px]">
        <header className="profile-settings-heading mb-7">
          <Title level={2} className="m-0 text-[30px] [font-weight:650] max-narrow-sm:text-[26px]">个人设置</Title>
        </header>

        <div className="profile-settings-grid grid grid-cols-[320px_minmax(0,1fr)] items-stretch gap-x-7 gap-y-6 max-narrow-md:grid-cols-[260px_minmax(0,1fr)] max-narrow-md:gap-5 max-narrow-sm:grid-cols-1">
          <aside className="profile-settings-identity min-w-0 rounded-[20px] border border-[var(--profile-border)] bg-[linear-gradient(150deg,var(--profile-tint),var(--profile-surface)_70%)] px-7 pt-12 pb-8 text-center shadow-[0_10px_30px_var(--app-profile-card-shadow)] max-narrow-sm:px-6 max-narrow-sm:py-7" aria-label="当前登录账号">
            <Avatar size={112} icon={<UserOutlined />} className={`profile-settings-avatar ${accountStyles.profileAvatar} mb-6`} />
            <Title level={3} className="mt-0 mb-2.5 text-[26px] [overflow-wrap:anywhere]">{normalizeUserName(user)}</Title>
            {isLdap ? <Tag color="blue">LDAP 用户</Tag> : null}
            {isSuperAdmin ? <Tag color="gold">系统管理员</Tag> : null}
            <Text type="secondary" className="block text-[15px] [overflow-wrap:anywhere]">{user?.email || '未设置邮箱'}</Text>
            <div className="profile-settings-identity-footer mt-9 flex items-center gap-2.5 border-t border-[var(--profile-border)] pt-6 text-left text-[var(--profile-muted)] max-narrow-sm:mt-6 max-narrow-sm:justify-center max-narrow-sm:pt-[18px]">
              <UserOutlined />
              <span>当前登录账号</span>
            </div>
          </aside>

          <section className="profile-settings-panel min-w-0 overflow-hidden rounded-[20px] border border-[var(--profile-border)] bg-[var(--profile-surface)] shadow-[0_10px_30px_var(--app-profile-card-shadow)]" aria-labelledby="profile-account-heading">
            <header className="profile-settings-panel-heading mx-8 border-b border-[var(--profile-border)] pt-7 pb-6 max-narrow-md:mx-6">
              <Title level={3} id="profile-account-heading" className="mt-0 mb-2.5 text-[24px]">账号信息</Title>
              <Paragraph type="secondary" className="m-0 leading-[1.7]">{isLdap ? '用户名和邮箱由公司目录管理，登录时同步，平台不可修改。' : '用户名创建后不可修改，邮箱用于平台内展示与后续通知。'}</Paragraph>
            </header>
            {updateMutation.error ? <Alert className="profile-settings-error mx-8 mt-5" showIcon type="error" title={getErrorMessage(updateMutation.error)} /> : null}
            <Form form={profileForm} layout="vertical" onFinish={(values) => !isLdap && updateMutation.mutate({ email: values.email })} requiredMark={false} className="profile-settings-form">
              <div className={`profile-settings-fields ${accountStyles.profileFields} px-8 pt-[26px] pb-2 max-narrow-md:px-6`}>
                <Form.Item name="name" label="用户名">
                  <Input placeholder="用户名" maxLength={50} disabled />
                </Form.Item>
                <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }]}>
                  <Input placeholder="请输入邮箱" maxLength={100} disabled={isLdap} />
                </Form.Item>
              </div>
              {!isLdap ? <div className="profile-settings-actions flex justify-end gap-3 bg-[var(--profile-tint)] px-8 py-5 max-narrow-md:px-6 max-narrow-sm:flex-wrap">
                <Button disabled={updateMutation.isPending} onClick={() => user && profileForm.setFieldsValue(user)}>重置</Button>
                <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>保存修改</Button>
              </div> : null}
            </Form>
          </section>

          {isLdap ? <Alert type="info" showIcon title="LDAP 密码由公司统一账号系统管理" /> : <section className="profile-settings-panel profile-settings-password-panel col-start-2 min-w-0 overflow-hidden rounded-[20px] border border-[var(--profile-border)] bg-[var(--profile-surface)] shadow-[0_10px_30px_var(--app-profile-card-shadow)] max-narrow-sm:col-start-1" aria-labelledby="profile-password-heading">
            <header className="profile-settings-panel-heading mx-8 border-b border-[var(--profile-border)] pt-7 pb-6 max-narrow-md:mx-6">
              <Title level={3} id="profile-password-heading" className="mt-0 mb-2.5 text-[24px]">修改密码</Title>
              <Paragraph type="secondary" className="m-0 leading-[1.7]">修改成功后所有已登录会话都会失效，需要使用新密码重新登录。</Paragraph>
            </header>
            {passwordMutation.error ? <Alert className="profile-settings-error mx-8 mt-5" showIcon type="error" title={getErrorMessage(passwordMutation.error)} /> : null}
            <Form form={passwordForm} layout="vertical" onFinish={(values) => passwordMutation.mutate({ oldPassword: values.oldPassword, newPassword: values.newPassword })} requiredMark={false} className="profile-settings-form">
              <div className={`profile-settings-fields ${accountStyles.profileFields} px-8 pt-[26px] pb-2 max-narrow-md:px-6`}>
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
              <div className="profile-settings-actions flex justify-end gap-3 bg-[var(--profile-tint)] px-8 py-5 max-narrow-md:px-6 max-narrow-sm:flex-wrap">
                <Button type="primary" htmlType="submit" loading={passwordMutation.isPending}>修改密码</Button>
              </div>
            </Form>
          </section>}
        </div>
      </div>
    </main>
  )
}
