import { Card, Tag, Tooltip, Typography } from 'antd'
import { ActionButton } from '@/shared/components/ActionButton'
import type { ReactNode } from 'react'
import { AppIcon } from '@/shared/icons'
import { formatTime } from '@/utils/format'
import { cx } from '@/shared/utils/cx'
import {
  serviceCardBodyClass,
  serviceCardClass,
  serviceCardHeadClass,
  serviceCardLabelClass,
  serviceCardMetaClass,
  serviceCardTitleClass,
  serviceCardTitleWrapClass,
  serviceCardUrlClass,
  serviceCardValueClass,
  serviceCardValueInlineClass,
} from '@/shared/utils/surfaceClasses'
import type { SharedService } from '../api/sharedServices.api'

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
  return <Card className={cx('base-services-connection-card base-services-mcp-card', serviceCardClass)} classNames={{ body: serviceCardBodyClass }}>
    <div className={cx('base-services-connection-head', serviceCardHeadClass)}>
      <div className={cx('base-services-mcp-title flex flex-1 items-center gap-2.5', serviceCardTitleWrapClass)}>
        <AppIcon name="zentao" size={24} />
        <Typography.Text strong className={serviceCardTitleClass} title={resource.name}>{resource.name}</Typography.Text>
      </div>
      <Tooltip title={authorized ? '本人已配置授权，业务权限在操作时校验' : '仅使用你本人的 Token'}>
        <Tag color={authorized ? 'success' : resource.authorization.status === 'invalid' ? 'error' : 'default'}>{authorization}</Tag>
      </Tooltip>
      {authorized && <ActionButton operation="refresh" className="base-services-mcp-refresh app-action-icon" aria-label="刷新实例信息" loading={checking} onClick={() => void onRefresh()} />}
    </div>
    <Typography.Paragraph className={serviceCardUrlClass} style={{ display: '-webkit-box' }} title={resource.baseUrl}>{resource.baseUrl}</Typography.Paragraph>
    <div className={cx('sprint-card-meta', serviceCardMetaClass)}>
      <span className={serviceCardLabelClass}>{pending ? '新禅道实例' : '禅道实例'}</span>
      <span className={cx('base-services-mcp-instance', serviceCardValueInlineClass)} title={instance}>{instance || (authorized ? '尚未读取' : '授权后读取')}</span>
    </div>
    <div className={cx('sprint-card-meta', serviceCardMetaClass)}>
      <span className={serviceCardLabelClass}>连接状态</span>
      <div className="base-services-mcp-status flex h-[22px] min-w-0 items-center gap-1">
        <Tooltip title={pending ? '禅道目标已变更，请在编辑服务中勾选确认后保存' : resource.instanceError || (authorized ? '业务权限在操作时校验' : '配置本人 Token 后读取实例')}>
          <span className={serviceCardValueClass}>{status}</span>
        </Tooltip>
      </div>
    </div>
    <div className={cx('sprint-card-meta', serviceCardMetaClass)}>
      <span className={serviceCardLabelClass}>最近授权</span>
      <span className={serviceCardValueClass}>{formatTime(resource.authorization.lastAuthAt ?? undefined)}</span>
    </div>
    {actions}
  </Card>
}
