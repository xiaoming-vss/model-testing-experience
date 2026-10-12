import { Card, Tag, Tooltip, Typography } from 'antd'
import { ActionButton } from '@/shared/components/ActionButton'
import type { ReactNode } from 'react'
import { AppIcon } from '@/shared/icons'
import { formatTime } from '@/utils/format'
import type { SharedService } from '../api/sharedServices.api'
import '../styles/zentao-mcp-service.css'

export function ZentaoMcpServiceCard({ resource, checking, onRefresh, actions }: {
  resource: SharedService
  checking: boolean
  onRefresh: () => Promise<void>
  actions: ReactNode
}) {
  const authorized = resource.authorization.status === 'authorized'
  const pending = resource.instanceResetRequired
  const status = checking ? '检查中' : pending ? '需更新配置' : resource.connectionStatus === 'available' ? '连接正常' : resource.connectionStatus === 'error' ? '连接异常' : '未检查'
  const authorization = authorized ? '已配置授权' : resource.authorization.status === 'invalid' ? '授权已失效' : '本人未授权'
  const instance = pending ? resource.pendingInstanceUrl : resource.zentaoInstanceUrl
  return <Card className="sprint-card api-collection-card base-services-connection-card base-services-mcp-card">
    <div className="api-collection-card-top base-services-connection-head">
      <div className="base-services-connection-title-wrap base-services-mcp-title">
        <AppIcon name="zentao" size={24} />
        <Typography.Text strong className="base-services-connection-title" title={resource.name}>{resource.name}</Typography.Text>
      </div>
      <Tooltip title={authorized ? '本人已配置授权，业务权限在操作时校验' : '仅使用你本人的 Token'}>
        <Tag color={authorized ? 'success' : resource.authorization.status === 'invalid' ? 'error' : 'default'}>{authorization}</Tag>
      </Tooltip>
      {authorized && <ActionButton operation="refresh" className="base-services-mcp-refresh app-action-icon" aria-label="刷新实例信息" loading={checking} onClick={() => void onRefresh()} />}
    </div>
    <Typography.Paragraph className="api-collection-description base-services-connection-url" title={resource.baseUrl}>{resource.baseUrl}</Typography.Paragraph>
    <div className="sprint-card-meta api-collection-meta-inline">
      <span className="sprint-card-label">{pending ? '新禅道实例' : '禅道实例'}</span>
      <span className="api-collection-inline-value base-services-mcp-instance" title={instance}>{instance || (authorized ? '尚未读取' : '授权后读取')}</span>
    </div>
    <div className="sprint-card-meta">
      <span className="sprint-card-label">连接状态</span>
      <div className="base-services-mcp-status">
        <Tooltip title={pending ? '禅道目标已变更，请在编辑服务中勾选确认后保存' : resource.instanceError || (authorized ? '业务权限在操作时校验' : '配置本人 Token 后读取实例')}>
          <span className="api-collection-inline-value">{status}</span>
        </Tooltip>
      </div>
    </div>
    <div className="sprint-card-meta">
      <span className="sprint-card-label">最近授权</span>
      <span className="api-collection-inline-value">{formatTime(resource.authorization.lastAuthAt ?? undefined)}</span>
    </div>
    {actions}
  </Card>
}
