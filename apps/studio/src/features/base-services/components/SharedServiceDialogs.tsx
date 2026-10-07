import { ZentaoMcpDeploymentHelp } from './ZentaoMcpDeploymentHelp'
import { Alert, Checkbox, Form, Input, Modal, Select, Typography } from 'antd'
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
  const endpoint = Form.useWatch('baseUrl', configuration)
  const confirmed = Form.useWatch('confirmInstanceSwitch', configuration)
  const needsConfirmation = provider === 'mcp' && editor && editor !== 'create'
    && (editor.instanceResetRequired || (endpoint !== undefined && endpoint.trim() !== editor.baseUrl))
  return <>
    <Modal forceRender okText="保存" cancelText="取消" title={editor === 'create' ? (provider === 'mcp' ? '新增 MCP' : `新建 ${providerLabel} 服务`) : '编辑服务'} open={Boolean(editor)} onCancel={closeEditor} onOk={saveConfiguration} confirmLoading={saving} okButtonProps={{ disabled: !canManage || Boolean(needsConfirmation && !confirmed) }} style={provider === 'mcp' ? { top: 24 } : undefined} styles={provider === 'mcp' ? { body: { maxHeight: 'calc(100dvh - 160px)', overflowY: 'auto' } } : undefined}>
      {(provider !== 'mcp' || editor === 'create') && <Alert showIcon type="info" title={provider === 'mcp' ? '填写已启动的 MCP 服务地址，创建后再配置本人的 Token。' : '服务配置对项目成员可见，创建时无需填写个人凭据。'} style={{ marginBottom: 16 }} />}
      {provider === 'mcp' && editor === 'create' && <ZentaoMcpDeploymentHelp />}
      <Form form={configuration} layout="vertical" preserve={false}>
        <Form.Item name="name" label="服务名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={120} placeholder={provider === 'mcp' ? '例如：项目禅道 MCP' : undefined} /></Form.Item>
        <Form.Item name="baseUrl" label={provider === 'mcp' ? 'MCP 服务地址' : '服务地址'} rules={[{ required: true }, provider === 'mcp' ? { validator: validateMcpUrl } : { type: 'url', message: '请输入完整的 http 或 https 地址' }]}><Input placeholder={provider === 'mcp' ? 'http://服务器地址:9091/zentao/mcp' : 'https://…'} disabled={provider !== 'mcp' && editor !== 'create'} onChange={() => configuration.setFieldValue('confirmInstanceSwitch', false)} /></Form.Item>
        {provider === 'mcp' && editor === 'create' && <Form.Item name="templateId" label="MCP 类型" rules={[{ required: true, message: '请选择 MCP 类型' }]}>
          <Select options={[{ value: 'zentao', label: '禅道（ZenTao）' }]} />
        </Form.Item>}
        {provider === 'llm' && <Form.Item name="modelId" label="模型 ID" rules={[{ required: true, whitespace: true }]}><Input disabled={editor !== 'create'} maxLength={255} /></Form.Item>}
        {provider === 'mcp' && editor !== 'create' && <Form.Item label="当前读取的禅道实例（保存时重新检查）">
          <Typography.Text>{editor && (editor.pendingInstanceUrl || editor.zentaoInstanceUrl) ? editor.pendingInstanceUrl || editor.zentaoInstanceUrl : '保存本人 Token 后从 MCP 自动读取'}</Typography.Text>
        </Form.Item>}
        {needsConfirmation && <>
          <Alert type="warning" showIcon title="保存时将检查并切换禅道目标" description="目标变化或存在旧关联时，清除此服务关联的旧禅道记录；此服务承载项目绑定时，同时清除本项目禅道绑定、测试单外部缺陷号、Bug 和附件推送关联。原禅道数据保留，旧推送记录留在 Bug 动态；随后需重新绑定，旧目标授权会失效。同一禅道实例只更换 MCP 地址时保留绑定。" style={{ marginBottom: 12 }} />
          <Form.Item name="confirmInstanceSwitch" valuePropName="checked" rules={[{ validator: (_, value) => value ? Promise.resolve() : Promise.reject(new Error('请勾选确认后保存')) }]}>
            <Checkbox>我确认切换禅道目标，并在需要时清除本项目旧绑定</Checkbox>
          </Form.Item>
        </>}
        {editor !== 'create' && provider !== 'mcp' && <Typography.Text type="secondary">地址和模型用于确定授权对象，需要更换时请新建服务。</Typography.Text>}
      </Form>
    </Modal>
    <Modal forceRender cancelText="取消" title={`我的授权 · ${authorization?.name ?? ''}`} open={Boolean(authorization)} onCancel={closeAuthorization} onOk={saveAuthorization} confirmLoading={saving} okText="保存我的授权">
      {provider === 'mcp' && <Alert type="info" showIcon title="token 仅用于本人的授权，保存后自动读取实例信息；禅道访问权限在业务操作时校验。" style={{ marginBottom: 16 }} />}
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
