import { AppIcon } from '@/shared/icons'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { SafetyCertificateOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Form, Input, Modal, Pagination, Popconfirm, Space, Tag, Tooltip, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { listItems } from '@/shared/api/request'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import { sharedServicesApi as api, type PersonalAuthorization, type ServiceConfiguration, type ServiceProvider, type SharedService } from '../api/sharedServices.api'

const labels = { llm: 'LLM', zentao: '禅道', gitlab: 'GitLab' }
const stateLabels = { unauthorized: '未授权', authorized: '已授权', invalid: '授权已失效' }

export function SharedServicesPanel({ projectId, provider, toolbarActions }: { projectId?: string; provider: ServiceProvider; toolbarActions?: HTMLElement | null }) {
  if (!projectId) return <Empty description="请先选择项目" />
  return <ProjectAccessScope projectId={projectId}>
    <ServiceCatalog key={`${projectId}:${provider}`} projectId={projectId} provider={provider} toolbarActions={toolbarActions} />
  </ProjectAccessScope>
}

function ServiceCatalog({ projectId, provider, toolbarActions }: { projectId: string; provider: ServiceProvider; toolbarActions?: HTMLElement | null }) {
  const { can } = useProjectAccess(projectId)
  const client = useQueryClient()
  const [editor, setEditor] = useState<SharedService | 'create' | null>(null)
  const [authorization, setAuthorization] = useState<SharedService | null>(null)
  const [saving, setSaving] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(18)
  const [configuration] = Form.useForm<ServiceConfiguration>()
  const [credentials] = Form.useForm<PersonalAuthorization>()
  const query = useQuery({
    queryKey: ['sharedServices', projectId, provider],
    queryFn: () => api.list(projectId, provider),
  })
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['sharedServices', projectId, provider] }),
      client.invalidateQueries({ queryKey: [`${provider}Connections`] }),
      client.invalidateQueries({ queryKey: [`${provider}Connection`] }),
    ])
  }
  const closeAuthorization = () => { credentials.resetFields(); setAuthorization(null) }
  const closeEditor = () => { configuration.resetFields(); setEditor(null) }
  const openEditor = (resource: SharedService | 'create') => {
    configuration.resetFields()
    if (resource !== 'create') configuration.setFieldsValue(resource)
    setEditor(resource)
  }
  const saveConfiguration = async () => {
    if (!can('manage') || !editor) return
    const values = await configuration.validateFields().catch(() => null)
    if (!values) return
    setSaving(true)
    try {
      if (editor === 'create') {
        await api.create(projectId, provider, {
          name: values.name.trim(), baseUrl: values.baseUrl.trim(),
          ...(provider === 'llm' ? { modelId: values.modelId?.trim() } : {}),
        })
        message.success('服务已创建，请单独完成我的授权')
      } else {
        await api.rename(projectId, provider, editor.serviceId, values.name.trim())
        message.success('服务名称已更新')
      }
      closeEditor()
      await refresh()
    } catch (error) { message.error(getErrorMessage(error)) }
    finally { setSaving(false) }
  }
  const saveAuthorization = async () => {
    if (!authorization || !can('read')) return
    const values = await credentials.validateFields().catch(() => null)
    if (!values) return
    setSaving(true)
    try {
      // Secrets stay in this form/request, never in React Query's mutation/cache variables.
      await api.authorize(projectId, provider, authorization.serviceId, values)
      closeAuthorization()
      message.success('我的授权已保存')
      await refresh()
    } catch (error) { message.error(getErrorMessage(error)) }
    finally { setSaving(false) }
  }
  const remove = async (resource: SharedService, personal: boolean) => {
    setSaving(true)
    try {
      if (personal) await api.revoke(projectId, provider, resource.serviceId)
      else await api.delete(projectId, provider, resource.serviceId)
      message.success(personal ? '已撤销我的授权' : '服务已删除')
      await refresh()
    } catch (error) { message.error(getErrorMessage(error)) }
    finally { setSaving(false) }
  }
  const services = listItems(query.data)
  const currentPage = Math.min(page, Math.max(1, Math.ceil(services.length / pageSize)))
  const pagedServices = services.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const createButton = <ProjectActionButton action="manage" projectId={projectId} type="primary" className="action-btn-create" operation="create" onClick={() => openEditor('create')}>新建服务</ProjectActionButton>
  return <>
    {toolbarActions ? createPortal(createButton, toolbarActions) : createButton}
    {query.isError && <Alert type="error" showIcon title={getErrorMessage(query.error)} />}
    <div className="base-services-connection-shell">
      <div className="table-body-scroll sprint-card-scroll base-services-card-scroll">
        {query.isPending ? (
          <div className="sprint-card-loading"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`${labels[provider]} 服务加载中...`} /></div>
        ) : services.length === 0 ? (
          <div className="base-services-empty-card base-services-empty-card-list">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={can('manage') ? '暂无服务，先创建服务，再单独授权' : '暂无服务，请项目所有者创建'} />
          </div>
        ) : (
          <div className={`api-collection-grid base-services-connection-grid${pageSize === 18 && pagedServices.length === 18 ? ' base-services-grid-fill-page' : ''}`}>
            {pagedServices.map((resource) => {
              const authorized = resource.authorization.status === 'authorized'
              const authorizationLabel = resource.authorization.status === 'unauthorized' ? '授权' : '更新我的授权'
              return <Card key={resource.serviceId} className="sprint-card api-collection-card base-services-connection-card" styles={{ body: { padding: 20 } }}>
                <div className="api-collection-card-top base-services-connection-head">
                  <Space size={10} className="base-services-connection-title-wrap">
                    <AppIcon name={provider} size={24} />
                    <Typography.Text strong className="base-services-connection-title" title={resource.name}>{resource.name}</Typography.Text>
                  </Space>
                  <Tag color={authorized ? 'success' : resource.authorization.status === 'invalid' ? 'error' : 'default'}>{stateLabels[resource.authorization.status]}</Tag>
                </div>
                <Typography.Paragraph className="api-collection-description base-services-connection-url" title={resource.baseUrl}>{resource.baseUrl}</Typography.Paragraph>
                {provider === 'llm' && <div className="sprint-card-meta api-collection-meta-inline">
                  <span className="sprint-card-label">模型 ID</span>
                  <span className="api-collection-inline-value">{resource.modelId || '-'}</span>
                </div>}
                <div className="sprint-card-meta">
                  <span className="sprint-card-label">我的授权</span>
                  <span className="api-collection-inline-value">{authorized ? '可使用' : '未授权'}</span>
                </div>
                <div className="sprint-card-meta">
                  <span className="sprint-card-label">最近授权</span>
                  <span className="api-collection-inline-value">{formatTime(resource.authorization.lastAuthAt ?? undefined)}</span>
                </div>
                <div className="sprint-card-actions base-services-connection-actions">
                  <Tooltip title={authorizationLabel}>
                    <Button type="text" shape="circle" aria-label={authorizationLabel} icon={<SafetyCertificateOutlined />} disabled={saving} onClick={() => { credentials.resetFields(); setAuthorization(resource) }} />
                  </Tooltip>
                  {resource.authorization.status !== 'unauthorized' && <Popconfirm okText="确认" cancelText="取消" title="撤销我的授权？" description="只影响你本人，其他成员的授权保持有效。" onConfirm={() => remove(resource, true)}>
                    <Tooltip title="撤销我的授权"><Button type="text" shape="circle" danger aria-label="撤销我的授权" icon={<StopOutlined />} disabled={saving} /></Tooltip>
                  </Popconfirm>}
                  <ProjectActionButton action="manage" projectId={projectId} type="text" shape="circle" className="action-btn-update" title="编辑服务" aria-label={`编辑 ${resource.name}`} operation="edit" iconOnly onClick={() => openEditor(resource)} disabled={saving} />
                  <Popconfirm okText="确认" cancelText="取消" disabled={!can('manage')} title="删除这个项目服务？" description="所有成员将无法继续使用此服务的授权，相关未完成任务会终止。" onConfirm={() => remove(resource, false)}>
                    <ProjectActionButton action="manage" projectId={projectId} type="text" shape="circle" className="action-btn-delete" danger title="删除服务" aria-label={`删除 ${resource.name}`} operation="delete" iconOnly disabled={saving} />
                  </Popconfirm>
                </div>
              </Card>
            })}
          </div>
        )}
      </div>
      <div className="table-footer">
        <Typography.Text type="secondary">显示第 {services.length ? (currentPage - 1) * pageSize + 1 : 0} 条 - 第 {Math.min(currentPage * pageSize, services.length)} 条，共 {services.length} 条</Typography.Text>
        <Pagination current={currentPage} pageSize={pageSize} total={services.length} showSizeChanger pageSizeOptions={['18', '24', '30', '36', '48', '60']} onChange={(nextPage, nextSize) => { setPage(nextSize === pageSize ? nextPage : 1); setPageSize(nextSize) }} />
      </div>
    </div>
    <Modal forceRender okText="保存" cancelText="取消" title={editor === 'create' ? `新建 ${labels[provider]} 服务` : '编辑服务'} open={Boolean(editor)} onCancel={closeEditor} onOk={saveConfiguration} confirmLoading={saving} okButtonProps={{ disabled: !can('manage') }}>
      <Alert showIcon type="info" title="服务配置对项目成员可见，创建时无需填写个人凭据。" style={{ marginBottom: 16 }} />
      <Form form={configuration} layout="vertical" preserve={false}>
        <Form.Item name="name" label="服务名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={120} /></Form.Item>
        <Form.Item name="baseUrl" label="服务地址" rules={[{ required: true }, { type: 'url', message: '请输入完整的 http 或 https 地址' }]}><Input placeholder="https://…" disabled={editor !== 'create'} /></Form.Item>
        {provider === 'llm' && <Form.Item name="modelId" label="模型 ID" rules={[{ required: true, whitespace: true }]}><Input disabled={editor !== 'create'} maxLength={255} /></Form.Item>}
        {editor !== 'create' && <Typography.Text type="secondary">地址和模型用于确定授权对象，需要更换时请新建服务。</Typography.Text>}
      </Form>
    </Modal>
    <Modal forceRender cancelText="取消" title={`我的授权 · ${authorization?.name ?? ''}`} open={Boolean(authorization)} onCancel={closeAuthorization} onOk={saveAuthorization} confirmLoading={saving} okText="保存我的授权">
      <Form form={credentials} layout="vertical" preserve={false} autoComplete="off">
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
