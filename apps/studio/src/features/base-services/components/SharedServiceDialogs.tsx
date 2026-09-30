import { Alert, Form, Input, Modal, Typography } from 'antd'
import type { FormInstance } from 'antd'
import type { PersonalAuthorization, ServiceConfiguration, ServiceProvider, SharedService } from '../api/sharedServices.api'

async function validateMcpUrl(_: unknown, value: string) {
  try {
    const url = new URL(value.trim())
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash || /\s/.test(value.trim())) throw new Error()
  } catch {
    throw new Error('请输入不含凭据、查询参数或片段的完整 http 或 https 地址')
  }
}

type Props = {
  provider: ServiceProvider
  providerLabel: string
  editor: SharedService | 'create' | null
  authorization: SharedService | null
  configuration: FormInstance<ServiceConfiguration>
  credentials: FormInstance<PersonalAuthorization>
  saving: boolean
  canManage: boolean
  closeEditor: () => void
  closeAuthorization: () => void
  saveConfiguration: () => Promise<void>
  saveAuthorization: () => Promise<void>
}

export function SharedServiceDialogs({ provider, providerLabel, editor, authorization, configuration, credentials, saving, canManage, closeEditor, closeAuthorization, saveConfiguration, saveAuthorization }: Props) {
  return <>
    <Modal forceRender okText="保存" cancelText="取消" title={editor === 'create' ? (provider === 'mcp' ? '配置禅道 MCP' : `新建 ${providerLabel} 服务`) : '编辑服务'} open={Boolean(editor)} onCancel={closeEditor} onOk={saveConfiguration} confirmLoading={saving} okButtonProps={{ disabled: !canManage }}>
      <Alert showIcon type="info" title="服务配置对项目成员可见，创建时无需填写个人凭据。" style={{ marginBottom: 16 }} />
      <Form form={configuration} layout="vertical" preserve={false}>
        <Form.Item name="name" label="服务名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={120} /></Form.Item>
        <Form.Item name="baseUrl" label="服务地址" rules={[{ required: true }, provider === 'mcp' ? { validator: validateMcpUrl } : { type: 'url', message: '请输入完整的 http 或 https 地址' }]}><Input placeholder={provider === 'mcp' ? 'http://127.0.0.1:9090/zentao/mcp' : 'https://…'} disabled={editor !== 'create'} /></Form.Item>
        {provider === 'llm' && <Form.Item name="modelId" label="模型 ID" rules={[{ required: true, whitespace: true }]}><Input disabled={editor !== 'create'} maxLength={255} /></Form.Item>}
        {editor !== 'create' && <Typography.Text type="secondary">{provider === 'mcp' ? '地址用于确定授权对象，需要更换时请删除后重新配置服务。' : '地址和模型用于确定授权对象，需要更换时请新建服务。'}</Typography.Text>}
      </Form>
    </Modal>
    <Modal forceRender cancelText="取消" title={`我的授权 · ${authorization?.name ?? ''}`} open={Boolean(authorization)} onCancel={closeAuthorization} onOk={saveAuthorization} confirmLoading={saving} okText="保存我的授权">
      {provider === 'mcp' && <Alert type="info" showIcon title="token 仅用于本人的授权，保存后不会验证远端连接。" style={{ marginBottom: 16 }} />}
      <Form form={credentials} layout="vertical" preserve={false} autoComplete="off">
        {provider === 'mcp' && <Form.Item name="token" label="我的 Token" rules={[{ required: true, whitespace: true }]}><Input.Password autoComplete="new-password" /></Form.Item>}
        {provider === 'llm' && <Form.Item name="apiKey" label="API Key" rules={[{ required: true, whitespace: true }]}><Input.Password autoComplete="new-password" /></Form.Item>}
        {provider === 'gitlab' && <Form.Item name="accessToken" label="个人访问令牌" rules={[{ required: true, whitespace: true }]}><Input.Password autoComplete="new-password" /></Form.Item>}
        {provider === 'zentao' && <>
          <Form.Item name="account" label="我的禅道账号" rules={[{ required: true, whitespace: true }]}><Input autoComplete="off" /></Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, whitespace: true }]}><Input.Password autoComplete="new-password" /></Form.Item>
        </>}
      </Form>
    </Modal>
  </>
}
