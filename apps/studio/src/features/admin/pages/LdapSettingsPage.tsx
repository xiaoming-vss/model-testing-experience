import { useEffect, useState } from 'react'
import { Alert, Button, Checkbox, Collapse, Form, Input, InputNumber, Modal, Select, Space, Spin, Switch, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { getErrorMessage } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { ldapApi, type LdapConfig, type LdapTest } from '../api/ldap.api'
import '@/shared/styles/surface-tokens.css'
import '../styles/ldap-settings.css'

const { Title, Text, Paragraph } = Typography

export function LdapSettingsPage() {
  const [form] = Form.useForm<LdapConfig & { clearPassword: boolean }>()
  const queryClient = useQueryClient()
  const userQuery = useQuery({ queryKey: ['user'], queryFn: api.getUser })
  const admin = Boolean(userQuery.data?.isSuperAdmin ?? userQuery.data?.is_super_admin)
  const settings = useQuery({ queryKey: ['ldapSettings'], queryFn: ldapApi.get, enabled: admin, refetchOnWindowFocus: false })
  const [testUsername, setTestUsername] = useState('')
  const [testResult, setTestResult] = useState<LdapTest | null>(null)
  const [pendingSave, setPendingSave] = useState<LdapConfig | null>(null)
  const [dirty, setDirty] = useState(false)
  const enabled = Form.useWatch('enabled', form)
  const memberAttribute = Form.useWatch('group_member_attribute', form)
  useEffect(() => {
    if (settings.data) {
      form.setFieldsValue({ ...settings.data.config, bind_password: '', clearPassword: false })
      setDirty(false)
    }
  }, [settings.data, form])
  const save = useMutation({
    mutationFn: (config: LdapConfig) => ldapApi.save({ generation: settings.data!.generation, config, clearPassword: Boolean(form.getFieldValue('clearPassword')) }),
    onSuccess: (data) => {
      setPendingSave(null)
      setTestResult(null)
      queryClient.setQueryData(['ldapSettings'], data)
      void queryClient.invalidateQueries({ queryKey: ['authConfig'] })
      void queryClient.invalidateQueries({ queryKey: ['adminUsers'] })
      message.success('LDAP 配置已保存并生效')
    },
  })
  const test = useMutation({ mutationFn: (config: LdapConfig) => ldapApi.test({ config, username: testUsername.trim(), clearPassword: Boolean(form.getFieldValue('clearPassword')) }), onSuccess: setTestResult })
  function configuration(values: LdapConfig & { clearPassword?: boolean }): LdapConfig {
    const config = { ...values }
    delete config.clearPassword
    return { ...config, group_member_value_type: config.group_member_attribute === 'member' ? 'dn' : 'username' }
  }
  function submit(values: LdapConfig) {
    const config = configuration(values)
    if (config.enabled !== settings.data?.config.enabled) setPendingSave(config)
    else save.mutate(config)
  }
  if (userQuery.isPending) return <Spin aria-label="账号加载中" />
  if (!admin) return <Alert type="error" showIcon title="仅系统管理员可以管理 LDAP" />
  if (settings.isPending) return <Spin aria-label="LDAP 配置加载中" />
  if (!settings.data) return <Alert type="error" title={getErrorMessage(settings.error)} action={<Button onClick={() => { void settings.refetch() }}>重试</Button>} />
  const busy = save.isPending || test.isPending
  return <main className="ldap-settings-page tp-surface">
    <div className="tp-board tp-list-panel">
    <header className="tp-list-toolbar">
      <h1 className="tp-list-title">LDAP 认证</h1>
      <Text type="secondary">管理目录连接、访问范围和登录方式</Text>
    </header>
    <div className="tp-list-body"><div className="tp-list-scroll">
    <Form id="ldap-settings-form" form={form} layout="vertical" onFinish={submit} disabled={busy} onValuesChange={() => { setDirty(true); setTestResult(null); test.reset(); save.reset() }}>
      <section className="ldap-settings-section">
        <Title level={5}>连接与访问范围</Title>
        <Form.Item name="enabled" label="启用 LDAP" valuePropName="checked"><Switch /></Form.Item>
        <div className="ldap-settings-grid">
          <Form.Item name="server_url" label="LDAP 地址" extra="例如 ldap://目录主机:389 或 ldaps://目录主机:636" rules={[{ required: enabled, message: '请输入 LDAP 地址' }]}><Input placeholder="ldap://" /></Form.Item>
          <Form.Item name="bind_dn" label="查询账号 DN" rules={[{ required: enabled, message: '请输入查询账号 DN' }]}><Input placeholder="uid=reader,cn=users,dc=example,dc=com" /></Form.Item>
          <Form.Item name="bind_password" label="查询密码" extra={settings.data.passwordConfigured ? '已保存密码；留空保持原密码，无法查看原文。' : '尚未配置查询密码。'}><Input.Password autoComplete="new-password" placeholder={settings.data.passwordConfigured ? '留空保持已保存密码' : '输入查询账号密码'} /></Form.Item>
          <Form.Item name="user_search_base" label="用户搜索 Base DN" rules={[{ required: enabled, message: '请输入搜索范围' }]}><Input /></Form.Item>
          <Form.Item name="user_search_filter" label="用户过滤器" extra="必须包含 {username}，系统会对用户名转义。"><Input /></Form.Item>
          <Form.Item name="access_group_dn" label="专用访问组 DN" rules={[{ required: enabled, message: '请输入访问组 DN' }]}><Input /></Form.Item>
          <Form.Item name="group_member_attribute" label="直接成员属性" extra={memberAttribute === 'member' ? '按用户 DN 比较，不展开嵌套组。' : '按目录用户名比较，不展开嵌套组。'}><Select options={[{ value: 'memberUid', label: 'memberUid（用户名）' }, { value: 'member', label: 'member（用户 DN）' }]} /></Form.Item>
        </div>
        <Form.Item name="start_tls" valuePropName="checked"><Checkbox>使用 StartTLS（仅 ldap://；ldaps:// 请关闭此项）</Checkbox></Form.Item>
        <Form.Item name="allow_insecure_connection" valuePropName="checked"><Checkbox>显式允许明文 LDAP（仅 ldap:// 且未使用 StartTLS）</Checkbox></Form.Item>
        <Form.Item name="tls_ca_pem" label="私有 CA 证书（PEM）" extra="粘贴 CA 公钥证书即可，不能包含私钥；留空使用原部署 CA 或系统信任库。"><Input.TextArea rows={4} placeholder="-----BEGIN CERTIFICATE-----" /></Form.Item>
      </section>
      <Collapse items={[{ key: 'advanced', label: '高级设置与目录状态规则', children: <div>
        <div className="ldap-settings-grid">
          <Form.Item name="username_attribute" label="用户名属性"><Input /></Form.Item>
          <Form.Item name="email_attribute" label="邮箱属性"><Input /></Form.Item>
          <Form.Item name="external_id_attribute" label="稳定身份属性"><Input /></Form.Item>
          <Form.Item name="timeout_seconds" label="网络阶段超时（秒）"><InputNumber min={1} max={60} /></Form.Item>
          <Form.Item name="login_timeout_seconds" label="登录总超时（秒）"><InputNumber min={1} max={300} /></Form.Item>
          <Form.Item name="reconcile_interval_seconds" label="资格对账周期（秒）"><InputNumber min={1} max={86400} /></Form.Item>
          <Form.Item name="token_expire_hours" label="LDAP 会话有效期（小时）"><InputNumber min={1} max={8760} /></Form.Item>
          <Form.Item name="active_user_filter" label="正常账号过滤器"><Input /></Form.Item>
          <Form.Item name="disabled_user_filter" label="停用账号过滤器"><Input /></Form.Item>
        </div>
        <Form.Item name="directory_rules_verified" valuePropName="checked"><Checkbox>已确认当前目录状态规则与查询权限，未识别状态拒绝处理</Checkbox></Form.Item>
        <Form.Item name="auto_link_by_username" valuePropName="checked" extra="仅迁移窗口内开启；关联成功会清空旧本地密码，保留原账号和项目。"><Checkbox>允许同名待关联账号首次登录时关联</Checkbox></Form.Item>
        <Form.Item name="clearPassword" valuePropName="checked"><Checkbox>清除已保存的查询密码（只能在关闭 LDAP 时保存）</Checkbox></Form.Item>
      </div> }]} />
      <section className="ldap-settings-section">
        <Title level={5}>保存前检查</Title>
        <Text type="secondary">只读检查查询连接和访问组；可填写目录用户名检查访问资格。不验证用户密码，也不会保存配置。</Text>
        <Space wrap className="ldap-settings-test">
          <Input aria-label="检查用户名" placeholder="可选：目录用户名" value={testUsername} onChange={(event) => { setTestUsername(event.target.value); setTestResult(null) }} maxLength={50} />
          <Button loading={test.isPending} onClick={async () => { try { const values = await form.validateFields(); test.mutate(configuration(values)) } catch { /* validation shown by form */ } }}>检查连接</Button>
        </Space>
        {testResult ? <Alert showIcon type={testResult.eligible === false ? 'warning' : 'success'} title={testResult.message} description={testResult.userFound !== undefined ? `用户${testResult.userFound ? '已找到' : '未找到'}；访问资格${testResult.eligible ? '通过' : '未通过'}；邮箱${testResult.emailPresent ? '存在' : '为空'}` : undefined} /> : null}
        {test.error ? <Alert type="error" showIcon title={getErrorMessage(test.error)} /> : null}
        {save.error ? <Alert type="error" showIcon title={getErrorMessage(save.error)} /> : null}
      </section>
    </Form>
    </div></div>
    <footer className="ldap-settings-actions">
      <Text type="secondary">{dirty ? '有未保存的修改' : '保存后即时生效，系统管理员始终保留本地登录'}</Text>
      <Space wrap><Button disabled={busy} onClick={() => { void settings.refetch() }}>重新加载</Button><Button type="primary" htmlType="submit" form="ldap-settings-form" loading={save.isPending} disabled={!dirty || busy}>保存并生效</Button></Space>
    </footer>
    </div>
    <Modal title={pendingSave?.enabled ? '确认启用 LDAP' : '确认关闭 LDAP'} open={Boolean(pendingSave)} okText="确认并保存" cancelText="取消" confirmLoading={save.isPending} onCancel={() => setPendingSave(null)} onOk={() => pendingSave && save.mutate(pendingSave)}>
      <Paragraph>{pendingSave?.enabled ? '启用后关闭注册，普通本地账号进入待 LDAP 关联，普通用户旧会话失效。管理员本地登录保留。' : '关闭后仅允许正常本地账号登录；待关联账号不会自动恢复，已关联 LDAP 用户不会恢复本地密码。'}</Paragraph>
      {save.error ? <Alert type="error" title={getErrorMessage(save.error)} /> : null}
    </Modal>
  </main>
}
