import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiOutlined } from '@ant-design/icons'
import { Alert, Card, Empty, Popconfirm, Space, Tag, Tooltip, Typography } from 'antd'
import { ListPagination } from '@/shared/components/ListPagination'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { ProjectAccessScope } from '@/domain/projects/components/ProjectAccessScope'
import { useProjectAccess } from '@/domain/projects/hooks/useProjectAccess'
import { listItems } from '@/shared/api/request'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import { cx } from '@/shared/utils/cx'
import {
  serviceCardActionsClass,
  serviceCardBodyClass,
  serviceCardClass,
  serviceCardEmptyClass,
  serviceCardGridClass,
  serviceCardHeadClass,
  serviceCardLabelClass,
  serviceCardMetaClass,
  serviceCardScrollClass,
  serviceCardShellClass,
  serviceCardTitleClass,
  serviceCardTitleWrapClass,
  serviceCardUrlClass,
  serviceCardValueClass,
  tableFooterClass,
  tableScrollClass,
} from '@/shared/utils/surfaceClasses'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { api } from '@/services/api'
import type {
  CreateMonitoringConnectionPayload,
  MonitoringConnection,
  UpdateMonitoringConnectionPayload,
} from '../types'
import { PerfMonitoringDrawer } from './PerfMonitoringDrawer'

const { Paragraph, Text } = Typography

const authLabels = { none: 'None', basic: 'Basic', bearer: 'Bearer', headers: 'Headers' }

export function PerfMonitoringPanel({ projectId, toolbarActions }: {
  projectId?: string
  toolbarActions?: HTMLElement | null
}) {
  if (!projectId) return <Empty description="请先选择项目" />
  return <ProjectAccessScope projectId={projectId}>
    <MonitoringCatalog projectId={projectId} toolbarActions={toolbarActions} />
  </ProjectAccessScope>
}

function MonitoringCatalog({ projectId, toolbarActions }: {
  projectId: string
  toolbarActions?: HTMLElement | null
}) {
  const queryClient = useQueryClient()
  const { can } = useProjectAccess(projectId)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<MonitoringConnection | null>(null)
  const connectionsQuery = useQuery({
    queryKey: ['perfMonitoringConnections', projectId],
    queryFn: () => api.listMonitoringConnections(projectId),
  })
  const connections = listItems(connectionsQuery.data)
  const currentPage = Math.min(page, Math.max(1, Math.ceil(connections.length / pageSize)))
  const paged = connections.slice((currentPage - 1) * pageSize, currentPage * pageSize)

  const saveMutation = useMutation({
    mutationFn: (payload: CreateMonitoringConnectionPayload | UpdateMonitoringConnectionPayload) =>
      editing
        ? api.updateMonitoringConnection(editing.connectionId, payload)
        : api.createMonitoringConnection(projectId, payload as CreateMonitoringConnectionPayload),
    onSuccess: () => {
      message.success(editing ? '监控接入已更新' : '监控接入已创建')
      setDrawerOpen(false)
      setEditing(null)
      queryClient.invalidateQueries({ queryKey: ['perfMonitoringConnections', projectId] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (connectionId: string) => api.deleteMonitoringConnection(connectionId),
    onSuccess: () => {
      message.success('监控接入已删除；历史运行仍保留接入快照')
      queryClient.invalidateQueries({ queryKey: ['perfMonitoringConnections', projectId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const createButton = <ProjectActionButton
    action="manage"
    projectId={projectId}
    type="primary"
    className="action-btn-create"
    operation="create"
    onClick={() => { setEditing(null); setDrawerOpen(true) }}
  >
    新建监控接入
  </ProjectActionButton>

  return <>
    {toolbarActions ? createPortal(createButton, toolbarActions) : createButton}
    {connectionsQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(connectionsQuery.error)} /> : null}
    <div className={cx('base-services-connection-shell', serviceCardShellClass)}>
      <div className={cx('table-body-scroll base-services-card-scroll tp-list-scroll', serviceCardScrollClass, tableScrollClass)}>
        {connectionsQuery.isPending ? (
          <div className="grid min-h-[220px] place-items-center"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="监控接入加载中..." /></div>
        ) : connections.length === 0 ? (
          <div className={cx('base-services-empty-card base-services-empty-card-list', serviceCardEmptyClass)}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={can('manage') ? '暂无监控接入，先创建后再发起性能测试' : '暂无监控接入，请项目所有者创建'}
            />
          </div>
        ) : (
          <div className={serviceCardGridClass}>
            {paged.map((connection) => <Card
              key={connection.connectionId}
              className={cx('base-services-connection-card', serviceCardClass)}
              classNames={{ body: serviceCardBodyClass }}
            >
              <div className={cx('base-services-connection-head', serviceCardHeadClass)}>
                <Space size={10} className={serviceCardTitleWrapClass}>
                  <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-app-accent-surface text-app-accent">
                    <ApiOutlined />
                  </span>
                  <Text strong className={serviceCardTitleClass} title={connection.name}>{connection.name}</Text>
                </Space>
                <Tag color={connection.enabled ? 'success' : 'default'}>{connection.enabled ? '已启用' : '已停用'}</Tag>
              </div>
              <Paragraph className={serviceCardUrlClass} style={{ display: '-webkit-box' }} title={connection.remoteWriteUrl} ellipsis>
                {connection.remoteWriteUrl}
              </Paragraph>
              <div className={cx('sprint-card-meta', serviceCardMetaClass)}>
                <span className={serviceCardLabelClass}>认证</span>
                <Space size={4} wrap>
                  <Tag>写入 {authLabels[connection.remoteWriteAuthType]}</Tag>
                  {connection.hasRemoteWriteCredentials
                    ? <Tag color="blue">凭据已配置</Tag>
                    : <Tag>无凭据</Tag>}
                </Space>
              </div>
              <div className={cx('sprint-card-meta', serviceCardMetaClass)}>
                <span className={serviceCardLabelClass}>最近更新</span>
                <span className={serviceCardValueClass}>{formatTime(connection.updatedAt)}</span>
              </div>
              <div className={cx('sprint-card-actions base-services-connection-actions', serviceCardActionsClass)}>
                <Tooltip title="编辑监控接入">
                  <ProjectActionButton
                    action="manage"
                    projectId={projectId}
                    type="text"
                    shape="circle"
                    className="action-btn-update"
                    operation="edit"
                    iconOnly
                    aria-label={`编辑 ${connection.name}`}
                    onClick={() => { setEditing(connection); setDrawerOpen(true) }}
                  />
                </Tooltip>
                <Popconfirm
                  title="删除这个监控接入？"
                  description="历史运行会保留接入快照，但新运行不能再选择它。"
                  okText="确认"
                  cancelText="取消"
                  onConfirm={() => deleteMutation.mutate(connection.connectionId)}
                >
                  <ProjectActionButton
                    action="manage"
                    projectId={projectId}
                    type="text"
                    shape="circle"
                    className="action-btn-delete"
                    operation="delete"
                    iconOnly
                    danger
                    aria-label={`删除 ${connection.name}`}
                    loading={deleteMutation.isPending && deleteMutation.variables === connection.connectionId}
                  />
                </Popconfirm>
              </div>
            </Card>)}
          </div>
        )}
      </div>
      <div className={cx('table-footer', tableFooterClass)}>
        <ListPagination
          loading={connectionsQuery.isFetching}
          current={currentPage}
          pageSize={pageSize}
          total={connections.length}
          onChange={(nextPage, nextSize) => {
            setPage(nextSize === pageSize ? nextPage : 1)
            setPageSize(nextSize)
          }}
        />
      </div>
    </div>
    <PerfMonitoringDrawer
      open={drawerOpen}
      editing={editing}
      saving={saveMutation.isPending}
      onClose={() => { setDrawerOpen(false); setEditing(null) }}
      onSubmit={async (payload) => { await saveMutation.mutateAsync(payload) }}
    />
  </>
}
