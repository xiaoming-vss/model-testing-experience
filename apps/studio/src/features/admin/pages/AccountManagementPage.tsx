import { Alert, Button, Empty, Form, Input, Modal, Popconfirm, Select, Space, Spin, Table, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useCurrentUser } from '@/features/auth/hooks/useCurrentUser'
import { ActionButton } from '@/shared/components/ActionButton'
import { ListPagination } from '@/shared/components/ListPagination'
import { listItems, listTotal } from '@/shared/api/request'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import { adminApi } from '../api/admin.api'
import type { AdminUser } from '../types'
import '@/shared/styles/surface-tokens.css'
import '@/shared/styles/list-table.css'
import '../styles/account-management.css'

const { Text } = Typography

type Operation = { action: () => Promise<unknown>; success: string }

export function AccountManagementPage() {
  const { userQuery } = useCurrentUser()
  const currentUser = userQuery.data
  const isSuperAdmin = Boolean(currentUser?.isSuperAdmin ?? currentUser?.is_super_admin)
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<'' | AdminUser['status']>('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [emailUser, setEmailUser] = useState<AdminUser | null>(null)
  const [resetUser, setResetUser] = useState<AdminUser | null>(null)
  const [emailForm] = Form.useForm()
  const [resetForm] = Form.useForm()

  const usersQuery = useQuery({
    queryKey: ['adminUsers', search, status, page, pageSize],
    queryFn: () => adminApi.listUsers({ search, status, page, pageSize }),
    enabled: isSuperAdmin,
  })

  const operation = useMutation({
    mutationFn: async ({ action }: Operation) => action(),
    onSuccess: async (_, variables) => {
      message.success(variables.success)
      setEmailUser(null)
      setResetUser(null)
      await queryClient.invalidateQueries({ queryKey: ['adminUsers'] })
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      await queryClient.invalidateQueries({ queryKey: ['projectAccess'] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  function run(action: () => Promise<unknown>, success: string) {
    operation.mutate({ action, success })
  }

  if (userQuery.isPending) {
    return <Spin aria-label="账号信息加载中" />
  }
  if (!isSuperAdmin) {
    return <Alert type="error" showIcon title="仅系统管理员可以访问账号管理" />
  }

  const columns = [
    {
      title: '用户名',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name: string, user: AdminUser) => (
        <div className="account-management-user-name">
          <Text strong>{name}</Text>
          {user.authSource === 'ldap' ? <Tag color="blue">LDAP 用户</Tag> : null}
          {user.isSuperAdmin ? <Tag color="gold">系统管理员</Tag> : null}
        </div>
      ),
    },
    { title: '邮箱', dataIndex: 'email', key: 'email', width: 240, render: (email?: string | null) => email || '-' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (value: AdminUser['status']) =>
        value === 'pending_ldap' ? <Tag color="orange">待 LDAP 关联</Tag> : value === 'disabled' ? <Tag color="red">已禁用</Tag> : <Tag color="green">正常</Tag>,
    },
    {
      title: '最近禁用',
      key: 'disabled',
      width: 190,
      render: (_: unknown, user: AdminUser) =>
        user.status === 'disabled' ? (
          <div className="account-disabled-reason">
            {user.disabledReason ? <div>{user.disabledReason}</div> : null}
            <Text type="secondary">{formatTime(user.disabledAt ?? undefined)}</Text>
          </div>
        ) : '-',
    },
    { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt', width: 170, render: (value?: string | null) => formatTime(value ?? undefined) },
    {
      title: '操作',
      key: 'actions',
      width: 340,
      align: 'right' as const,
      render: (_: unknown, user: AdminUser) =>
        user.isSuperAdmin ? (
          <Text type="secondary">系统保护账号</Text>
        ) : (
          <Space size={4} wrap className="account-management-actions">
            {user.status !== 'active' ? (
              <Button type="link" size="small" onClick={() => run(async () => { const updated = await adminApi.enableUser(user.userId); if (updated.status === 'pending_ldap') message.info('账号待 LDAP 关联，需通过 LDAP 登录完成关联'); return updated }, '账号状态已更新')}>
                启用
              </Button>
            ) : (
              <Popconfirm
                title={`禁用账号 ${user.name}？`}
                okText="确认禁用"
                cancelText="取消"
                onConfirm={() => run(() => adminApi.disableUser(user.userId), '账号已禁用')}
              >
                <Button type="link" size="small" danger>
                  禁用
                </Button>
              </Popconfirm>
            )}
            {user.status === 'pending_ldap' ? <Button type="link" size="small" danger onClick={() => run(() => adminApi.disableUser(user.userId), '账号已禁用')}>禁用</Button> : null}
            {user.authSource !== 'ldap' ? <Button type="link" size="small" onClick={() => { resetForm.resetFields(); setResetUser(user) }}>
              重置密码
            </Button> : null}
            <Button type="link" size="small" onClick={() => run(() => adminApi.revokeSessions(user.userId), '已强制该账号下线')}>
              强制下线
            </Button>
            {user.authSource !== 'ldap' ? <Button type="link" size="small" onClick={() => { setEmailUser(user); emailForm.setFieldsValue({ email: user.email ?? '' }) }}>
              修改邮箱
            </Button> : null}
            <Popconfirm
              title={`删除账号 ${user.name}？`}
              description="账号拥有的项目将自动转给系统管理员，个人授权与未完成任务会被清理，历史记录显示为已删除账户。"
              okText="确认删除"
              cancelText="取消"
              onConfirm={() => run(() => adminApi.deleteUser(user.userId), '账号已删除')}
            >
              <Button type="link" size="small" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
    },
  ]

  return (
    <div className="workbench-page account-management-page tp-list-surface tp-surface">
      <div className="account-management-content">
        <section className="account-management-panel tp-board tp-list-panel" aria-labelledby="account-management-title">
          <div className="account-management-toolbar tp-list-toolbar">
            <div className="account-management-filters">
              <h1 className="tp-list-title" id="account-management-title">账号管理</h1>
              <Input.Search
                className="account-management-search"
                allowClear
                aria-label="搜索用户名或邮箱"
                placeholder="搜索用户名或邮箱"
                onSearch={(value) => { setSearch(value.trim()); setPage(1) }}
              />
              <Select
                className="account-management-status"
                aria-label="账号状态"
                value={status}
                onChange={(value) => { setStatus(value); setPage(1) }}
                options={[
                  { value: '', label: '全部状态' },
                  { value: 'active', label: '正常' },
                  { value: 'disabled', label: '已禁用' },
                  { value: 'pending_ldap', label: '待 LDAP 关联' },
                ]}
              />
            </div>
            <Space size={8} className="tp-refresh-actions">
              <ActionButton
                operation="refresh"
                loading={usersQuery.isFetching}
                onClick={() => { void usersQuery.refetch() }}
              />
            </Space>
          </div>

          {usersQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(usersQuery.error)} action={<Button onClick={() => { void usersQuery.refetch() }}>重试</Button>} />
          ) : null}

          <div className="tp-list-body">
            <div className="tp-list-scroll">
              <Table<AdminUser>
                className="account-management-table tp-list-table"
                rowKey="userId"
                dataSource={listItems(usersQuery.data)}
                columns={columns}
                loading={usersQuery.isLoading}
                pagination={false}
                tableLayout="fixed"
                scroll={{ x: 1240 }}
                locale={{ emptyText: <Empty description="暂无账号" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
              />
            </div>
            <div className="table-footer">
              <ListPagination
                loading={usersQuery.isFetching || usersQuery.isError}
                current={page}
                pageSize={pageSize}
                total={listTotal(usersQuery.data)}
                onChange={(nextPage, nextSize) => { setPage(nextPage); setPageSize(nextSize) }}
              />
            </div>
          </div>
        </section>
      </div>

      <Modal
        title={`修改邮箱${emailUser ? ` · ${emailUser.name}` : ''}`}
        open={Boolean(emailUser)}
        onCancel={() => setEmailUser(null)}
        onOk={() => emailForm.submit()}
        confirmLoading={operation.isPending}
        destroyOnHidden
      >
        <Form form={emailForm} layout="vertical" onFinish={(values) => emailUser && run(() => adminApi.updateEmail(emailUser.userId, values.email), '邮箱已更新')}>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }]}>
            <Input placeholder="请输入邮箱" maxLength={100} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`重置密码${resetUser ? ` · ${resetUser.name}` : ''}`}
        open={Boolean(resetUser)}
        onCancel={() => setResetUser(null)}
        onOk={() => resetForm.submit()}
        confirmLoading={operation.isPending}
        destroyOnHidden
      >
        <Alert
          type="warning"
          showIcon
          title="重置后该账号所有已登录会话会立即失效"
          description="请通过安全渠道把新密码告知对方；重置不会强制对方再次修改密码。"
          style={{ marginBottom: 16 }}
        />
        <Form
          form={resetForm}
          layout="vertical"
          onFinish={(values) => resetUser && run(() => adminApi.resetPassword(resetUser.userId, values.newPassword), '密码已重置')}
        >
          <Form.Item name="newPassword" label="新密码" rules={[{ required: true, message: '请输入新密码' }, { min: 10, message: '密码至少需要 10 个字符' }]}>
            <Input.Password placeholder="请输入新密码" autoComplete="new-password" />
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
            <Input.Password placeholder="请再次输入新密码" autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
