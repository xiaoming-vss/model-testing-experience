import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { sharedServicesApi } from '../api/sharedServices.api'
import { zentaoMcpApi } from '../api/zentaoMcp.api'
import { normalizeInstanceUrl } from '../utils/personalConnections'
import { useProjectAccess } from '@/domain/projects/hooks/useProjectAccess'
import { LinkOutlined } from '@ant-design/icons'
import { Alert, Checkbox, Modal, Popconfirm, Select, Space, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api, listItems, type ZentaoBinding, type ZentaoBindingTargetType, type ZentaoRemoteOption } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'

const { Text, Title } = Typography

export type BindingDepth = 'project' | 'execution' | 'story'

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
      createBinding: (remoteResourceId: string, mcpServiceId?: string) =>
        api.createProjectBinding(resourceId, { provider: 'zentao', remoteResourceId, mcpServiceId }),
      deleteBinding: (bindingId: string) => api.deleteProjectBinding(resourceId, bindingId),
    }
  }

  if (targetType === 'sprint') {
    return {
      bindingsKey: ['sprintBindings', resourceId],
      getBindings: () => api.getSprintBindings(resourceId),
      createBinding: (remoteResourceId: string) =>
        api.createSprintBinding(resourceId, { provider: 'zentao', remoteResourceId }),
      deleteBinding: (bindingId: string) => api.deleteSprintBinding(resourceId, bindingId),
    }
  }

  return {
    bindingsKey: ['requirementBindings', resourceId],
    getBindings: () => api.getRequirementBindings(resourceId),
    createBinding: (remoteResourceId: string) =>
      api.createRequirementBinding(resourceId, { provider: 'zentao', remoteResourceId }),
    deleteBinding: (bindingId: string) => api.deleteRequirementBinding(resourceId, bindingId),
  }
}

function getRemoteResourceId(depth: BindingDepth, values: { projectId?: string; executionId?: string; leafId?: string }) {
  if (depth === 'project') return values.projectId
  if (depth === 'execution') return values.executionId
  return values.leafId
}

function getCurrentZentaoBinding(bindings?: ZentaoBinding[]) {
  return (bindings ?? []).find((binding) => binding.provider === 'zentao' && binding.status === 'active')
}

function getBindingStatusText(status?: string) {
  if (!status) return '-'
  if (status === 'active') return '已绑定'
  if (status === 'disabled') return '已停用'
  return status
}

function getBindingEntityLabel(targetType: ZentaoBindingTargetType) {
  if (targetType === 'project') return '项目'
  if (targetType === 'sprint') return '执行'
  return '需求'
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
  }
  return <ZentaoBindingBadge targetType={targetType} binding={currentBinding} variant={variant} />
}

/** Render list-provided metadata without issuing a per-row binding query. */
export function ZentaoBindingBadge({ targetType, binding: currentBinding, variant = 'footer' }: {
  targetType: ZentaoBindingTargetType
  binding: ZentaoBinding | null | undefined
  variant?: 'footer' | 'toolbar' | 'settings'
}) {
  if (variant === 'settings') {
    if (!currentBinding) return <Text type="secondary">未绑定项目</Text>
    return <div className="settingsDetails mt-3 flex flex-col gap-1.5">
      <div className="settingsLine flex items-start justify-between gap-3">
        <Text className="settingsName min-w-0 [overflow-wrap:anywhere]">{getBindingRemoteName(currentBinding) || getBindingRemoteResourceId(currentBinding)}</Text>
        <Tag className="shrink-0" color={currentBinding.status === 'active' ? 'success' : 'default'}>{getBindingStatusText(currentBinding.status)}</Tag>
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

  const statusClass = currentBinding.status === 'active'
    ? 'text-[var(--app-accent)] border-[var(--app-testing-active-border)] bg-[var(--app-editor-focus-ring)]'
    : currentBinding.status === 'disabled'
      ? 'text-[var(--app-service-status-disabled-text)] border-[var(--app-service-status-disabled-border)] bg-[var(--app-service-status-disabled-bg)]'
      : 'text-[var(--app-result-warning-text)] border-[var(--app-service-status-warning-border)] bg-[var(--app-service-status-warning-bg)]'

  return (
    <div className="summary flex min-w-0 max-w-full items-center gap-2 whitespace-nowrap text-xs leading-[18px] text-[var(--tp-text-muted)]" title={summaryTitle}>
      <div className="summaryMain flex min-w-0 items-center gap-1.5 overflow-hidden">
        <Tag color="blue" className="me-0 shrink-0 rounded-full px-1.5 text-[11px] leading-[18px]">禅道</Tag>
        <span className="summaryKey flex-none text-[var(--app-service-text-label)]">{entityLabel}</span>
        <span className="summaryName min-w-0 flex-none overflow-hidden text-ellipsis font-semibold text-[var(--tp-text)]">{remoteName}</span>
        <span className="summarySeparator flex-none text-[var(--app-service-text-placeholder)]">/</span>
        <span className="summaryKey flex-none text-[var(--app-service-text-label)]">ID</span>
        <span className="summaryMeta flex-none overflow-hidden text-ellipsis">{remoteId}</span>
      </div>
      <span className={`flex-none rounded-full border px-2 text-[11px] leading-[18px] ${statusClass}`}>{statusText}</span>
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
  const [selectedMcpId, setSelectedMcpId] = useState<string>()
  const [confirmInstanceSwitch, setConfirmInstanceSwitch] = useState(false)
  const [mcpChanged, setMcpChanged] = useState(false)
  const [remoteProjectId, setRemoteProjectId] = useState<string>()
  const [remoteExecutionId, setRemoteExecutionId] = useState<string>()
  const [remoteLeafResourceId, setRemoteLeafResourceId] = useState<string>()
  const bindingConfig = useMemo(() => getBindingConfig(targetType, resourceId), [resourceId, targetType])
  const leafResourceLabel = '禅道需求'

  const mcpQuery = useQuery({
    queryKey: ['sharedServices', projectId, 'mcp'],
    queryFn: () => sharedServicesApi.list(projectId, 'mcp'),
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
  const zentaoBindings = useMemo(() => listItems(bindingsQuery.data).filter((binding) => binding.provider === 'zentao' && binding.status === 'active'), [bindingsQuery.data])
  const currentBinding = zentaoBindings[0]
  const inheritedProjectBinding = useMemo(
    () => targetType === 'project' ? undefined : listItems(parentProjectBindingsQuery.data).find((binding) => binding.provider === 'zentao' && binding.status === 'active'),
    [parentProjectBindingsQuery.data, targetType],
  )
  const inheritedSprintBinding = useMemo(
    () => listItems(parentSprintBindingsQuery.data).find((binding) => binding.provider === 'zentao' && binding.status === 'active'),
    [parentSprintBindingsQuery.data],
  )

  const mcps = listItems(mcpQuery.data).filter(service => service.templateId === 'zentao')
  const rootBinding = targetType === 'project' ? currentBinding : inheritedProjectBinding
  const legacyMatches = mcps.filter(service => rootBinding?.instanceUrl && normalizeInstanceUrl(service.zentaoInstanceUrl || '') === normalizeInstanceUrl(rootBinding.instanceUrl))
  const inheritedMcpId = rootBinding?.mcpServiceId || (mcps.length === 1 ? mcps[0].serviceId : legacyMatches.length === 1 ? legacyMatches[0].serviceId : undefined)
  const effectiveMcpId = targetType === 'project' ? selectedMcpId || inheritedMcpId : inheritedMcpId
  const mcp = mcps.find(service => service.serviceId === effectiveMcpId)
  const bindingInstance = currentBinding?.instanceUrl || inheritedSprintBinding?.instanceUrl || inheritedProjectBinding?.instanceUrl
  const instanceSwitch = targetType === 'project' && Boolean(currentBinding?.instanceUrl && mcp?.zentaoInstanceUrl && normalizeInstanceUrl(currentBinding.instanceUrl) !== normalizeInstanceUrl(mcp.zentaoInstanceUrl))
  const mcpReason = !mcp ? (mcps.length === 0 ? '请先在基础服务 → MCP 中配置禅道 MCP' : effectiveMcpId ? '项目绑定所选 MCP 已不存在，请在项目绑定中重新选择' : targetType === 'project' ? '请选择项目使用的禅道 MCP' : '请先在项目绑定中选择禅道 MCP')
    : !mcp.zentaoInstanceUrl ? (mcp.instanceError || '无法从 MCP 读取禅道实例，请检查 MCP 服务')
      : targetType !== 'project' && bindingInstance && normalizeInstanceUrl(mcp.zentaoInstanceUrl) !== normalizeInstanceUrl(bindingInstance) ? '项目 MCP 的禅道实例与已有绑定不一致'
        : mcp.authorization.status !== 'authorized' ? '请在基础服务 → MCP 中配置本人的 Token' : ''
  const mcpReady = Boolean(mcp && !mcpReason && bindingsQuery.isSuccess && (targetType === 'project' || parentProjectBindingsQuery.isSuccess) && (targetType !== 'requirement' || parentSprintBindingsQuery.isSuccess))
  const parentReady = targetType === 'project' || Boolean(inheritedProjectBinding && (targetType !== 'requirement' || inheritedSprintBinding))
  const projectsQuery = useQuery({
    queryKey: ['zentaoMcpProjects', projectId, mcp?.serviceId, mcp?.authorization.connectionId, mcp?.authorization.lastAuthAt],
    queryFn: () => zentaoMcpApi.resources(projectId, 'projects', undefined, mcp?.serviceId),
    enabled: open && mcpReady,
  })
  const executionsQuery = useQuery({
    queryKey: ['zentaoMcpExecutions', projectId, mcp?.serviceId, mcp?.authorization.connectionId, mcp?.authorization.lastAuthAt, remoteProjectId],
    queryFn: () => zentaoMcpApi.resources(projectId, 'executions', remoteProjectId!, mcp?.serviceId),
    enabled: open && mcpReady && Boolean(remoteProjectId) && depth !== 'project',
  })
  const storiesQuery = useQuery({
    queryKey: ['zentaoMcpStories', projectId, mcp?.serviceId, mcp?.authorization.connectionId, mcp?.authorization.lastAuthAt, remoteExecutionId],
    queryFn: () => zentaoMcpApi.resources(projectId, 'stories', remoteExecutionId!, mcp?.serviceId),
    enabled: open && mcpReady && Boolean(remoteExecutionId) && depth === 'story',
  })

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
    const options = mapRemoteOptions(storiesQuery.data?.items)
    const currentLeafResourceId = depth === 'story' ? getBindingRemoteResourceId(currentBinding) : ''
    if (!currentLeafResourceId || options.some((option) => option.value === currentLeafResourceId)) return options

    const currentLeafResourceName = getBindingRemoteName(currentBinding) || currentLeafResourceId
    return [
      {
        label: `${currentLeafResourceName}${currentLeafResourceName !== currentLeafResourceId ? ` (${currentLeafResourceId})` : ''}`,
        value: currentLeafResourceId,
      },
      ...options,
    ]
  }, [currentBinding, depth, storiesQuery.data?.items])

  useEffect(() => {
    setRemoteProjectId(undefined)
    setRemoteExecutionId(undefined)
    setRemoteLeafResourceId(undefined)
    setSelectedMcpId(undefined)
    setConfirmInstanceSwitch(false)
    setMcpChanged(false)
  }, [open, projectId, resourceId])

  useEffect(() => {
    if (!open || remoteProjectId || mcpChanged) return
    const inheritedProjectId = getBindingRemoteResourceId(inheritedProjectBinding)
    if (inheritedProjectId) {
      setRemoteProjectId(inheritedProjectId)
      return
    }
    if (depth === 'project') {
      const currentProjectId = getBindingRemoteResourceId(currentBinding)
      if (currentProjectId) setRemoteProjectId(currentProjectId)
    }
  }, [currentBinding, depth, inheritedProjectBinding, open, remoteProjectId, mcpChanged])

  useEffect(() => {
    if (!open || remoteExecutionId || depth === 'project') return
    if (depth === 'story') {
      const inheritedExecutionId = getBindingRemoteResourceId(inheritedSprintBinding)
      if (inheritedExecutionId) setRemoteExecutionId(inheritedExecutionId)
      return
    }
    const currentExecutionId = getBindingRemoteResourceId(currentBinding)
    if (currentExecutionId) setRemoteExecutionId(currentExecutionId)
  }, [currentBinding, depth, inheritedSprintBinding, open, remoteExecutionId])

  useEffect(() => {
    if (!open || remoteLeafResourceId || depth !== 'story') return
    const currentLeafResourceId = getBindingRemoteResourceId(currentBinding)
    if (currentLeafResourceId) setRemoteLeafResourceId(currentLeafResourceId)
  }, [currentBinding, depth, open, remoteLeafResourceId])

  const selectedRemoteResourceId = getRemoteResourceId(depth, {
    projectId: remoteProjectId,
    executionId: remoteExecutionId,
    leafId: remoteLeafResourceId,
  })

  function refreshBindingQueries() {
    void queryClient.invalidateQueries({ queryKey: bindingConfig.bindingsKey })
    if (targetType === 'project') {
      for (const key of ['sprintBindings', 'requirementBindings', 'sprints', 'requirementsPool', 'bugZentaoPush']) void queryClient.invalidateQueries({ queryKey: [key] })
    }
    if (targetType === 'sprint') void queryClient.invalidateQueries({ queryKey: ['sprints', projectId] })
    if (targetType === 'requirement') void queryClient.invalidateQueries({ queryKey: ['requirementsPool', projectId] })
  }

  const saveBindingMutation = useMutation({
    mutationFn: async () => {
      if (!mcpReady) throw new Error(mcpReason)
      if (!parentReady) throw new Error('请先完成上级项目和迭代的禅道绑定')
      if (!selectedRemoteResourceId) throw new Error('请选择要绑定的禅道对象')
      if (instanceSwitch && !confirmInstanceSwitch) throw new Error('请勾选确认清除旧关联')

      if (!can('manage')) throw new Error('仅项目所有者可修改绑定')
      if (currentBinding && getBindingId(currentBinding)) {
        return api.updateZentaoBinding(targetType, resourceId, getBindingId(currentBinding), { remoteResourceId: selectedRemoteResourceId, ...(targetType === 'project' ? { mcpServiceId: mcp?.serviceId, confirmInstanceSwitch } : {}) })
      }

      return bindingConfig.createBinding(selectedRemoteResourceId, targetType === 'project' ? mcp?.serviceId : undefined)
    },
    onSuccess: () => {
      message.success(currentBinding ? '禅道绑定已更新' : '禅道绑定已创建')
      refreshBindingQueries()
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
      refreshBindingQueries()
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

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
      mask={{ closable: false }}
      centered
      styles={{
        container: {
          maxWidth: 'calc(100vw - 24px)',
          border: '1px solid var(--tp-border-soft)',
          borderRadius: 16,
          background: 'linear-gradient(180deg, var(--app-glass-surface-98), var(--app-testing-card-gradient-end)), var(--app-surface)',
          boxShadow: 'inset 0 1px 0 var(--app-glass-highlight-72), 0 20px 48px var(--app-service-card-shadow)',
        },
        header: { padding: '18px 20px 0', background: 'transparent' },
        title: { color: 'var(--tp-text)', fontSize: 15, lineHeight: '22px', fontWeight: 600 },
        body: { padding: '18px 20px 20px', display: 'flex', flexDirection: 'column', gap: 14 },
      }}
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
      <div className="head flex flex-wrap items-center justify-between gap-4">
        <Title level={5} className="mb-0 text-[15px] leading-[22px]">当前绑定</Title>
        {currentBinding ? (
          <Space size={8} wrap className="current min-w-0 justify-start [&_.ant-typography]:text-[13px] [&_.ant-typography]:leading-5">
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

      {mcpQuery.error ? <Alert showIcon type="error" title={getErrorMessage(mcpQuery.error)} /> : null}
      {!projectId ? <Alert showIcon type="info" title="请先选择项目" /> : null}
      {bindingsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(bindingsQuery.error)} /> : null}
      {parentProjectBindingsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(parentProjectBindingsQuery.error)} /> : null}
      {parentSprintBindingsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(parentSprintBindingsQuery.error)} /> : null}
      {projectsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(projectsQuery.error)} /> : null}
      {executionsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(executionsQuery.error)} /> : null}
      {storiesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(storiesQuery.error)} /> : null}
      {((targetType === 'sprint' || targetType === 'requirement') && inheritedProjectBinding) ||
      (targetType === 'requirement' && inheritedSprintBinding) ? (
        <div className="inheritNote flex flex-wrap items-center gap-2 px-0.5 text-xs leading-[22px] text-[var(--tp-text-secondary,var(--app-control-text))] [&_.ant-tag]:me-0 [&_.ant-tag]:max-w-[220px] [&_.ant-tag]:overflow-hidden [&_.ant-tag]:text-ellipsis [&_.ant-tag]:whitespace-nowrap">
          <Text type="secondary">已使用上级绑定；修改上级目标请到对应项目或迭代的绑定配置</Text>
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

      {targetType === 'project' && (
        <div className="formRow flex flex-wrap items-center gap-2.5">
          <Text>项目 MCP 服务</Text>
          <Select className="w-[220px] min-w-0 flex-1 max-[680.01px]:w-full" aria-label="项目 MCP 服务" value={effectiveMcpId}
            loading={mcpQuery.isLoading} placeholder="选择项目使用的禅道 MCP"
            disabled={!can('manage')} showSearch optionFilterProp="label"
            options={mcps.map(service => ({ value: service.serviceId, label: `${service.name} · ${service.zentaoInstanceUrl || service.baseUrl}` }))}
            onChange={(value: string) => {
              setSelectedMcpId(value)
              setMcpChanged(true)
              setConfirmInstanceSwitch(false)
              setRemoteProjectId(undefined)
              setRemoteExecutionId(undefined)
              setRemoteLeafResourceId(undefined)
            }} />
        </div>
      )}
      {instanceSwitch && <Alert showIcon type="warning" title="更换禅道实例将清除旧关联" description={
        <Checkbox checked={confirmInstanceSwitch} onChange={event => setConfirmInstanceSwitch(event.target.checked)}>
          我确认切换禅道并清除本项目原有的禅道绑定、缺陷号及推送关联；平台数据和远端数据保留。
        </Checkbox>
      } />}
      {!mcpQuery.isLoading && mcpReason && <Alert showIcon type="info" title={mcpReason} action={<a href="/base-services?tab=mcp">前往配置</a>} />}
      {!parentReady && <Alert showIcon type="info" title="请先完成上级项目和迭代的禅道绑定" />}
      {mcp && <Text type="secondary">当前服务：{mcp.name} · {mcp.zentaoInstanceUrl || '实例地址未确认'} · 使用本人授权</Text>}
      {mcpReady && parentReady && (
        <div className="formRow flex flex-wrap items-center gap-2.5">
          <Select
            className="w-[220px] max-[680.01px]:w-full"
            aria-label="禅道项目"
            loading={projectsQuery.isLoading}
            value={remoteProjectId}
            placeholder={inheritedProjectBinding ? '已使用项目绑定' : '选择禅道项目'}
            options={projectOptions}
            disabled={targetType !== 'project'}
            onChange={handleProjectChange}
            showSearch
            optionFilterProp="label"
          />
          {depth !== 'project' ? (
            <Select
              className="w-[220px] max-[680.01px]:w-full"
              aria-label="禅道执行"
              loading={executionsQuery.isLoading}
              value={remoteExecutionId}
              placeholder={inheritedSprintBinding ? '已使用迭代绑定' : '选择禅道执行'}
              options={executionOptions}
              disabled={!remoteProjectId || targetType === 'requirement'}
              onChange={handleExecutionChange}
              showSearch
              optionFilterProp="label"
            />
          ) : null}
          {depth === 'story' ? (
            <Select
              className="w-[220px] max-[680.01px]:w-full"
              aria-label="禅道需求"
              loading={storiesQuery.isLoading}
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
            className="action-btn-save max-[680.01px]:w-full"
            loading={saveBindingMutation.isPending}
            disabled={!can('manage') || !mcpReady || !parentReady || !selectedRemoteResourceId || (instanceSwitch && !confirmInstanceSwitch) || projectsQuery.isError || executionsQuery.isError || storiesQuery.isError}
            onClick={() => saveBindingMutation.mutate()}
          >
            {currentBinding ? '重新绑定' : '绑定'}
          </ProjectActionButton>
        </div>
      )}
    </Modal>
  )
}
