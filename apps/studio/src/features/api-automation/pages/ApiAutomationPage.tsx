import { footerRange } from '@/shared/utils/pagination'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { SettingOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Form, Pagination, Popconfirm, Select, Space, Table, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiEnvironmentDrawer } from '@/features/api-automation/components/ApiEnvironmentDrawer'
import { CollectionDrawer, type CollectionFormValues } from '@/features/api-automation/components/CollectionDrawer'
import { useProjectRequirements } from '@/features/projects/hooks/useProjectRequirements'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { useSprintRequirementScope } from '@/features/projects/hooks/useSprintRequirementScope'
import { api, listItems, type ApiCollection, type ApiEnvironment, type Requirement } from '@/services/api'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import {
  formatTime,
  getErrorMessage,
  normalizeEnvironmentId,
  normalizeRequirementId,
  normalizeSprintId,
  pickCreatedAt,
  pickUpdatedAt,
} from '@/utils/format'
import { buildApiCollectionUpdatePayload } from '@/utils/updatePayload'
import { message } from '@/shared/utils/feedback'

const { Text } = Typography

type ApiAutomationPageScope = {
  projectId?: string
  sprintId?: string
  sprintName?: string
  requirementId?: string
  requirementName?: string
}

function isApiRunPollingStatus(status?: string) {
  return status === 'pending' || status === 'running'
}

export function ApiAutomationPage({ scope }: { scope?: ApiAutomationPageScope }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const workbenchActiveProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const activeProjectId = scope?.projectId ?? workbenchActiveProjectId
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerSprintId, setDrawerSprintId] = useState<string | undefined>(undefined)
  const [editingCollection, setEditingCollection] = useState<ApiCollection | null>(null)
  const [environmentDrawerOpen, setEnvironmentDrawerOpen] = useState(false)
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | undefined>(undefined)
  const [runningCollectionId, setRunningCollectionId] = useState('')
  const [drawerForm] = Form.useForm<CollectionFormValues>()
  const isRequirementLocked = Boolean(scope?.requirementId)
  const { activeSprintId: globalSprintId, selectSprint: selectGlobalSprint } = useActiveSprint()

  const {
    currentRequirementSelection,
    currentSprintSelection,
    requirementFilterOptions,
    requirementsQuery,
    resolvedSelectedRequirementId,
    resolvedSelectedSprintId,
    selectRequirement,
    selectSprint,
    sprintFilterOptions,
    sprints,
    sprintsQuery,
  } = useSprintRequirementScope({
    activeProjectId,
    includeAllRequirementOption: true,
    includeAllSprintOption: true,
    defaultToAllWhenIncluded: true,
    sprintScope: scope ? undefined : { value: globalSprintId, onChange: selectGlobalSprint },
  })
  const selectedSprintId = scope?.sprintId ?? resolvedSelectedSprintId
  const selectedRequirementId = scope?.requirementId ?? resolvedSelectedRequirementId

  const { allRequirements, allRequirementsQuery, requirementNameMap, requirementSprintMap, sprintNameMap } =
    useProjectRequirements({
      activeProjectId,
      enabled: !sprintsQuery.isLoading && !isRequirementLocked,
      sprints,
    })

  const collectionsQuery = useQuery({
    queryKey: [
      'apiCollections',
      activeProjectId,
      selectedSprintId,
      selectedRequirementId,
      sprints.map(normalizeSprintId).join(','),
    ],
    queryFn: async () => {
      if (selectedRequirementId) {
        const collections = await api.getApiCollections(selectedRequirementId)
        return collections.map((collection) => ({
          ...collection,
          requirementId: collection.requirementId ?? collection.requirement_id ?? selectedRequirementId,
        }))
      }

      const targetRequirements: Requirement[] = selectedSprintId
        ? (() => {
            const pool = allRequirements.length > 0 ? allRequirements : []
            const targets = pool.filter((item) => (item.sprintId ?? item.sprint_id) === selectedSprintId)
            return targets
          })()
        : sprints.length === 0
          ? []
          : (await Promise.all(sprints.map((sprint) => api.getRequirements(normalizeSprintId(sprint))))).flat()

      if (targetRequirements.length === 0 && selectedSprintId) {
        return []
      }

      const requirementPool =
        targetRequirements.length > 0
          ? targetRequirements
          : sprints.length === 0
            ? []
            : (await Promise.all(sprints.map((sprint) => api.getRequirements(normalizeSprintId(sprint))))).flat()

      if (requirementPool.length === 0) return []

      const collectionGroups = await Promise.all(
        requirementPool.map(async (requirement) => {
          const requirementId = normalizeRequirementId(requirement)
          const collections = await api.getApiCollections(requirementId)
          return collections.map((collection) => ({
            ...collection,
            requirementId: collection.requirementId ?? collection.requirement_id ?? requirementId,
          }))
        }),
      )

      return collectionGroups.flat()
    },
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })
  const collections = useMemo(() => collectionsQuery.data ?? [], [collectionsQuery.data])

  const environmentsQuery = useQuery({
    queryKey: ['apiEnvironments', activeProjectId],
    queryFn: () => api.getApiEnvironments(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const environments = listItems(environmentsQuery.data)
  const selectedEnvironment =
    environments.find((environment) => normalizeEnvironmentId(environment) === selectedEnvironmentId) ??
    environments.find((environment) => environment.isDefault) ??
    environments[0]
  const resolvedEnvironmentId = selectedEnvironment ? normalizeEnvironmentId(selectedEnvironment) : undefined

  const environmentVarsQuery = useQuery({
    queryKey: ['apiEnvironmentVars', resolvedEnvironmentId],
    queryFn: () => api.getApiEnvironmentVars(resolvedEnvironmentId!),
    enabled: Boolean(resolvedEnvironmentId),
  })

  const drawerSprintOptions = useMemo(
    () => sprints.map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) })),
    [sprints],
  )

  const drawerRequirementsQuery = useQuery({
    queryKey: ['requirements', 'drawer', drawerSprintId],
    queryFn: () => api.getRequirements(drawerSprintId!),
    enabled: Boolean(drawerSprintId),
  })
  const drawerRequirementOptions = useMemo(
    () => listItems(drawerRequirementsQuery.data).map((requirement) => ({ label: requirement.name, value: normalizeRequirementId(requirement) })),
    [drawerRequirementsQuery.data],
  )

  const saveCollectionMutation = useMutation({
    mutationFn: (values: CollectionFormValues) => {
      if (!values.requirementId) throw new Error('请选择所属需求')
      const editingCollectionId = editingCollection?.collectionId ?? editingCollection?.collection_id

      if (editingCollectionId && editingCollection) {
        return api.updateApiCollection(editingCollectionId, buildApiCollectionUpdatePayload(editingCollection, values))
      }
      return api.createApiCollection(values.requirementId, {
        name: values.name,
        description: values.summary,
      })
    },
    onSuccess: () => {
      message.success(editingCollection ? 'API测试集已更新' : 'API测试集已创建')
      setDrawerOpen(false)
      setEditingCollection(null)
      setDrawerSprintId(undefined)
      drawerForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['apiCollections'] })
    },
  })

  const deleteCollectionMutation = useMutation({
    mutationFn: (collectionId: string) => api.deleteApiCollection(collectionId),
    onSuccess: () => {
      message.success('API测试集已删除')
      queryClient.invalidateQueries({ queryKey: ['apiCollections'] })
    },
  })

  const runCollectionMutation = useMutation({
    mutationFn: ({ collectionId, environmentId }: { collectionId: string; environmentId: string }) =>
      api.runApiCollection(collectionId, { environmentId }),
    onSuccess: (result) => {
      if (isApiRunPollingStatus(result.status)) {
        message.success('已开始运行，可在API测试集详情查看运行记录')
        return
      }
      message.success('API测试集运行已触发')
    },
    onSettled: () => {
      setRunningCollectionId('')
    },
  })

  const pagedCollections = useMemo(
    () => collections.slice((page - 1) * pageSize, page * pageSize),
    [collections, page, pageSize],
  )

  function openCreateDrawer() {
    setEditingCollection(null)
    setDrawerSprintId(scope?.sprintId ?? resolvedSelectedSprintId)
    drawerForm.setFieldsValue({
      sprintId: scope?.sprintId ?? resolvedSelectedSprintId,
      requirementId: selectedRequirementId,
      name: '',
      summary: '',
    })
    setDrawerOpen(true)
  }

  function openEditDrawer(collection: ApiCollection) {
    const requirementId = collection.requirementId ?? collection.requirement_id
    const sprintId = scope?.sprintId ?? (requirementId ? requirementSprintMap.get(requirementId) : undefined)

    setEditingCollection(collection)
    setDrawerSprintId(sprintId)
    drawerForm.setFieldsValue({
      sprintId,
      requirementId,
      name: collection.name,
      summary: collection.description,
    })
    setDrawerOpen(true)
  }

  function handleRunCollection(event: React.MouseEvent<HTMLElement>, collectionId: string) {
    event.stopPropagation()
    if (!resolvedEnvironmentId) {
      message.warning('请先选择运行环境')
      return
    }

    setRunningCollectionId(collectionId)
    runCollectionMutation.mutate({
      collectionId,
      environmentId: resolvedEnvironmentId,
    })
  }

  function openCollectionDetail(collectionId: string) {
    if (!collectionId) return
    navigate(`/api-automation/collections/${collectionId}`)
  }

  function getCollectionRowContext(collection: ApiCollection) {
    const collectionId = collection.collectionId ?? collection.collection_id ?? ''
    const requirementId = collection.requirementId ?? collection.requirement_id
    const requirementName =
      scope?.requirementName || (requirementId ? requirementNameMap.get(requirementId) ?? requirementId : '-')
    const sprintIdForCollection = scope?.sprintId ?? (requirementId ? requirementSprintMap.get(requirementId) : undefined)
    const sprintName =
      scope?.sprintName || (sprintIdForCollection ? sprintNameMap.get(sprintIdForCollection) ?? sprintIdForCollection : '-')
    const collectionDescription = collection.description || '暂无API测试集描述'
    const collectionScopeText = `${sprintName} / ${requirementName}`

    return { collectionDescription, collectionId, collectionScopeText }
  }

  const columns: TableProps<ApiCollection>['columns'] = [
    {
      title: '测试集名称',
      dataIndex: 'name',
      key: 'name',
      width: '30%',
      render: (name: ApiCollection['name']) => (
        <Space size={0} className="functional-suite-list-name">
          <Tooltip title={name}>
            <Text ellipsis>{name}</Text>
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '所属迭代/需求',
      key: 'scope',
      ellipsis: true,
      render: (_, collection) => {
        const { collectionScopeText } = getCollectionRowContext(collection)
        return (
          <Tooltip title={collectionScopeText}>
            <Text className="functional-suite-list-scope" ellipsis>
              {collectionScopeText}
            </Text>
          </Tooltip>
        )
      },
    },
    {
      title: '创建时间',
      key: 'createdAt',
      width: 180,
      render: (_, collection) => <Text type="secondary">{formatTime(pickCreatedAt(collection))}</Text>,
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: 180,
      render: (_, collection) => <Text type="secondary">{formatTime(pickUpdatedAt(collection))}</Text>,
    },
    {
      title: '描述',
      key: 'description',
      ellipsis: true,
      render: (_, collection) => {
        const { collectionDescription } = getCollectionRowContext(collection)
        return (
          <Tooltip title={collectionDescription}>
            <Text className="functional-suite-list-description" type="secondary" ellipsis>
              {collectionDescription}
            </Text>
          </Tooltip>
        )
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 138,
      align: 'right',
      render: (_, collection) => {
        const { collectionId } = getCollectionRowContext(collection)
        return (
          <Space
            size={8}
            className="functional-suite-list-actions"
            onClick={(event) => event.stopPropagation()}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <Tooltip title={resolvedEnvironmentId ? '运行API测试集' : '请先选择环境'}>
              <ProjectActionButton action="execute"
                type="text"
                shape="circle"
                className="action-btn-read"
                operation="run" iconOnly
                aria-label="运行API测试集"
                disabled={!resolvedEnvironmentId}
                loading={runningCollectionId === collectionId && runCollectionMutation.isPending}
                onClick={(event) => handleRunCollection(event, collectionId)}
              />
            </Tooltip>
            <Tooltip title="编辑测试集">
              <ProjectActionButton action="write"
                type="text"
                shape="circle"
                className="action-btn-update"
                operation="edit" iconOnly
                aria-label="编辑API测试集"
                onClick={() => openEditDrawer(collection)}
              />
            </Tooltip>
            <Popconfirm title="确认删除该API测试集？" onConfirm={() => deleteCollectionMutation.mutate(collectionId)}>
              <Tooltip title="删除测试集">
                <ProjectActionButton action="write"
                  danger
                  type="text"
                  shape="circle"
                  className="action-btn-delete"
                  operation="delete" iconOnly
                  aria-label="删除API测试集"
                  loading={deleteCollectionMutation.isPending && deleteCollectionMutation.variables === collectionId}
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        )
      },
    },
  ]

  return (
    <div className="workbench-page api-automation-page functional-test-page api-test-page">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel">
          <div className="panel-header api-panel-header">
            <div className="requirement-panel-head api-panel-head-main">
              <Text strong>API测试集</Text>
              {!isRequirementLocked ? (
                <div className="api-filter-group">
                  <div className="api-filter-field">
                    <span className="api-filter-field-label">迭代</span>
                    <Select
                      className="api-filter-select business-filter-select"
                      value={currentSprintSelection === null ? 'all' : selectedSprintId ?? 'all'}
                      options={sprintFilterOptions}
                      loading={sprintsQuery.isLoading}
                      placeholder="筛选迭代"
                      onChange={(value: string) => {
                        selectSprint(value === 'all' ? null : value)
                        if (value === 'all') {
                          selectRequirement(null)
                        }
                        setPage(1)
                      }}
                    />
                  </div>
                  <div className="api-filter-field">
                    <span className="api-filter-field-label">需求</span>
                    <Select
                      className="api-filter-select business-filter-select"
                      value={currentRequirementSelection === null ? 'all' : selectedRequirementId ?? 'all'}
                      options={requirementFilterOptions}
                      loading={requirementsQuery.isLoading}
                      placeholder="筛选需求"
                      disabled={!selectedSprintId && sprints.length === 0}
                      onChange={(value: string) => {
                        selectRequirement(value === 'all' ? null : value)
                        setPage(1)
                      }}
                    />
                  </div>
                </div>
              ) : null}
              <div className="api-inline-environment">
                <div className="api-environment-selector">
                  <span className="api-environment-label">当前环境</span>
                  <Select
                    className="api-filter-select business-filter-select"
                    value={resolvedEnvironmentId}
                    placeholder="请选择环境"
                    loading={environmentsQuery.isLoading}
                    options={environments.map((environment: ApiEnvironment) => ({
                      label: `${environment.name}${environment.isDefault ? '（启用中）' : ''}`,
                      value: normalizeEnvironmentId(environment),
                    }))}
                    onChange={(value: string) => setSelectedEnvironmentId(value)}
                    disabled={!activeProjectId || environments.length === 0}
                  />
                </div>
                <div className="api-environment-summary">
                  <span className="api-environment-summary-item">Base URL：{selectedEnvironment?.baseUrl || '-'}</span>
                  <span className="api-environment-summary-item">变量数：{environmentVarsQuery.data?.length ?? 0}</span>
                  <span className="api-environment-summary-item">
                    更新时间：{formatTime(pickUpdatedAt(selectedEnvironment))}
                  </span>
                </div>
              </div>
            </div>
            <Space size={8}>
              <Button icon={<SettingOutlined />} disabled={!activeProjectId} onClick={() => setEnvironmentDrawerOpen(true)}>
                环境管理
              </Button>
              <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" disabled={!activeProjectId || sprints.length === 0} onClick={openCreateDrawer}>
                新建API测试集
              </ProjectActionButton>
            </Space>
          </div>

          {sprintsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} /> : null}
          {!isRequirementLocked ? <>{requirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(requirementsQuery.error)} /> : null}</> : null}
          {!isRequirementLocked ? <>{allRequirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(allRequirementsQuery.error)} /> : null}</> : null}
          {collectionsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(collectionsQuery.error)} /> : null}
          {environmentsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(environmentsQuery.error)} /> : null}

          <div className="table-body-scroll sprint-card-scroll">
            {sprintsQuery.isLoading ? (
              <div className="sprint-card-loading">
                <Empty description="迭代加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </div>
            ) : !activeProjectId ? (
              <div className="sprint-card-loading">
                <Empty description="请先选择项目" />
              </div>
            ) : isRequirementLocked && !selectedRequirementId ? (
              <div className="sprint-card-loading">
                <Empty description="当前需求不可用" />
              </div>
            ) : collectionsQuery.isLoading ? (
              <div className="sprint-card-loading">
                <Empty description="API测试集加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </div>
            ) : collections.length === 0 ? (
              <div className="sprint-card-loading">
                <Empty description={selectedRequirementId ? '当前需求下暂无API测试集' : '当前范围下暂无API测试集'}>
                  <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" disabled={!activeProjectId || sprints.length === 0} onClick={openCreateDrawer}>
                    新建API测试集
                  </ProjectActionButton>
                </Empty>
              </div>
            ) : (
              <Table<ApiCollection>
                className="functional-suite-list-table api-suite-list-table"
                columns={columns}
                dataSource={pagedCollections}
                rowKey={(collection) => getCollectionRowContext(collection).collectionId || collection.name}
                pagination={false}
                onRow={(collection) => ({
                  onClick: () => openCollectionDetail(getCollectionRowContext(collection).collectionId),
                })}
              />
            )}
          </div>
          <div className="table-footer">
            <Text type="secondary">{footerRange(collections.length, page, pageSize)}</Text>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={collections.length}
              showSizeChanger
              pageSizeOptions={['10', '20', '30', '50']}
              onChange={(nextPage, nextPageSize) => {
                setPage(nextPage)
                setPageSize(nextPageSize)
              }}
            />
          </div>
        </section>
      </div>

      <CollectionDrawer
        title={editingCollection ? '编辑API测试集' : '新建API测试集'}
        open={drawerOpen}
        form={drawerForm}
        loading={saveCollectionMutation.isPending}
        error={saveCollectionMutation.error ?? drawerRequirementsQuery.error}
        sprintOptions={drawerSprintOptions}
        requirementOptions={drawerRequirementOptions}
        showScopeFields={!isRequirementLocked}
        onSprintChange={(nextSprintId) => {
          setDrawerSprintId(nextSprintId)
          drawerForm.setFieldValue('requirementId', undefined)
        }}
        onClose={() => {
          setDrawerOpen(false)
          setEditingCollection(null)
          setDrawerSprintId(undefined)
          drawerForm.resetFields()
        }}
        onFinish={(values) => saveCollectionMutation.mutate(values)}
      />

      <ApiEnvironmentDrawer
        open={environmentDrawerOpen}
        projectId={activeProjectId}
        currentEnvironmentId={resolvedEnvironmentId}
        onClose={() => setEnvironmentDrawerOpen(false)}
        onSelectEnvironment={setSelectedEnvironmentId}
      />
    </div>
  )
}
