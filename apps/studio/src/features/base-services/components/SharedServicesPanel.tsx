import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { ListPagination } from '@/shared/components/ListPagination'
import { SharedServiceDialogs } from './SharedServiceDialogs'
import { ZentaoMcpServiceCard } from './ZentaoMcpServiceCard'
import { AppIcon } from '@/shared/icons'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { SafetyCertificateOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Form, Popconfirm, Space, Tag, Tooltip, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { listItems } from '@/shared/api/request'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import { sharedServicesApi as api, type PersonalAuthorization, type ServiceConfiguration, type ServiceProvider, type SharedService } from '../api/sharedServices.api'

const labels = { llm: 'LLM', zentao: '禅道', gitlab: 'GitLab', mcp: 'MCP' }
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
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [configuration] = Form.useForm<ServiceConfiguration>()
  const [credentials] = Form.useForm<PersonalAuthorization>()
  const query = useQuery({
    queryKey: ['sharedServices', projectId, provider],
    queryFn: () => api.list(projectId, provider),
  })
  const templates = useQuery({
    queryKey: ['mcpTemplates', projectId],
    queryFn: () => api.mcpTemplates(projectId),
    enabled: provider === 'mcp',
  })
  const mcpTemplate = listItems(templates.data)[0]
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
    if (resource !== 'create') configuration.setFieldsValue({ name: resource.name, baseUrl: resource.baseUrl, modelId: resource.modelId, templateId: resource.templateId ?? undefined })
    else if (provider === 'mcp') configuration.setFieldsValue({ templateId: 'zentao' })
    setEditor(resource)
  }
  const saveConfiguration = async () => {
    if (!can('manage') || !editor) return
    const values = await configuration.validateFields().catch(() => null)
    if (!values) return
    setSaving(true)
    try {
      if (editor === 'create') {
        if (provider === 'mcp' && !mcpTemplate) return
        await api.create(projectId, provider, {
          name: values.name.trim(), baseUrl: values.baseUrl.trim(),
          ...(provider === 'llm' ? { modelId: values.modelId?.trim() } : {}),
          ...(provider === 'mcp' ? { templateId: values.templateId } : {}),
        })
        message.success('服务配置已保存，请单独完成我的授权')
      } else {
        if (provider === 'mcp') await api.rename(projectId, provider, editor.serviceId, values.name.trim(), values.baseUrl.trim(), values.confirmInstanceSwitch === true)
        else await api.rename(projectId, provider, editor.serviceId, values.name.trim())
      }
      closeEditor()
      if (provider === 'mcp' && values.confirmInstanceSwitch) {
        message.success('配置已保存，禅道目标已重新核对')
        await client.invalidateQueries()
      } else await refresh()
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
      message.success(provider === 'mcp' ? '我的授权已保存，实例信息将自动读取' : '我的授权已保存')
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
  const createButton = <ProjectActionButton action="manage" projectId={projectId} type="primary" className="action-btn-create" operation="create" disabled={provider === 'mcp' && (templates.isPending || templates.isError || query.isPending || query.isError)} onClick={() => openEditor('create')}>{provider === 'mcp' ? '新增 MCP' : '新建服务'}</ProjectActionButton>
  return <>
    {toolbarActions ? createPortal(createButton, toolbarActions) : createButton}
    {provider === 'mcp' && templates.isError && <Alert type="error" showIcon title={getErrorMessage(templates.error)} />}
    {query.isError && <Alert type="error" showIcon title={getErrorMessage(query.error)} />}
    <div className="base-services-connection-shell">
      <div className="table-body-scroll sprint-card-scroll base-services-card-scroll tp-list-scroll">
        {query.isPending || (provider === 'mcp' && templates.isPending) ? (
          <div className="sprint-card-loading"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`${labels[provider]} 服务加载中...`} /></div>
        ) : services.length === 0 ? (
          <div className="base-services-empty-card base-services-empty-card-list">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={can('manage') ? provider === 'mcp' ? '暂无 MCP，先新增 MCP，再配置本人授权' : '暂无服务，先创建服务，再单独授权' : '暂无服务，请项目所有者创建'} />
          </div>
        ) : (
          <div className="api-collection-grid base-services-connection-grid">
            {pagedServices.map((resource) => {
              const authorized = resource.authorization.status === 'authorized'
              const authorizationLabel = resource.authorization.status === 'unauthorized' ? '授权' : '更新我的授权'
              const actions = <div className="sprint-card-actions base-services-connection-actions">
                  <Tooltip title={authorizationLabel}>
                    <Button type="text" shape="circle" className="app-action app-action-icon app-action-save" aria-label={authorizationLabel} icon={<SafetyCertificateOutlined />} disabled={saving} onClick={() => { credentials.resetFields(); setAuthorization(resource) }}></Button>
                  </Tooltip>
                  {resource.authorization.status !== 'unauthorized' && <Popconfirm okText="确认" cancelText="取消" title="撤销我的授权？" description="只影响你本人，其他成员的授权保持有效。" onConfirm={() => remove(resource, true)}>
                    <Tooltip title="撤销我的授权"><Button type="text" shape="circle" danger className="app-action app-action-icon app-action-delete" aria-label="撤销我的授权" icon={<StopOutlined />} disabled={saving} /></Tooltip>
                  </Popconfirm>}
                  <ProjectActionButton action="manage" projectId={projectId} type="text" shape="circle" className="action-btn-update" title="编辑服务" aria-label={`编辑 ${resource.name}`} operation="edit" iconOnly onClick={() => openEditor(resource)} disabled={saving}></ProjectActionButton>
                  <Popconfirm okText="确认" cancelText="取消" disabled={!can('manage')} title="删除这个项目服务？" description={provider === 'mcp' ? '删除服务会同时删除所有成员的个人授权。' : '所有成员将无法继续使用此服务的授权，相关未完成任务会终止。'} onConfirm={() => remove(resource, false)}>
                    <ProjectActionButton action="manage" projectId={projectId} type="text" shape="circle" className="action-btn-delete" danger title="删除服务" aria-label={`删除 ${resource.name}`} operation="delete" iconOnly disabled={saving} />
                  </Popconfirm>
                </div>
              if (provider === 'mcp') return <ZentaoMcpServiceCard key={resource.serviceId} resource={resource} checking={query.isFetching} onRefresh={refresh} actions={actions} />
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
                {actions}
              </Card>
            })}
          </div>
        )}
      </div>
      <div className="table-footer">
        <ListPagination loading={query.isFetching || query.isError} current={page} pageSize={pageSize} total={services.length} onChange={(nextPage, nextSize) => { setPage(nextSize === pageSize ? nextPage : 1); setPageSize(nextSize) }} />
      </div>
    </div>
    <SharedServiceDialogs provider={provider} providerLabel={labels[provider]} editor={editor} authorization={authorization} configuration={configuration} credentials={credentials} saving={saving} closeEditor={closeEditor} closeAuthorization={closeAuthorization} saveConfiguration={saveConfiguration} saveAuthorization={saveAuthorization} />
  </>
}
