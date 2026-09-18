import { Alert, Avatar, Button, Form, Input, Popconfirm, Typography } from 'antd'
import { UserOutlined } from '@ant-design/icons'
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
  const [form] = Form.useForm()

  useEffect(() => {
    if (user) form.setFieldsValue(user)
  }, [form, user])

  const updateMutation = useMutation({
    mutationFn: api.updateUser,
    onSuccess: (_, values) => {
      message.success('用户信息已更新')
      setUser({ ...(user ?? { name: values.name ?? '' }), ...values })
      queryClient.invalidateQueries({ queryKey: ['user'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: api.deleteUser,
    onSuccess: () => {
      message.success('账号已注销')
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
            <Text type="secondary">{user?.email || '未设置邮箱'}</Text>
            <div className="profile-settings-identity-footer">
              <UserOutlined />
              <span>当前登录账号</span>
            </div>
          </aside>

          <section className="profile-settings-panel" aria-labelledby="profile-account-heading">
            <header className="profile-settings-panel-heading">
              <Title level={3} id="profile-account-heading">账号信息</Title>
              <Paragraph type="secondary">更新用户名和邮箱，用于平台内展示与后续通知。</Paragraph>
            </header>
            {updateMutation.error ? <Alert className="profile-settings-error" showIcon type="error" title={getErrorMessage(updateMutation.error)} /> : null}
            <Form form={form} layout="vertical" onFinish={(values) => updateMutation.mutate(values)} requiredMark={false} className="profile-settings-form">
              <div className="profile-settings-fields">
                <Form.Item name="name" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
                  <Input placeholder="请输入用户名" maxLength={50} />
                </Form.Item>
                <Form.Item name="email" label="邮箱">
                  <Input placeholder="请输入邮箱" maxLength={100} />
                </Form.Item>
              </div>
              <div className="profile-settings-actions">
                <Button disabled={updateMutation.isPending} onClick={() => user && form.setFieldsValue(user)}>重置</Button>
                <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>保存修改</Button>
              </div>
            </Form>
          </section>

          <section className="profile-settings-danger" aria-labelledby="profile-delete-heading">
            <div>
              <Title level={5} id="profile-delete-heading">注销账号</Title>
              <Paragraph type="secondary">注销前请先转移或删除你拥有的全部项目。注销后账号不可继续使用，个人授权与未完成任务将失效。</Paragraph>
              {deleteMutation.error ? <Alert showIcon type="error" title={getErrorMessage(deleteMutation.error)} /> : null}
            </div>
            <Popconfirm title="确认注销当前账号？" okText="确认注销" cancelText="取消" onConfirm={() => deleteMutation.mutate()}>
              <Button danger loading={deleteMutation.isPending}>注销账号</Button>
            </Popconfirm>
          </section>
        </div>
      </div>
    </main>
  )
}
