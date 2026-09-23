import { footerRange } from '@/shared/utils/pagination'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ApiOutlined, ReloadOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  Pagination,
  Popconfirm,
  Select,
  Space,
  Table,
  Tooltip,
  Typography,
} from 'antd'
import type { InputRef, TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
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
import '@/shared/styles/surface-tokens.css'
import '@/features/api-automation/styles/list-v2.css'

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
  const [keyword, setKeyword] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerSprintId, setDrawerSprintId] = useState<string | undefined>(undefined)
  const [editingCollection, setEditingCollection] = useState<ApiCollection | null>(null)
  const [environmentDrawerOpen, setEnvironmentDrawerOpen] = useState(false)
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | undefined>(undefined)
  const [runningCollectionId, setRunningCollectionId] = useState('')
  const [drawerForm] = Form.useForm<CollectionFormValues>()
  const keywordInputRef = useRef<InputRef>(null)
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
    // queryFn 在没有选中需求时要靠 allRequirements 才能知道去哪些需求下取测试集，
    // 所以这个依赖必须进 key：否则需求池还没回来就先算出空列表，而且被缓存住不再重算。
    queryKey: [
      'apiCollections',
      activeProjectId,
      selectedSprintId,
      selectedRequirementId,
      sprints.map(normalizeSprintId).join(','),
      allRequirements.map(normalizeRequirementId).join(','),
    ],
    // 同理，未锁定需求时等需求池回来再查，避免拿到「需求还没回来」的空结果。
    enabled:
      Boolean(activeProjectId) &&
      !sprintsQuery.isLoading &&
      Boolean(selectedRequirementId || isRequirementLocked || !allRequirementsQuery.isLoading),
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

  // 测试集数量不多（一个项目一个迭代下的全部），搜索与分页都在前端做，和大盘一致。
  const filteredCollections = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    if (!text) return collections
    return collections.filter((collection) =>
      `${collection.name} ${collection.description ?? ''}`.toLowerCase().includes(text),
    )
  }, [collections, keyword])

  const pagedCollections = useMemo(
    () => filteredCollections.slice((page - 1) * pageSize, page * pageSize),
    [filteredCollections, page, pageSize],
  )

  // 搜索框右侧标了 ⌘K，那就得真的能按：Mac 用 ⌘，其他平台用 Ctrl。
  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey)) return
      event.preventDefault()
      keywordInputRef.current?.focus()
    }

    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

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
        <Space size={8} className="functional-suite-list-name api-test-name-cell">
          <span className="api-test-name-icon">
            <ApiOutlined />
          </span>
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
      render: (_, collection) => (
        <Text className="api-test-time-cell" type="secondary">
          {formatTime(pickCreatedAt(collection))}
        </Text>
      ),
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: 180,
      render: (_, collection) => (
        <Text className="api-test-time-cell" type="secondary">
          {formatTime(pickUpdatedAt(collection))}
        </Text>
      ),
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
    <div className="workbench-page api-automation-page functional-test-page api-test-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board">
          {/* 设计稿里筛选行与环境信息条在同一张卡片里，中间一条分隔线。 */}
          <div className="panel-header api-panel-header api-test-header">
            <div className="api-test-header-main">
              <div className="requirement-panel-head api-panel-head-main">
                <Text strong className="api-test-title">
                  API测试集
                </Text>
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
                </div>
                <div className="api-test-search-field">
                  <Input
                    ref={keywordInputRef}
                    className="api-filter-input api-test-search-input"
                    allowClear
                    prefix={<SearchOutlined />}
                    suffix={<span className="api-test-search-hint">⌘K</span>}
                    placeholder="搜索测试集名称 / 描述"
                    value={keyword}
                    onChange={(event) => {
                      setKeyword(event.target.value)
                      setPage(1)
                    }}
                  />
                </div>
              </div>
              <Space size={8} className="api-test-header-actions">
                <Button
                  icon={<SettingOutlined />}
                  disabled={!activeProjectId}
                  onClick={() => setEnvironmentDrawerOpen(true)}
                >
                  环境管理
                </Button>
                <ProjectActionButton
                  action="write"
                  type="primary"
                  className="action-btn-create"
                  operation="create"
                  disabled={!activeProjectId || sprints.length === 0}
                  onClick={openCreateDrawer}
                >
                  新建API测试集
                </ProjectActionButton>
              </Space>
            </div>

            <div className="api-test-env-strip">
              <div className="api-test-env-facts">
                <span className="api-test-env-fact">
                  <span className="api-test-env-label">Base URL:</span>
                  <code className="api-test-env-code">{selectedEnvironment?.baseUrl || '-'}</code>
                </span>
                <span className="api-test-env-sep">|</span>
                <span className="api-test-env-fact">
                  <span className="api-test-env-label">环境变量数:</span>
                  <strong>{environmentVarsQuery.data?.length ?? 0}</strong>
                </span>
                <span className="api-test-env-sep">|</span>
                <span className="api-test-env-fact">
                  <span className="api-test-env-label">更新时间:</span>
                  {formatTime(pickUpdatedAt(selectedEnvironment))}
                </span>
              </div>
              <button
                type="button"
                className="api-test-env-refresh"
                onClick={() => {
                  environmentsQuery.refetch()
                  environmentVarsQuery.refetch()
                }}
              >
                <ReloadOutlined />
                刷新环境配置
              </button>
            </div>
          </div>

          {sprintsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} /> : null}
          {!isRequirementLocked ? <>{requirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(requirementsQuery.error)} /> : null}</> : null}
          {!isRequirementLocked ? <>{allRequirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(allRequirementsQuery.error)} /> : null}</> : null}
          {collectionsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(collectionsQuery.error)} /> : null}
          {environmentsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(environmentsQuery.error)} /> : null}

          {/* 设计稿上另外两个胶囊（自动化冒烟 / 核心链路）要有「测试集分类」字段，模型里没有，先只留全部。 */}
          <div className="tp-quickbar api-test-quickbar">
            <div className="tp-quick-filters">
              <span className="tp-quick-label">快速过滤:</span>
              <button
                type="button"
                className={`tp-chip${keyword ? '' : ' active'}`}
                aria-pressed={!keyword}
                onClick={() => {
                  setKeyword('')
                  setPage(1)
                }}
              >
                全部
                <span className="tp-chip-count">{filteredCollections.length}</span>
              </button>
            </div>
            <div className="tp-selection">
              共 <strong>{filteredCollections.length}</strong> 条测试集
            </div>
          </div>

          <div className="api-test-table-card">
            <div className="table-body-scroll sprint-card-scroll api-test-table-scroll">
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
              ) : filteredCollections.length === 0 ? (
                <div className="sprint-card-loading">
                  <Empty
                    description={
                      keyword.trim()
                        ? '没有符合搜索条件的API测试集'
                        : selectedRequirementId
                          ? '当前需求下暂无API测试集'
                          : '当前范围下暂无API测试集'
                    }
                  >
                    {keyword.trim() ? (
                      <Button onClick={() => setKeyword('')}>清空搜索</Button>
                    ) : (
                      <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" disabled={!activeProjectId || sprints.length === 0} onClick={openCreateDrawer}>
                        新建API测试集
                      </ProjectActionButton>
                    )}
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

            <div className="table-footer api-test-footer">
              <Text type="secondary">{footerRange(filteredCollections.length, page, pageSize)}</Text>
              <Pagination
                current={page}
                pageSize={pageSize}
                total={filteredCollections.length}
                showSizeChanger
                pageSizeOptions={['10', '20', '30', '50']}
                onChange={(nextPage, nextPageSize) => {
                  setPage(nextPage)
                  setPageSize(nextPageSize)
                }}
              />
            </div>
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
