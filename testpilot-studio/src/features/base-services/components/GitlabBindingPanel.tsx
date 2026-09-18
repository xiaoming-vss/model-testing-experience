import { normalizeInstanceUrl } from '../utils/personalConnections'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { LinkOutlined } from '@ant-design/icons'
import { Alert, Button, Dropdown, Empty, Input, Modal, Popconfirm, Select, Space, Tag, Tooltip, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient, useQueries } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import '@/features/base-services/styles/index.css'
import { api, ApiError, listItems, type GitlabGroup, type ResourceBinding } from '@/services/api'
import {
  getBindingId,
  getBindingRemoteName,
  getBindingRemoteResourceId,
  isGitlabGroupBinding,
} from '../utils/resourceBinding'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

const { Text, Title } = Typography

function getBindingStatusText(status?: string) {
  if (!status) return '-'
  if (status === 'active') return '已绑定'
  return status
}

function getBindingStatusClassName(status?: string) {
  if (status === 'active') return 'is-active'
  if (status === 'disabled') return 'is-disabled'
  return 'is-neutral'
}

function getGroupResourceId(group: GitlabGroup) {
  const value = group.id ?? group.fullPath
  return value === undefined || value === null ? '' : String(value)
}

function getGroupLabel(group: GitlabGroup) {
  const id = getGroupResourceId(group)
  const label = group.fullPath ?? group.name ?? id
  return label === id ? label : `${label} (${id})`
}

export function GitlabBindingSummary({
  projectId,
  variant = 'toolbar',
}: {
  projectId?: string
  variant?: 'footer' | 'toolbar' | 'settings'
}) {
  const bindingsQuery = useQuery({
    queryKey: ['projectBindings', projectId],
    queryFn: () => api.getGitlabProjectBindings(projectId!),
    enabled: Boolean(projectId),
  })
  const groupBindings = useMemo(
    () => listItems(bindingsQuery.data).filter(isGitlabGroupBinding),
    [bindingsQuery.data],
  )

  if (variant === 'settings') {
    if (bindingsQuery.isPending) return <Text type="secondary">加载绑定信息…</Text>
    if (bindingsQuery.isError) return <Text type="danger">绑定信息加载失败</Text>
    if (groupBindings.length === 0) return <Text type="secondary">未绑定群组</Text>
    return <div className="project-settings-binding-details">
      {groupBindings.map((binding) => <div key={getBindingId(binding)} className="project-settings-binding-line">
        <Text className="project-settings-binding-name">{getBindingRemoteName(binding) || getBindingRemoteResourceId(binding)}</Text>
        <Tag color={binding.status === 'active' ? 'success' : 'default'}>{getBindingStatusText(binding.status)}</Tag>
      </div>)}
    </div>
  }
  if (groupBindings.length === 0) return null

  const names = groupBindings.slice(0, 3).map((binding) => getBindingRemoteName(binding))
  const remaining = groupBindings.length - names.length
  const summaryText = names.join('、') + (remaining > 0 ? ` 等 ${groupBindings.length} 个群组` : '')

  return (
    <div className={`gitlab-binding-summary gitlab-binding-summary-${variant}`} title={summaryText}>
      <div className="gitlab-binding-summary-main">
        <Tag color="geekblue">GitLab</Tag>
        <span className="gitlab-binding-summary-name">{summaryText}</span>
      </div>
      <span className={`gitlab-binding-summary-status ${getBindingStatusClassName(groupBindings[0].status)}`}>
        {getBindingStatusText(groupBindings[0].status)}
      </span>
    </div>
  )
}

export function GitlabBindingModal({
  open,
  onClose,
  projectId,
  projectName = '',
  requirementNameResolver,
}: {
  open: boolean
  onClose: () => void
  projectId: string
  projectName?: string
  requirementNameResolver?: (requirementId: string) => string | undefined
}) {
  const queryClient = useQueryClient()
  const { can } = useProjectAccess(projectId)
  const [connectionId, setConnectionId] = useState<string>()
  const [searchValue, setSearchValue] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [groupsPage, setGroupsPage] = useState(1)
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<string>>(new Set())
  const [affectedBindings, setAffectedBindings] = useState<ResourceBinding[]>([])

  const connectionsQuery = useQuery({
    queryKey: ['gitlabConnections', projectId],
    queryFn: () => api.getGitlabConnections(projectId),
    enabled: open && Boolean(projectId),
  })
  const bindingsQuery = useQuery({
    queryKey: ['projectBindings', projectId],
    queryFn: () => api.getGitlabProjectBindings(projectId),
    enabled: open && Boolean(projectId),
  })
  const groupBindings = useMemo(() => listItems(bindingsQuery.data).filter(isGitlabGroupBinding), [bindingsQuery.data])
  const boundGroupIds = useMemo(() => new Set(groupBindings.filter(b => normalizeInstanceUrl(b.instanceUrl ?? '') === normalizeInstanceUrl(listItems(connectionsQuery.data).find(c => c.connectionId === connectionId)?.baseUrl ?? '')).map(getBindingRemoteResourceId)), [groupBindings, connectionsQuery.data, connectionId])
  const currentUserConnections = useMemo(
    () => listItems(connectionsQuery.data).map((connection) => ({
      connectionId: connection.connectionId,
      name: connection.name,
      baseUrl: connection.baseUrl,
      status: connection.status,
      lastAuthError: connection.lastAuthError,
    })),
    [connectionsQuery.data],
  )


  useEffect(() => {
    if (!open || connectionId) return
    const active = currentUserConnections.filter((connection) => connection.status === 'active')
    if (active.length === 1) setConnectionId(active[0].connectionId)
  }, [currentUserConnections, connectionId, open])

  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => setDebouncedSearch(searchValue.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [open, searchValue])

  useEffect(() => {
    setGroupsPage(1)
    setSelectedGroupIds(new Set())
  }, [connectionId, debouncedSearch, open])

  const groupPageQueries = useQueries({
    queries: Array.from({ length: groupsPage }, (_, index) => ({
      queryKey: ['gitlabGroups', projectId, connectionId, debouncedSearch, index + 1],
      queryFn: () => api.getGitlabGroups(projectId, connectionId!, debouncedSearch, index + 1),
      enabled: open && Boolean(projectId) && Boolean(connectionId),
    })),
  })
  const groupStates = useMemo(
    () =>
      groupPageQueries.map((query) => ({
        items: query.data?.items ?? [],
        total: query.data?.total ?? 0,
        isLoading: query.isLoading,
        error: query.error,
      })),
    [groupPageQueries],
  )
  const loadedGroups = useMemo(() => groupStates.flatMap((state) => state.items), [groupStates])
  const loadedTotal = groupStates.length > 0 ? Math.max(...groupStates.map((state) => state.total)) : 0
  const hasMoreGroups = loadedGroups.length < loadedTotal
  const groupQueryError = groupPageQueries[0]?.error

  const saveBindingsMutation = useMutation({
    mutationFn: async () => {
      if (!connectionId) throw new Error('请选择 GitLab 连接')

      const failures: string[] = []
      const successfulGroupIds = new Set<string>()
      for (const groupId of selectedGroupIds) {
        const group = loadedGroups.find((item) => getGroupResourceId(item) === groupId)
        try {
          await api.createGitlabGroupBinding(projectId, {
            provider: 'gitlab',
            connectionId,
            remoteResourceType: 'group',
            remoteResourceId: groupId,
            remoteNameSnapshot: group?.fullPath ?? group?.name ?? groupId,
          })
          successfulGroupIds.add(groupId)
        } catch (error) {
          failures.push(`${getGroupLabel(group ?? { id: groupId })}：${getErrorMessage(error)}`)
        }
      }
      return { failures, successfulGroupIds }
    },
    onSuccess: async ({ failures, successfulGroupIds }) => {
      setSelectedGroupIds((current) => new Set([...current].filter((id) => !successfulGroupIds.has(id))))
      await queryClient.invalidateQueries({ queryKey: ['projectBindings', projectId] })
      if (failures.length > 0) {
        message.error(failures.join('\n'), 6)
        return
      }
      message.success('GitLab 群组绑定已保存')
      setSelectedGroupIds(new Set())
      setSearchValue('')
      setDebouncedSearch('')
    },
    onError: (error) => message.error(getErrorMessage(error), 6),
  })

  const revalidateMutation = useMutation({
    mutationFn: ({ bindingId, nextConnectionId }: { bindingId: string; nextConnectionId: string }) =>
      api.revalidateGitlabGroupBinding(projectId, bindingId, nextConnectionId),
    onSuccess: () => {
      message.success('已使用本人授权验证绑定')
      queryClient.invalidateQueries({ queryKey: ['projectBindings', projectId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const deleteBindingMutation = useMutation({
    mutationFn: (bindingId: string) => api.deleteGitlabGroupBinding(projectId, bindingId),
    onSuccess: () => {
      message.success('群组绑定已解除')
      setAffectedBindings([])
      queryClient.invalidateQueries({ queryKey: ['projectBindings', projectId] })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 3506) {
        const data = error.data as { bindings?: ResourceBinding[] }
        setAffectedBindings(data?.bindings ?? [])
        message.error(getErrorMessage(error))
        return
      }
      message.error(getErrorMessage(error))
    },
  })

  function toggleGroup(groupId: string) {
    if (boundGroupIds.has(groupId)) return
    setSelectedGroupIds((current) => {
      const next = new Set(current)
      if (next.has(groupId)) next.delete(groupId)
      else next.add(groupId)
      return next
    })
  }

  const connectionOptions = currentUserConnections.map((connection) => ({
    label: connection.status === 'active' ? connection.name : `${connection.name}（${connection.status}）`,
    value: connection.connectionId,
    disabled: connection.status !== 'active',
  }))

  return (
    <Modal
      width={760}
      className="gitlab-binding-modal"
      title={
        <Space size={8}>
          <LinkOutlined />
          <span>GitLab 群组绑定{projectName ? ` · ${projectName}` : ''}</span>
        </Space>
      }
      open={open}
      onCancel={() => {
        setAffectedBindings([])
        onClose()
      }}
      footer={null}
      destroyOnHidden
    >
      {bindingsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(bindingsQuery.error)} /> : null}
      {connectionsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(connectionsQuery.error)} /> : null}
      {groupQueryError ? <Alert showIcon type="error" title={getErrorMessage(groupQueryError)} /> : null}

      <div className="gitlab-binding-head">
        <Title level={5}>已绑定群组</Title>
        {groupBindings.length === 0 ? <Text type="secondary">当前项目未绑定任何群组</Text> : null}
      </div>
      {groupBindings.length > 0 ? (
        <div className="gitlab-binding-current-list">
          {groupBindings.map((binding) => {
            const bindingId = getBindingId(binding)
            const revalidateItems = currentUserConnections
              .filter((connection) => connection.status === 'active' && normalizeInstanceUrl(connection.baseUrl) === normalizeInstanceUrl(binding.instanceUrl ?? ''))
              .map((connection) => ({
                key: connection.connectionId,
                label: connection.status === 'active' ? connection.name : `${connection.name}（${connection.status}）`,
              }))

            return (
              <div key={bindingId || getBindingRemoteResourceId(binding)} className="gitlab-binding-current-item">
                <div className="gitlab-binding-current-main">
                  <Tag className="gitlab-binding-group-tag" color="geekblue">
                    {getBindingRemoteName(binding)}
                  </Tag>
                  <Text type="secondary">{binding.instanceUrl} · ID：{getBindingRemoteResourceId(binding) || '-'}</Text>
                  <span className={`gitlab-binding-summary-status ${getBindingStatusClassName(binding.status)}`}>
                    {getBindingStatusText(binding.status)}
                  </span>
                  {binding.lastSyncError ? (
                    <Tooltip title={`同步失败：${binding.lastSyncError}`}>
                      <Tag color="warning">同步异常</Tag>
                    </Tooltip>
                  ) : null}

                </div>
                <Space size={6}>
                  {revalidateItems.length === 1 ? (
                    <ProjectActionButton
                      action="manage"
                      projectId={projectId}
                      size="small"
                      className="action-btn-read"
                      loading={revalidateMutation.isPending && revalidateMutation.variables?.bindingId === bindingId}
                      disabled={revalidateMutation.isPending}
                      onClick={() => revalidateMutation.mutate({ bindingId, nextConnectionId: revalidateItems[0].key })}
                    >
                      重新验证
                    </ProjectActionButton>
                  ) : revalidateItems.length > 1 ? (
                    <Dropdown
                      disabled={!can('manage') || revalidateMutation.isPending}
                      trigger={['click']}
                      menu={{
                        items: revalidateItems,
                        onClick: (info: { key: string }) => revalidateMutation.mutate({ bindingId, nextConnectionId: String(info.key) }),
                      }}
                    >
                      <ProjectActionButton action="manage" projectId={projectId} size="small" className="action-btn-read">
                        重新验证
                      </ProjectActionButton>
                    </Dropdown>
                  ) : null}
                  <Popconfirm
                    title="确认解除该群组绑定？"
                    description="若仍有需求代码绑定引用该群组，解绑会被阻止。"
                    onConfirm={() => deleteBindingMutation.mutate(bindingId)}
                  >
                    <ProjectActionButton action="manage" projectId={projectId} danger size="small" className="action-btn-delete" loading={deleteBindingMutation.isPending}>
                      解绑
                    </ProjectActionButton>
                  </Popconfirm>
                </Space>
              </div>
            )
          })}
        </div>
      ) : null}

      {affectedBindings.length > 0 ? (
        <Alert
          showIcon
          type="error"
          className="gitlab-binding-affected-alert"
          title="仍有需求代码绑定引用该群组，无法解绑"
          description={
            <ul className="gitlab-binding-affected-list">
              {affectedBindings.map((binding) => {
                const requirementName = requirementNameResolver?.(binding.localResourceId ?? binding.local_resource_id ?? '')
                return (
                  <li key={getBindingId(binding)}>
                    {getBindingRemoteName(binding)}（{binding.branch || '-'}）· 需求：{requirementName ?? binding.localResourceId ?? '-'}
                  </li>
                )
              })}
            </ul>
          }
        />
      ) : null}

      {can('manage') ? (
        <>
          {currentUserConnections.length === 0 && !connectionsQuery.isLoading ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 GitLab 连接，请先到基础服务页创建连接" />
          ) : (
            <div className="gitlab-binding-form-row">
              <Select
                className="gitlab-binding-select"
                loading={connectionsQuery.isLoading}
                value={connectionId}
                placeholder="选择 GitLab 连接（仅自己的连接）"
                options={connectionOptions}
                onChange={setConnectionId}
              />
              <Input.Search
                className="gitlab-binding-search"
                placeholder="搜索群组（含子群组）"
                allowClear
                value={searchValue}
                onChange={(event) => setSearchValue(event.target.value)}
                disabled={!connectionId}
              />
            </div>
          )}

          <div className="gitlab-binding-group-list">
            {groupPageQueries.every((query) => query.isLoading) ? <Empty description="群组加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} /> : null}
            {!groupPageQueries.some((query) => query.isLoading) && loadedGroups.length === 0 && !connectionId ? (
              <Empty description="请先选择连接" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : null}
            {!groupPageQueries.some((query) => query.isLoading) && loadedGroups.length === 0 && connectionId ? (
              <Empty description="未搜索到群组" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : null}
            {loadedGroups.length > 0 ? (
              <>
                <div className="gitlab-binding-group-options">
                  {loadedGroups.map((group) => {
                    const groupId = getGroupResourceId(group)
                    const bound = boundGroupIds.has(groupId)
                    const selected = selectedGroupIds.has(groupId)

                    return (
                      <button
                        key={groupId || getGroupLabel(group)}
                        type="button"
                        className={`gitlab-binding-group-option${selected ? ' selected' : ''}${bound ? ' bound' : ''}`}
                        disabled={bound}
                        aria-pressed={selected}
                        onClick={() => toggleGroup(groupId)}
                      >
                        <span className="gitlab-binding-group-option-name">{getGroupLabel(group)}</span>
                        <span className="gitlab-binding-group-option-meta">
                          {group.description ? <span className="gitlab-binding-group-description">{group.description}</span> : null}
                          {bound ? <Tag color="default">已绑定</Tag> : null}
                          {selected ? <Tag color="blue">已选择</Tag> : null}
                        </span>
                      </button>
                    )
                  })}
                </div>
                {hasMoreGroups ? (
                  <div className="gitlab-binding-group-more">
                    <Button size="small" loading={groupPageQueries.some((query) => query.isFetching)} onClick={() => setGroupsPage((page) => page + 1)}>
                      加载更多群组
                    </Button>
                    <Text type="secondary">
                      已加载 {loadedGroups.length} / {loadedTotal}
                    </Text>
                  </div>
                ) : null}
              </>
            ) : null}
          </div>

          <div className="gitlab-binding-actions">
            <Text type="secondary">已选择 {selectedGroupIds.size} 个群组</Text>
            <Space size={8}>
              <Button onClick={onClose}>取消</Button>
              <ProjectActionButton action="manage" projectId={projectId}
                type="primary"
                className="action-btn-save"
                loading={saveBindingsMutation.isPending}
                disabled={!can('manage') || !connectionId || selectedGroupIds.size === 0}
                onClick={() => saveBindingsMutation.mutate()}
              >
                绑定
              </ProjectActionButton>
            </Space>
          </div>
        </>
      ) : (
        <div className="gitlab-binding-actions">
          <Button onClick={onClose}>关闭</Button>
        </div>
      )}
    </Modal>
  )
}
