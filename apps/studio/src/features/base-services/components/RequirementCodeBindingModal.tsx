import { usePersonalConnections } from '@/features/base-services/hooks/usePersonalConnections'
import { PersonalConnectionFields } from './PersonalConnectionFields'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { LinkOutlined } from '@ant-design/icons'
import { Alert, Empty, Modal, Popconfirm, Select, Space, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient, useQueries } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import '@/features/base-services/styles/index.css'
import { GitlabBranchSelect } from '@/features/base-services/components/GitlabBranchSelect'
import {
  getBindingId,
  getBindingRemoteName,
  getBindingRemoteResourceId,
  isGitlabGroupBinding,
  isGitlabRepositoryBinding,
} from '@/features/base-services/utils/resourceBinding'
import { api, listItems, type GitlabRepository } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

const { Text, Title } = Typography

const GROUP_REPO_PAGE_SIZE = 100

function getRepoId(repository: GitlabRepository) {
  const value = repository.id
  return value === undefined || value === null ? '' : String(value)
}

function getRepoLabel(repository: GitlabRepository) {
  const id = getRepoId(repository)
  const label = repository.pathWithNamespace ?? repository.name ?? id
  return label === id ? label : `${label} (${id})`
}

export function RequirementCodeBindingModal({
  open,
  onClose,
  projectId,
  requirementId,
  requirementName = '',
}: {
  open: boolean
  onClose: () => void
  projectId: string
  requirementId: string
  requirementName?: string
}) {
  const queryClient = useQueryClient()
  const { can } = useProjectAccess(projectId)
  const [selectedConnections, setSelectedConnections] = useState<Record<string, string>>({})
  const personal = usePersonalConnections(projectId, 'gitlab', selectedConnections)
  const [repoPages, setRepoPages] = useState<Record<string, number>>({})
  const [selectedRepoId, setSelectedRepoId] = useState<string>()
  const [selectedBranch, setSelectedBranch] = useState<string>()
  const [selectedBaseline, setSelectedBaseline] = useState<string>()

  const groupBindingsQuery = useQuery({
    queryKey: ['projectBindings', projectId],
    queryFn: () => api.getGitlabProjectBindings(projectId),
    enabled: open && Boolean(projectId),
  })
  const groupBindings = useMemo(
    () => listItems(groupBindingsQuery.data).filter(isGitlabGroupBinding),
    [groupBindingsQuery.data],
  )
  const bindingsQuery = useQuery({
    queryKey: ['requirementCodeBindings', requirementId],
    queryFn: () => api.getGitlabRequirementBindings(requirementId),
    enabled: open && Boolean(requirementId),
  })
  const codeBindings = useMemo(
    () => listItems(bindingsQuery.data).filter(isGitlabRepositoryBinding),
    [bindingsQuery.data],
  )

  const repositoryQueries = useQueries({
    queries: groupBindings.flatMap((groupBinding) => {
      const groupId = getBindingRemoteResourceId(groupBinding)
      const connectionId = personal.resolve(groupBinding.instanceUrl ?? '')
      const pages = repoPages[getBindingId(groupBinding)] ?? 1
      return Array.from({ length: pages }, (_, index) => ({
        queryKey: ['gitlabGroupRepositories', projectId, connectionId, groupId, index + 1],
        queryFn: () => api.getGitlabGroupRepositories(projectId, connectionId, groupId, index + 1, GROUP_REPO_PAGE_SIZE),
        enabled: open && Boolean(projectId) && Boolean(connectionId) && Boolean(groupId),
      }))
    }),
  })

  const groupRepoAggregate = useMemo(() => {
    const seen = new Set<string>()
    const repos: Array<{ repository: GitlabRepository; groupId: string; connectionId: string }> = []
    const hasMoreGroups: string[] = []
    let cursor = 0

    for (const groupBinding of groupBindings) {
      const groupId = getBindingRemoteResourceId(groupBinding)
      const connectionId = personal.resolve(groupBinding.instanceUrl ?? '')
      const pages = repoPages[getBindingId(groupBinding)] ?? 1
      let loaded = 0
      let total = 0

      for (let page = 0; page < pages; page += 1) {
        const query = repositoryQueries[cursor]
        cursor += 1
        if (!query) break
        const items = query.data?.items ?? []
        total = Math.max(total, query.data?.total ?? items.length)
        loaded += items.length
        for (const repository of items) {
          const repoId = getRepoId(repository)
          if (!repoId || seen.has(`${groupBinding.instanceUrl}:${repoId}`)) continue
          seen.add(`${groupBinding.instanceUrl}:${repoId}`)
          repos.push({ repository, groupId, connectionId })
        }
      }

      if (loaded > 0 && loaded < total) {
        hasMoreGroups.push(getBindingId(groupBinding))
      }
    }

    return { repos, hasMoreGroups }
  }, [groupBindings, repositoryQueries, repoPages, personal])

  const repositoryOptions = useMemo(
    () =>
      groupRepoAggregate.repos.map(({ repository, connectionId }) => ({
        label: `${getRepoLabel(repository)} · ${personal.connections.find(c => c.connectionId === connectionId)?.baseUrl ?? ''}`,
        value: `${connectionId}:${getRepoId(repository)}`,
      })),
    [groupRepoAggregate.repos, personal.connections],
  )
  const selectedRepoInfo = useMemo(
    () => groupRepoAggregate.repos.find(({ repository, connectionId }) => `${connectionId}:${getRepoId(repository)}` === selectedRepoId),
    [groupRepoAggregate.repos, selectedRepoId],
  )
  const hasMoreRepositories = groupRepoAggregate.hasMoreGroups.length > 0

  function loadMoreRepositories() {
    setRepoPages((current) => {
      const next = { ...current }
      for (const groupId of groupRepoAggregate.hasMoreGroups) {
        next[groupId] = (next[groupId] ?? 1) + 1
      }
      return next
    })
  }

  const createBindingMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRepoInfo) throw new Error('请选择仓库')
      if (!selectedBranch) throw new Error('请选择分支')
      return api.createGitlabRequirementBinding(requirementId, {
        provider: 'gitlab',
        connectionId: selectedRepoInfo.connectionId,
        remoteResourceType: 'repository',
        remoteResourceId: getRepoId(selectedRepoInfo.repository),
        remoteParentId: selectedRepoInfo.groupId,
        remoteNameSnapshot: selectedRepoInfo.repository.pathWithNamespace ?? selectedRepoInfo.repository.name ?? getRepoId(selectedRepoInfo.repository),
        extraJson: {
          branch: selectedBranch,
          ...(selectedBaseline ? { baselineBranch: selectedBaseline } : {}),
        },
      })
    },
    onSuccess: () => {
      message.success('代码绑定已创建')
      setSelectedRepoId(undefined)
      setSelectedBranch(undefined)
      setSelectedBaseline(undefined)
      queryClient.invalidateQueries({ queryKey: ['requirementCodeBindings', requirementId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const updateBranchMutation = useMutation({
    mutationFn: ({ bindingId, branch }: { bindingId: string; branch: string }) => {
      if (!can('manage')) throw new Error('仅项目所有者可以修改代码绑定')
      return api.updateGitlabRequirementBinding(requirementId, bindingId, { branch, connectionId: personal.resolve(codeBindings.find(b => getBindingId(b) === bindingId)?.instanceUrl ?? '') })
    },
    onSuccess: () => {
      message.success('分支已更新')
      queryClient.invalidateQueries({ queryKey: ['requirementCodeBindings', requirementId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const updateBaselineMutation = useMutation({
    mutationFn: ({ bindingId, baselineBranch }: { bindingId: string; baselineBranch?: string }) => {
      if (!can('manage')) throw new Error('仅项目所有者可以修改代码绑定')
      return api.updateGitlabRequirementBinding(requirementId, bindingId, { baselineBranch: baselineBranch ?? '', connectionId: personal.resolve(codeBindings.find(b => getBindingId(b) === bindingId)?.instanceUrl ?? '') })
    },
    onSuccess: () => {
      message.success('基线分支已更新')
      queryClient.invalidateQueries({ queryKey: ['requirementCodeBindings', requirementId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const deleteBindingMutation = useMutation({
    mutationFn: (bindingId: string) => api.deleteGitlabRequirementBinding(requirementId, bindingId),
    onSuccess: () => {
      message.success('代码绑定已删除')
      queryClient.invalidateQueries({ queryKey: ['requirementCodeBindings', requirementId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  return (
    <Modal
      width={720}
      className="requirement-code-binding-modal"
      title={
        <Space size={8}>
          <LinkOutlined />
          <span>代码绑定{requirementName ? ` · ${requirementName}` : ''}</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <PersonalConnectionFields instances={[...groupBindings, ...codeBindings].map(b => b.instanceUrl ?? '')} connections={personal.connections} value={selectedConnections} onChange={value => { setSelectedConnections(value); setSelectedRepoId(undefined); setSelectedBranch(undefined); setSelectedBaseline(undefined) }} />
      {groupBindingsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(groupBindingsQuery.error)} /> : null}
      {bindingsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(bindingsQuery.error)} /> : null}
      {groupBindings.length === 0 ? (
        <Alert showIcon type="info" title="项目尚未绑定 GitLab 群组，请先到项目主页绑定群组" />
      ) : null}

      <div className="requirement-code-binding-head">
        <Title level={5}>已绑定仓库</Title>
        <Text type="secondary">{codeBindings.length} 个仓库</Text>
      </div>

      {bindingsQuery.isLoading ? (
        <Empty description="代码绑定加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : codeBindings.length === 0 ? (
        <Empty description="当前需求未绑定任何仓库" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div className="requirement-code-binding-list">
          {codeBindings.map((binding) => {
            const bindingId = getBindingId(binding)
            const repositoryId = getBindingRemoteResourceId(binding)
            const repositoryName = getBindingRemoteName(binding)
            const repositoryConnectionId = personal.resolve(binding.instanceUrl ?? '')

            return (
              <div key={bindingId || repositoryId} className="requirement-code-binding-row">
                <div className="requirement-code-binding-row-main">
                  <Tag className="requirement-code-binding-repo-tag" color="geekblue" title={repositoryName}>
                    {repositoryName}
                  </Tag>
                  <Text type="secondary">{binding.instanceUrl}</Text>
                  {binding.branch ? <Tag color="blue">{binding.branch}</Tag> : null}
                  {binding.baselineBranch ? <Tag color="orange">基线：{binding.baselineBranch}</Tag> : null}
                </div>
                <div className="requirement-code-binding-row-actions">
                  <GitlabBranchSelect
                    projectId={projectId}
                    connectionId={repositoryConnectionId}
                    repositoryId={repositoryId}
                    value={binding.branch}
                    placeholder="切换分支"
                    disabled={!can('manage')}
                    allowClear={false}
                    onChange={(branch) => {
                      if (branch) updateBranchMutation.mutate({ bindingId, branch })
                    }}
                  />
                  <GitlabBranchSelect
                    projectId={projectId}
                    connectionId={repositoryConnectionId}
                    repositoryId={repositoryId}
                    value={binding.baselineBranch || undefined}
                    placeholder="设置基线分支（可选）"
                    disabled={!can('manage')}
                    onChange={(baseline) => updateBaselineMutation.mutate({ bindingId, baselineBranch: baseline ?? '' })}
                  />
                  <Popconfirm title="确认删除该仓库绑定？" onConfirm={() => deleteBindingMutation.mutate(bindingId)}>
                    <ProjectActionButton operation="delete" action="manage" projectId={projectId} danger size="small" className="action-btn-delete">
                      删除
                    </ProjectActionButton>
                  </Popconfirm>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {can('manage') && groupBindings.length > 0 ? (
        <div className="requirement-code-binding-add">
          <Title level={5} className="requirement-code-binding-add-title">
            添加代码绑定
          </Title>
          <div className="requirement-code-binding-add-row">
            <Select
              className="requirement-code-binding-select"
              showSearch
              optionFilterProp="label"
              loading={repositoryQueries.some((query) => query.isLoading)}
              options={repositoryOptions}
              value={selectedRepoId}
              placeholder="选择仓库（已绑群组内）"
              onPopupScroll={(event) => {
                const el = event.currentTarget
                if (el.scrollTop + el.clientHeight >= el.scrollHeight - 48 && hasMoreRepositories && !repositoryQueries.some((query) => query.isFetching)) {
                  loadMoreRepositories()
                }
              }}
              onChange={(repoId) => {
                setSelectedRepoId(repoId as string)
                setSelectedBranch(undefined)
                setSelectedBaseline(undefined)
              }}
            />
            <GitlabBranchSelect
              projectId={projectId}
              connectionId={selectedRepoInfo?.connectionId ?? ''}
              repositoryId={selectedRepoInfo ? getRepoId(selectedRepoInfo.repository) : ''}
              value={selectedBranch}
              placeholder="选择分支（必选）"
              allowClear={false}
              disabled={!can('manage') || !selectedRepoInfo}
              onChange={setSelectedBranch}
            />
            <GitlabBranchSelect
              projectId={projectId}
              connectionId={selectedRepoInfo?.connectionId ?? ''}
              repositoryId={selectedRepoInfo ? getRepoId(selectedRepoInfo.repository) : ''}
              value={selectedBaseline}
              placeholder="基线分支（可选）"
              disabled={!can('manage') || !selectedRepoInfo}
              onChange={(value) => setSelectedBaseline(value ?? '')}
            />
            <ProjectActionButton action="manage" projectId={projectId}
              type="primary"
              className="action-btn-save"
              operation="create"
              loading={createBindingMutation.isPending}
              disabled={!selectedRepoInfo || !selectedBranch}
              onClick={() => createBindingMutation.mutate()}
            >
              添加
            </ProjectActionButton>
          </div>
          {selectedBaseline && selectedRepoInfo ? (
            <Alert
              showIcon
              type="info"
              className="requirement-code-binding-baseline-note"
              title="设置基线分支后，分析将直接以此分支作为基线，不再自动查找历史迭代。"
            />
          ) : null}
          {hasMoreRepositories ? (
            <div className="requirement-code-binding-more">
              <ProjectActionButton action="read" projectId={projectId} size="small" loading={repositoryQueries.some((query) => query.isFetching)} onClick={loadMoreRepositories}>
                加载更多仓库
              </ProjectActionButton>
            </div>
          ) : null}
        </div>
      ) : null}

    </Modal>
  )
}
