import { LinkOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Empty, Modal, Popconfirm, Select, Space, Tag, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { GitlabBranchSelect } from '@/features/base-services/components/GitlabBranchSelect'
import { usePersonalConnections } from '@/features/base-services/hooks/usePersonalConnections'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import '@/features/base-services/styles/index.css'

const { Text, Title } = Typography

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
  const canWrite = can('write')
  const personal = usePersonalConnections(projectId, 'gitlab', {})
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<string>()
  const [selectedBranch, setSelectedBranch] = useState<string>()
  const [selectedBaseline, setSelectedBaseline] = useState<string>()

  const repositoriesQuery = useQuery({
    queryKey: ['softwareRepositories', projectId],
    queryFn: () => interfaceLibraryApi.getSoftwareRepositories(projectId),
    enabled: open && Boolean(projectId),
  })
  const bindingsQuery = useQuery({
    queryKey: ['requirementSoftwareRepositories', requirementId],
    queryFn: () => interfaceLibraryApi.getRequirementSoftwareRepositories(requirementId),
    enabled: open && Boolean(requirementId),
  })
  const repositories = useMemo(
    () => listItems(repositoriesQuery.data),
    [repositoriesQuery.data],
  )
  const bindings = useMemo(() => listItems(bindingsQuery.data), [bindingsQuery.data])
  const associatedIds = useMemo(
    () => new Set(bindings.map(binding => binding.softwareRepositoryId)),
    [bindings],
  )
  const repositoryOptions = useMemo(
    () =>
      repositories
        .filter(repository => !associatedIds.has(repository.softwareRepositoryId))
        .map(repository => ({
          label: `${repository.name} · ${repository.repository?.path ?? '未绑定代码仓库'}`,
          value: repository.softwareRepositoryId,
        })),
    [associatedIds, repositories],
  )
  const selectedRepository = repositories.find(
    repository => repository.softwareRepositoryId === selectedRepositoryId,
  )
  const selectedConnectionId = selectedRepository
    ? personal.resolve(selectedRepository.repository?.instanceUrl ?? '')
    : ''

  const createBindingMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRepositoryId) throw new Error('请选择软件仓库')
      if (!selectedBranch) throw new Error('请选择工作分支')
      if (!selectedBaseline) throw new Error('请选择基线分支')
      if (selectedBaseline === selectedBranch)
        throw new Error('基线分支不能与工作分支相同')
      return interfaceLibraryApi.createRequirementSoftwareRepository(requirementId, {
        softwareRepositoryId: selectedRepositoryId,
        branch: selectedBranch,
        baselineBranch: selectedBaseline,
      })
    },
    onSuccess: () => {
      message.success('软件仓库关联已创建')
      setSelectedRepositoryId(undefined)
      setSelectedBranch(undefined)
      setSelectedBaseline(undefined)
      queryClient.invalidateQueries({
        queryKey: ['requirementSoftwareRepositories', requirementId],
      })
      queryClient.invalidateQueries({ queryKey: ['requirementsPool', projectId] })
    },
    onError: error => message.error(getErrorMessage(error)),
  })

  const updateBranchMutation = useMutation({
    mutationFn: ({
      softwareRepositoryId,
      branch,
    }: {
      softwareRepositoryId: string
      branch: string
    }) =>
      interfaceLibraryApi.updateRequirementSoftwareRepository(
        requirementId,
        softwareRepositoryId,
        { branch },
      ),
    onSuccess: () => {
      message.success('工作分支已更新')
      queryClient.invalidateQueries({
        queryKey: ['requirementSoftwareRepositories', requirementId],
      })
      queryClient.invalidateQueries({ queryKey: ['requirementsPool', projectId] })
    },
    onError: error => message.error(getErrorMessage(error)),
  })

  const updateBaselineMutation = useMutation({
    mutationFn: ({
      softwareRepositoryId,
      baselineBranch,
    }: {
      softwareRepositoryId: string
      baselineBranch: string
    }) =>
      interfaceLibraryApi.updateRequirementSoftwareRepository(
        requirementId,
        softwareRepositoryId,
        { baselineBranch },
      ),
    onSuccess: () => {
      message.success('基线分支已更新')
      queryClient.invalidateQueries({
        queryKey: ['requirementSoftwareRepositories', requirementId],
      })
      queryClient.invalidateQueries({ queryKey: ['requirementsPool', projectId] })
    },
    onError: error => message.error(getErrorMessage(error)),
  })

  const deleteBindingMutation = useMutation({
    mutationFn: (softwareRepositoryId: string) =>
      interfaceLibraryApi.deleteRequirementSoftwareRepository(
        requirementId,
        softwareRepositoryId,
      ),
    onSuccess: () => {
      message.success('软件仓库关联已删除')
      queryClient.invalidateQueries({
        queryKey: ['requirementSoftwareRepositories', requirementId],
      })
      queryClient.invalidateQueries({ queryKey: ['requirementsPool', projectId] })
    },
    onError: error => message.error(getErrorMessage(error)),
  })

  return (
    <Modal
      width={760}
      mask={{ closable: false }}
      centered
      className="requirement-code-binding-modal"
      title={
        <Space size={8}>
          <LinkOutlined />
          <span>软件仓库{requirementName ? ` · ${requirementName}` : ''}</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      {repositoriesQuery.error ? (
        <Alert showIcon type="error" title={getErrorMessage(repositoriesQuery.error)} />
      ) : null}
      {bindingsQuery.error ? (
        <Alert showIcon type="error" title={getErrorMessage(bindingsQuery.error)} />
      ) : null}
      {repositories.length === 0 ? (
        <Alert
          showIcon
          type="info"
          title="当前项目还没有软件仓库，请先在「软件仓库」页创建软件仓库"
        />
      ) : null}

      {canWrite ? (
        <div className="requirement-code-binding-create">
          <div className="requirement-code-binding-head">
            <Title level={5}>关联软件仓库</Title>
            <Text type="secondary">每个关联分别维护工作分支和基线分支</Text>
          </div>
          <div className="requirement-code-binding-create-row">
            <Select
              className="requirement-code-binding-select"
              aria-label="选择软件仓库"
              placeholder="选择软件仓库"
              value={selectedRepositoryId}
              options={repositoryOptions}
              loading={repositoriesQuery.isLoading}
              showSearch
              optionFilterProp="label"
              onChange={value => {
                setSelectedRepositoryId(value)
                setSelectedBranch(undefined)
                setSelectedBaseline(undefined)
              }}
            />
            <GitlabBranchSelect
              projectId={projectId}
              connectionId={selectedConnectionId}
              repositoryId={selectedRepository?.repository?.projectId ?? ''}
              value={selectedBranch}
              placeholder="工作分支"
              ariaLabel="工作分支"
              disabled={!selectedRepository}
              onChange={setSelectedBranch}
            />
            <GitlabBranchSelect
              projectId={projectId}
              connectionId={selectedConnectionId}
              repositoryId={selectedRepository?.repository?.projectId ?? ''}
              value={selectedBaseline}
              placeholder="基线分支"
              ariaLabel="基线分支"
              disabled={!selectedRepository}
              onChange={setSelectedBaseline}
            />
            <ProjectActionButton
              operation="save"
              action="write"
              projectId={projectId}
              type="primary"
              disabled={!selectedRepositoryId || !selectedBranch || !selectedBaseline}
              loading={createBindingMutation.isPending}
              onClick={() => createBindingMutation.mutate()}
            >
              添加
            </ProjectActionButton>
          </div>
          {selectedRepository && !selectedConnectionId ? (
            <div className="if-repository-hint">
              当前账号没有该 GitLab 实例的个人连接，暂时无法选择分支。
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="requirement-code-binding-head">
        <Title level={5}>已关联软件仓库</Title>
        <Text type="secondary">{bindings.length} 个软件仓库</Text>
      </div>

      {bindingsQuery.isLoading ? (
        <Empty description="关联加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : bindings.length === 0 ? (
        <Empty description="当前需求未关联软件仓库" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div className="requirement-code-binding-list">
          {bindings.map(binding => {
            const connectionId = personal.resolve(
              binding.repository?.instanceUrl ?? '',
            )
            return (
              <div
                key={binding.softwareRepositoryId}
                className="requirement-code-binding-row"
              >
                <div className="requirement-code-binding-row-main">
                  <Tag
                    className="requirement-code-binding-repo-tag"
                    color="geekblue"
                    title={binding.repository?.path ?? binding.softwareRepositoryName}
                  >
                    {binding.softwareRepositoryName}
                  </Tag>
                  <Text type="secondary">{binding.repository?.path}</Text>
                  <Tag color="blue">{binding.branch}</Tag>
                  <Tag color="orange">基线：{binding.baselineBranch}</Tag>
                </div>
                <div className="requirement-code-binding-row-actions">
                  <GitlabBranchSelect
                    projectId={projectId}
                    connectionId={connectionId}
                    repositoryId={binding.repository?.projectId ?? ''}
                    value={binding.branch}
                    placeholder="切换工作分支"
                    ariaLabel={`${binding.softwareRepositoryName} 工作分支`}
                    disabled={!canWrite || !connectionId}
                    allowClear={false}
                    onChange={branch => {
                      if (branch)
                        updateBranchMutation.mutate({
                          softwareRepositoryId: binding.softwareRepositoryId,
                          branch,
                        })
                    }}
                  />
                  <GitlabBranchSelect
                    projectId={projectId}
                    connectionId={connectionId}
                    repositoryId={binding.repository?.projectId ?? ''}
                    value={binding.baselineBranch || undefined}
                    placeholder="切换基线分支"
                    ariaLabel={`${binding.softwareRepositoryName} 基线分支`}
                    disabled={!canWrite || !connectionId}
                    allowClear={false}
                    onChange={baseline => {
                      if (baseline)
                        updateBaselineMutation.mutate({
                          softwareRepositoryId: binding.softwareRepositoryId,
                          baselineBranch: baseline,
                        })
                    }}
                  />
                  <Popconfirm
                    title="确认删除该软件仓库关联？"
                    onConfirm={() =>
                      deleteBindingMutation.mutate(binding.softwareRepositoryId)
                    }
                  >
                    <ProjectActionButton
                      operation="delete"
                      action="write"
                      projectId={projectId}
                      danger
                      size="small"
                      className="action-btn-delete"
                      disabled={!canWrite}
                    >
                      删除
                    </ProjectActionButton>
                  </Popconfirm>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}
