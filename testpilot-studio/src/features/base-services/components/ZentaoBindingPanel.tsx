import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { normalizeInstanceUrl } from '../utils/personalConnections'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { LinkOutlined } from '@ant-design/icons'
import { Alert, Empty, Modal, Popconfirm, Select, Space, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import '@/features/base-services/styles/index.css'
import { api, listItems, type ZentaoBinding, type ZentaoBindingTargetType, type ZentaoConnection, type ZentaoRemoteOption } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'

const { Text, Title } = Typography

export type BindingDepth = 'project' | 'execution' | 'testtask' | 'story'

function getBindingId(binding: ZentaoBinding) {
  return binding.bindingId ?? binding.binding_id ?? ''
}



function getBindingRemoteResourceId(binding?: ZentaoBinding) {
  return binding?.remoteResourceId ?? binding?.remote_resource_id ?? ''
}

function getBindingRemoteName(binding?: ZentaoBinding) {
  return binding?.remoteNameSnapshot ?? binding?.remote_name_snapshot ?? ''
}

function getBindingBoundAt(binding?: ZentaoBinding) {
  return binding?.boundAt ?? binding?.bound_at ?? binding?.createdAt ?? binding?.created_at
}

function getRemoteOptionId(item: ZentaoRemoteOption) {
  const value = item.id ?? item.remoteResourceId ?? item.remote_resource_id ?? item.code
  return value === undefined || value === null ? '' : String(value)
}

function getRemoteOptionName(item: ZentaoRemoteOption) {
  const value = item.name ?? item.title ?? item.remoteNameSnapshot ?? item.remote_name_snapshot ?? item.code ?? getRemoteOptionId(item)
  return value === undefined || value === null ? '-' : String(value)
}

function mapRemoteOptions(items?: ZentaoRemoteOption[]) {
  return (items ?? [])
    .map((item) => {
      const value = getRemoteOptionId(item)
      if (!value) return null
      const name = getRemoteOptionName(item)
      return {
        label: `${name}${name !== value ? ` (${value})` : ''}`,
        value,
      }
    })
    .filter(Boolean) as Array<{ label: string; value: string }>
}

function getBindingConfig(targetType: ZentaoBindingTargetType, resourceId: string) {
  if (targetType === 'project') {
    return {
      bindingsKey: ['projectBindings', resourceId],
      getBindings: () => api.getProjectBindings(resourceId),
      createBinding: (remoteResourceId: string, connectionId: string) =>
        api.createProjectBinding(resourceId, { provider: 'zentao', connectionId, remoteResourceId }),
      deleteBinding: (bindingId: string) => api.deleteProjectBinding(resourceId, bindingId),
    }
  }

  if (targetType === 'sprint') {
    return {
      bindingsKey: ['sprintBindings', resourceId],
      getBindings: () => api.getSprintBindings(resourceId),
      createBinding: (remoteResourceId: string, connectionId: string) =>
        api.createSprintBinding(resourceId, { provider: 'zentao', connectionId, remoteResourceId }),
      deleteBinding: (bindingId: string) => api.deleteSprintBinding(resourceId, bindingId),
    }
  }

  return {
    bindingsKey: ['requirementBindings', resourceId],
    getBindings: () => api.getRequirementBindings(resourceId),
    createBinding: (remoteResourceId: string, connectionId: string) =>
      api.createRequirementBinding(resourceId, { provider: 'zentao', connectionId, remoteResourceId }),
    deleteBinding: (bindingId: string) => api.deleteRequirementBinding(resourceId, bindingId),
  }
}

function getRemoteResourceId(depth: BindingDepth, values: { projectId?: string; executionId?: string; leafId?: string }) {
  if (depth === 'project') return values.projectId
  if (depth === 'execution') return values.executionId
  return values.leafId
}

function getCurrentZentaoBinding(bindings?: ZentaoBinding[]) {
  return (bindings ?? []).find((binding) => binding.provider === 'zentao')
}

function getBindingStatusText(status?: string) {
  if (!status) return '-'
  if (status === 'active') return '已绑定'
  if (status === 'disabled') return '已停用'
  return status
}

function getBindingStatusClassName(status?: string) {
  if (status === 'active') return 'is-active'
  if (status === 'disabled') return 'is-disabled'
  return 'is-neutral'
}

function getBindingEntityLabel(targetType: ZentaoBindingTargetType) {
  if (targetType === 'project') return '项目'
  if (targetType === 'sprint') return '执行'
  return '需求'
}

function getLeafResourceLabel(depth: BindingDepth) {
  if (depth === 'story') return '禅道需求 Story'
  return '禅道测试单'
}

export function ZentaoBindingSummary({
  targetType,
  resourceId,
  variant = 'footer',
}: {
  targetType: ZentaoBindingTargetType
  resourceId: string
  variant?: 'footer' | 'toolbar' | 'settings'
}) {
  const bindingConfig = useMemo(() => getBindingConfig(targetType, resourceId), [resourceId, targetType])
  const bindingsQuery = useQuery({
    queryKey: bindingConfig.bindingsKey,
    queryFn: bindingConfig.getBindings,
    enabled: Boolean(resourceId),
  })
  const currentBinding = useMemo(() => getCurrentZentaoBinding(bindingsQuery.data), [bindingsQuery.data])

  if (variant === 'settings') {
    if (bindingsQuery.isPending) return <Text type="secondary">加载绑定信息…</Text>
    if (bindingsQuery.isError) return <Text type="danger">绑定信息加载失败</Text>
    if (!currentBinding) return <Text type="secondary">未绑定项目</Text>
    return <div className="project-settings-binding-details">
      <div className="project-settings-binding-line">
        <Text className="project-settings-binding-name">{getBindingRemoteName(currentBinding) || getBindingRemoteResourceId(currentBinding)}</Text>
        <Tag color={currentBinding.status === 'active' ? 'success' : 'default'}>{getBindingStatusText(currentBinding.status)}</Tag>
      </div>
      <Text type="secondary">项目 ID：{getBindingRemoteResourceId(currentBinding) || '-'}</Text>
    </div>
  }
  if (!currentBinding) return null

  const entityLabel = getBindingEntityLabel(targetType)
  const remoteName = getBindingRemoteName(currentBinding) || getBindingRemoteResourceId(currentBinding) || '-'
  const remoteId = getBindingRemoteResourceId(currentBinding) || '-'
  const statusText = getBindingStatusText(currentBinding.status)
  const summaryTitle = `禅道已绑定 ${entityLabel} ${remoteName} | ID ${remoteId} | ${statusText}`

  return (
    <div className={`zentao-binding-summary zentao-binding-summary-${variant}`} title={summaryTitle}>
      <div className="zentao-binding-summary-main">
        <Tag color="blue">禅道</Tag>
        <span className="zentao-binding-summary-key">{entityLabel}</span>
        <span className="zentao-binding-summary-name">{remoteName}</span>
        <span className="zentao-binding-summary-separator">/</span>
        <span className="zentao-binding-summary-key">ID</span>
        <span className="zentao-binding-summary-meta">{remoteId}</span>
      </div>
      <span className={`zentao-binding-summary-status ${getBindingStatusClassName(currentBinding.status)}`}>{statusText}</span>
    </div>
  )
}

export function ZentaoBindingModal({
  open,
  onClose,
  projectId,
  targetType,
  resourceId,
  parentProjectId,
  parentSprintId,
  depth,
  title = '禅道绑定',
}: {
  open: boolean
  onClose: () => void
  projectId: string
  targetType: ZentaoBindingTargetType
  resourceId: string
  parentProjectId?: string
  parentSprintId?: string
  depth: BindingDepth
  title?: string
}) {
  const queryClient = useQueryClient()
  const { can } = useProjectAccess(projectId)
  const [connectionId, setConnectionId] = useState<string>()
  const [remoteProjectId, setRemoteProjectId] = useState<string>()
  const [remoteExecutionId, setRemoteExecutionId] = useState<string>()
  const [remoteLeafResourceId, setRemoteLeafResourceId] = useState<string>()
  const bindingConfig = useMemo(() => getBindingConfig(targetType, resourceId), [resourceId, targetType])
  const leafResourceLabel = getLeafResourceLabel(depth)

  const connectionsQuery = useQuery({
    queryKey: ['zentaoConnections', projectId],
    queryFn: () => api.getZentaoConnections(projectId),
    enabled: open && Boolean(projectId),
  })
  const bindingsQuery = useQuery({
    queryKey: bindingConfig.bindingsKey,
    queryFn: bindingConfig.getBindings,
    enabled: open && Boolean(resourceId),
  })
  const parentProjectBindingsQuery = useQuery({
    queryKey: ['projectBindings', parentProjectId],
    queryFn: () => api.getProjectBindings(parentProjectId!),
    enabled: open && (targetType === 'sprint' || targetType === 'requirement') && Boolean(parentProjectId),
  })
  const parentSprintBindingsQuery = useQuery({
    queryKey: ['sprintBindings', parentSprintId],
    queryFn: () => api.getSprintBindings(parentSprintId!),
    enabled: open && targetType === 'requirement' && Boolean(parentSprintId),
  })
  const zentaoBindings = useMemo(() => listItems(bindingsQuery.data).filter((binding) => binding.provider === 'zentao'), [bindingsQuery.data])
  const currentBinding = zentaoBindings[0]
  const inheritedProjectBinding = useMemo(
    () => listItems(parentProjectBindingsQuery.data).find((binding) => binding.provider === 'zentao'),
    [parentProjectBindingsQuery.data],
  )
  const inheritedSprintBinding = useMemo(
    () => listItems(parentSprintBindingsQuery.data).find((binding) => binding.provider === 'zentao'),
    [parentSprintBindingsQuery.data],
  )

  const projectsQuery = useQuery({
    queryKey: ['zentaoRemoteProjects', projectId, connectionId],
    queryFn: () => api.getZentaoRemoteProjects(projectId, connectionId!),
    enabled: open && Boolean(projectId) && Boolean(connectionId),
  })
  const executionsQuery = useQuery({
    queryKey: ['zentaoRemoteExecutions', projectId, connectionId, remoteProjectId],
    queryFn: () => api.getZentaoRemoteExecutions(projectId, connectionId!, remoteProjectId!),
    enabled: open && Boolean(projectId) && Boolean(connectionId) && Boolean(remoteProjectId) && depth !== 'project',
  })
  const testtasksQuery = useQuery({
    queryKey: ['zentaoRemoteTestTasks', projectId, connectionId, remoteExecutionId],
    queryFn: () => api.getZentaoRemoteTestTasks(projectId, connectionId!, remoteExecutionId!),
    enabled: open && Boolean(projectId) && Boolean(connectionId) && Boolean(remoteExecutionId) && depth === 'testtask',
  })
  const storiesQuery = useQuery({
    queryKey: ['zentaoRemoteStories', projectId, connectionId, remoteExecutionId],
    queryFn: () => api.getZentaoRemoteStories(projectId, connectionId!, remoteExecutionId!),
    enabled: open && Boolean(projectId) && Boolean(connectionId) && Boolean(remoteExecutionId) && depth === 'story',
  })

  const connectionOptions = useMemo(
    () =>
      listItems(connectionsQuery.data).map((connection: ZentaoConnection) => ({
        label: `${connection.name}${connection.status === 'active' ? '' : `（${connection.status}）`}`,
        disabled: connection.status !== 'active',
        value: connection.connectionId,
      })),
    [connectionsQuery.data],
  )
  const projectOptions = useMemo(() => {
    const options = mapRemoteOptions(projectsQuery.data?.items)
    const inheritedProjectId = getBindingRemoteResourceId(inheritedProjectBinding)
    if (!inheritedProjectId || options.some((option) => option.value === inheritedProjectId)) return options

    const inheritedProjectName = getBindingRemoteName(inheritedProjectBinding) || inheritedProjectId
    return [
      {
        label: `${inheritedProjectName}${inheritedProjectName !== inheritedProjectId ? ` (${inheritedProjectId})` : ''}`,
        value: inheritedProjectId,
      },
      ...options,
    ]
  }, [inheritedProjectBinding, projectsQuery.data?.items])
  const executionOptions = useMemo(() => {
    const options = mapRemoteOptions(executionsQuery.data?.items)
    const inheritedExecutionId = getBindingRemoteResourceId(inheritedSprintBinding)
    if (!inheritedExecutionId || options.some((option) => option.value === inheritedExecutionId)) return options

    const inheritedExecutionName = getBindingRemoteName(inheritedSprintBinding) || inheritedExecutionId
    return [
      {
        label: `${inheritedExecutionName}${inheritedExecutionName !== inheritedExecutionId ? ` (${inheritedExecutionId})` : ''}`,
        value: inheritedExecutionId,
      },
      ...options,
    ]
  }, [executionsQuery.data?.items, inheritedSprintBinding])
  const leafResourceOptions = useMemo(() => {
    const options = mapRemoteOptions(depth === 'story' ? storiesQuery.data?.items : testtasksQuery.data?.items)
    const currentLeafResourceId = depth === 'testtask' || depth === 'story' ? getBindingRemoteResourceId(currentBinding) : ''
    if (!currentLeafResourceId || options.some((option) => option.value === currentLeafResourceId)) return options

    const currentLeafResourceName = getBindingRemoteName(currentBinding) || currentLeafResourceId
    return [
      {
        label: `${currentLeafResourceName}${currentLeafResourceName !== currentLeafResourceId ? ` (${currentLeafResourceId})` : ''}`,
        value: currentLeafResourceId,
      },
      ...options,
    ]
  }, [currentBinding, depth, storiesQuery.data?.items, testtasksQuery.data?.items])

  const bindingInstance = currentBinding?.instanceUrl || inheritedSprintBinding?.instanceUrl || inheritedProjectBinding?.instanceUrl
  useEffect(() => {
    const candidates = listItems(connectionsQuery.data).filter(c => c.status === 'active' && (!bindingInstance || normalizeInstanceUrl(c.baseUrl) === normalizeInstanceUrl(bindingInstance)))
    if (connectionId && candidates.some(c => c.connectionId === connectionId)) return
    setConnectionId(candidates.length === 1 ? candidates[0].connectionId : undefined)
  }, [connectionId, connectionsQuery.data, bindingInstance])

  useEffect(() => {
    if (!open || remoteProjectId) return
    const inheritedProjectId = getBindingRemoteResourceId(inheritedProjectBinding)
    if (inheritedProjectId) {
      setRemoteProjectId(inheritedProjectId)
      return
    }
    if (depth === 'project') {
      const currentProjectId = getBindingRemoteResourceId(currentBinding)
      if (currentProjectId) setRemoteProjectId(currentProjectId)
    }
  }, [currentBinding, depth, inheritedProjectBinding, open, remoteProjectId])

  useEffect(() => {
    if (!open || remoteExecutionId || depth === 'project') return
    if (depth === 'testtask' || depth === 'story') {
      const inheritedExecutionId = getBindingRemoteResourceId(inheritedSprintBinding)
      if (inheritedExecutionId) setRemoteExecutionId(inheritedExecutionId)
      return
    }
    const currentExecutionId = getBindingRemoteResourceId(currentBinding)
    if (currentExecutionId) setRemoteExecutionId(currentExecutionId)
  }, [currentBinding, depth, inheritedSprintBinding, open, remoteExecutionId])

  useEffect(() => {
    if (!open || remoteLeafResourceId || (depth !== 'testtask' && depth !== 'story')) return
    const currentLeafResourceId = getBindingRemoteResourceId(currentBinding)
    if (currentLeafResourceId) setRemoteLeafResourceId(currentLeafResourceId)
  }, [currentBinding, depth, open, remoteLeafResourceId])

  const selectedRemoteResourceId = getRemoteResourceId(depth, {
    projectId: remoteProjectId,
    executionId: remoteExecutionId,
    leafId: remoteLeafResourceId,
  })

  const saveBindingMutation = useMutation({
    mutationFn: async () => {
      if (!connectionId) throw new Error('请选择禅道连接')
      if (!selectedRemoteResourceId) throw new Error('请选择要绑定的禅道对象')

      if (!can('manage')) throw new Error('仅项目所有者可修改绑定')
      if (currentBinding && getBindingId(currentBinding)) {
        return api.updateZentaoBinding(targetType, resourceId, getBindingId(currentBinding), { connectionId, remoteResourceId: selectedRemoteResourceId })
      }

      return bindingConfig.createBinding(selectedRemoteResourceId, connectionId)
    },
    onSuccess: () => {
      message.success(currentBinding ? '禅道绑定已更新' : '禅道绑定已创建')
      queryClient.invalidateQueries({ queryKey: bindingConfig.bindingsKey })
      onClose()
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const deleteBindingMutation = useMutation({
    mutationFn: async () => {
      for (const binding of zentaoBindings) {
        const bindingId = getBindingId(binding)
        if (bindingId) {
          await bindingConfig.deleteBinding(bindingId)
        }
      }
    },
    onSuccess: () => {
      message.success('禅道绑定已解绑')
      queryClient.invalidateQueries({ queryKey: bindingConfig.bindingsKey })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  function handleConnectionChange(nextConnectionId: string) {
    setConnectionId(nextConnectionId)
    setRemoteProjectId(undefined)
    setRemoteExecutionId(undefined)
    setRemoteLeafResourceId(undefined)
  }

  function handleProjectChange(nextProjectId: string) {
    setRemoteProjectId(nextProjectId)
    setRemoteExecutionId(undefined)
    setRemoteLeafResourceId(undefined)
  }

  function handleExecutionChange(nextExecutionId: string) {
    setRemoteExecutionId(nextExecutionId)
    setRemoteLeafResourceId(undefined)
  }

  return (
    <Modal
      width={760}
      className="zentao-binding-modal"
      title={
        <Space size={8}>
          <LinkOutlined />
          <span>{title}</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <div className="zentao-binding-head">
        <Title level={5}>当前绑定</Title>
        {currentBinding ? (
          <Space size={8} wrap className="zentao-binding-current">
            <Tag color="blue">{getBindingRemoteName(currentBinding) || getBindingRemoteResourceId(currentBinding) || '-'}</Tag>
            <Text type="secondary">ID：{getBindingRemoteResourceId(currentBinding) || '-'}</Text>
            <Text type="secondary">状态：{getBindingStatusText(currentBinding.status)}</Text>
            <Text type="secondary">绑定时间：{formatTime(getBindingBoundAt(currentBinding))}</Text>
            <Popconfirm title="确认解绑当前禅道对象？" disabled={!can('manage')} onConfirm={() => deleteBindingMutation.mutate()}>
              <ProjectActionButton action="manage" projectId={projectId} danger size="small" loading={deleteBindingMutation.isPending}>
                解绑
              </ProjectActionButton>
            </Popconfirm>
          </Space>
        ) : (
          <Text type="secondary">当前未绑定禅道对象</Text>
        )}
      </div>

      {connectionsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(connectionsQuery.error)} /> : null}
      {!projectId ? <Alert showIcon type="info" title="请先选择项目" /> : null}
      {bindingsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(bindingsQuery.error)} /> : null}
      {parentProjectBindingsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(parentProjectBindingsQuery.error)} /> : null}
      {parentSprintBindingsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(parentSprintBindingsQuery.error)} /> : null}
      {projectsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(projectsQuery.error)} /> : null}
      {executionsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(executionsQuery.error)} /> : null}
      {testtasksQuery.error ? <Alert showIcon type="error" title={getErrorMessage(testtasksQuery.error)} /> : null}
      {storiesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(storiesQuery.error)} /> : null}
      {((targetType === 'sprint' || targetType === 'requirement') && inheritedProjectBinding) ||
      (targetType === 'requirement' && inheritedSprintBinding) ? (
        <div className="zentao-binding-inherit-note">
          <Text type="secondary">已自动带入上级绑定，可在下方修改</Text>
          {(targetType === 'sprint' || targetType === 'requirement') && inheritedProjectBinding ? (
            <Tag color="blue">
              项目：{getBindingRemoteName(inheritedProjectBinding) || getBindingRemoteResourceId(inheritedProjectBinding) || '-'}
            </Tag>
          ) : null}
          {targetType === 'requirement' && inheritedSprintBinding ? (
            <Tag color="cyan">
              执行：{getBindingRemoteName(inheritedSprintBinding) || getBindingRemoteResourceId(inheritedSprintBinding) || '-'}
            </Tag>
          ) : null}
        </div>
      ) : null}

      {connectionOptions.length === 0 && !connectionsQuery.isLoading ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无禅道连接，请先到基础服务中创建连接" />
      ) : (
        <div className="zentao-binding-form-row">
          <Select
            className="zentao-binding-select"
            loading={connectionsQuery.isLoading}
            value={connectionId}
            placeholder="选择禅道连接"
            options={connectionOptions.filter(option => !bindingInstance || listItems(connectionsQuery.data).some(c => c.connectionId === option.value && normalizeInstanceUrl(c.baseUrl) === normalizeInstanceUrl(bindingInstance)))}
            onChange={handleConnectionChange}
          />
          <Select
            className="zentao-binding-select"
            loading={projectsQuery.isLoading}
            value={remoteProjectId}
            placeholder={inheritedProjectBinding ? '已带入项目绑定，可修改' : '选择禅道项目'}
            options={projectOptions}
            disabled={!connectionId}
            onChange={handleProjectChange}
            showSearch
            optionFilterProp="label"
          />
          {depth !== 'project' ? (
            <Select
              className="zentao-binding-select"
              loading={executionsQuery.isLoading}
              value={remoteExecutionId}
              placeholder={inheritedSprintBinding ? '已带入迭代绑定，可修改' : '选择禅道执行'}
              options={executionOptions}
              disabled={!remoteProjectId}
              onChange={handleExecutionChange}
              showSearch
              optionFilterProp="label"
            />
          ) : null}
          {depth === 'testtask' || depth === 'story' ? (
            <Select
              className="zentao-binding-select"
              loading={depth === 'story' ? storiesQuery.isLoading : testtasksQuery.isLoading}
              value={remoteLeafResourceId}
              placeholder={`选择${leafResourceLabel}`}
              options={leafResourceOptions}
              disabled={!remoteExecutionId}
              onChange={setRemoteLeafResourceId}
              showSearch
              optionFilterProp="label"
            />
          ) : null}
          <ProjectActionButton action="manage" projectId={projectId}
            type="primary"
            className="action-btn-save"
            loading={saveBindingMutation.isPending}
            disabled={!can('manage') || !connectionId || !selectedRemoteResourceId}
            onClick={() => saveBindingMutation.mutate()}
          >
            {currentBinding ? '重新绑定' : '绑定'}
          </ProjectActionButton>
        </div>
      )}
    </Modal>
  )
}
