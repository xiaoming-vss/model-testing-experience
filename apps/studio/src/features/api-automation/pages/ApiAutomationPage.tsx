import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { ListPagination } from '@/shared/components/ListPagination'
import { tableFooterClass } from '@/shared/utils/surfaceClasses'
import { EntityCard } from '@/shared/components/EntityCard'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { SearchOutlined, SettingOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Tooltip,
} from 'antd'
import type { InputRef } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { EnvironmentDrawer } from '@/features/projects/components/EnvironmentDrawer'
import { CollectionDrawer, type CollectionFormValues } from '@/features/api-automation/components/CollectionDrawer'
import { useProjectRequirementOptions } from '@/features/projects/hooks/useProjectRequirementOptions'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { useSprintRequirementScope } from '@/features/projects/hooks/useSprintRequirementScope'
import { api, listItems, type ApiCollection, type ApiEnvironment } from '@/services/api'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import {
  formatTime,
  getErrorMessage,
  normalizeEnvironmentId,
  normalizeRequirementId,
  normalizeSprintId,
  pickUpdatedAt,
} from '@/utils/format'
import { buildApiCollectionUpdatePayload } from '@/utils/updatePayload'
import { message } from '@/shared/utils/feedback'
import { entityCardDescClass, entityCardDescEmptyClass, entityCardGridClass } from '@/shared/utils/surfaceClasses'
import '@/shared/styles/surface-tokens.css'

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
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
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

  const { allRequirements, allRequirementsQuery, requirementNameMap, requirementSprintMap, sprintNameMap } =
    useProjectRequirementOptions({ activeProjectId })

  const {
    currentRequirementSelection,
    requirementFilterOptions,
    requirementsLoading,
    resolvedSelectedRequirementId,
    resolvedSelectedSprintId,
    selectRequirement,
    sprints,
    sprintsQuery,
  } = useSprintRequirementScope({
    activeProjectId,
    includeAllRequirementOption: true,
    includeAllSprintOption: true,
    defaultToAllWhenIncluded: true,
    sprintScope: scope ? undefined : { value: globalSprintId, onChange: selectGlobalSprint },
    requirementOptions: allRequirements,
    requirementOptionsLoading: allRequirementsQuery.isLoading,
  })
  const selectedSprintId = scope?.sprintId ?? resolvedSelectedSprintId
  const selectedRequirementId = scope?.requirementId ?? resolvedSelectedRequirementId

  useEffect(() => { setPage(1) }, [activeProjectId, selectedSprintId, selectedRequirementId, keyword])

  const collectionsQuery = useQuery({
    // 「全部需求」用项目级列表一次取回，不再按需求逐个请求；选中需求时仍走需求维度接口。
    queryKey: ['apiCollections', activeProjectId, selectedRequirementId ?? 'all'],
    // 未锁定需求时等需求池回来，才能按迭代在前端筛选；请求本身只依赖项目。
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
      const response = await api.getProjectApiCollections(activeProjectId!)
      return listItems(response).map((collection) => ({
        ...collection,
        requirementId: collection.requirementId ?? collection.requirement_id,
      }))
    },
  })
  const collections = useMemo(() => {
    const data = collectionsQuery.data ?? []
    if (selectedRequirementId || !selectedSprintId) return data
    return data.filter((collection) => requirementSprintMap.get(collection.requirementId ?? collection.requirement_id ?? '') === selectedSprintId)
  }, [collectionsQuery.data, requirementSprintMap, selectedRequirementId, selectedSprintId])

  const environmentsQuery = useQuery({
    queryKey: ['testEnvironments', activeProjectId, 'api'],
    queryFn: () => api.getApiEnvironments(activeProjectId!, 'api'),
    enabled: Boolean(activeProjectId),
  })
  const environments = listItems(environmentsQuery.data)
  const selectedEnvironment =
    environments.find((environment) => normalizeEnvironmentId(environment) === selectedEnvironmentId) ??
    environments.find((environment) => environment.isDefault) ??
    environments[0]
  const resolvedEnvironmentId = selectedEnvironment ? normalizeEnvironmentId(selectedEnvironment) : undefined



  const drawerSprintOptions = useMemo(
    () => sprints.map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) })),
    [sprints],
  )

  const drawerRequirementOptions = useMemo(
    () => allRequirements
      .filter((requirement) => !drawerSprintId || requirement.sprintId === drawerSprintId)
      .map((requirement) => ({ label: requirement.name, value: normalizeRequirementId(requirement) })),
    [allRequirements, drawerSprintId],
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
    onSuccess: (_result, values) => {
      const previousRequirementId = editingCollection?.requirementId ?? editingCollection?.requirement_id
      for (const requirementId of new Set([previousRequirementId, values.requirementId])) {
        if (requirementId) void queryClient.invalidateQueries({ queryKey: ['generationChain', requirementId, 'api', 'importOptions'] })
      }
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
      // 标签页常驻挂载后，隐藏面板里的搜索框不能抢占快捷键。
      if (keywordInputRef.current?.nativeElement?.closest('[hidden]')) return
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

    return { collectionDescription, collectionId, requirementName, sprintName }
  }

  function renderCollectionCard(collection: ApiCollection) {
    const { collectionDescription, collectionId, requirementName, sprintName } =
      getCollectionRowContext(collection)
    const title = collectionId ? (
      <Link to={`/api-automation/collections/${collectionId}`} title={collection.name}>
        {collection.name}
      </Link>
    ) : collection.name

    return (
      <EntityCard
        key={collectionId || collection.name}
        title={title}
        meta={[
          { label: '所属迭代', value: sprintName },
          { label: '所属需求', value: requirementName },
        ]}
        footerNote={<>最近更新 {formatTime(pickUpdatedAt(collection))}</>}
        actions={
          <>
            <Tooltip title={resolvedEnvironmentId ? '运行API测试集' : '请先选择环境'}>
              <ProjectActionButton
                action="execute"
                type="text"
                shape="circle"
                className="action-btn-read"
                operation="run"
                iconOnly
                aria-label="运行API测试集"
                disabled={!resolvedEnvironmentId}
                loading={runningCollectionId === collectionId && runCollectionMutation.isPending}
                onClick={(event) => handleRunCollection(event, collectionId)}
              />
            </Tooltip>
            <Tooltip title="编辑测试集">
              <ProjectActionButton
                action="write"
                type="text"
                shape="circle"
                className="action-btn-update"
                operation="edit"
                iconOnly
                aria-label="编辑API测试集"
                onClick={() => openEditDrawer(collection)}
              />
            </Tooltip>
            <Popconfirm title="确认删除该API测试集？" onConfirm={() => deleteCollectionMutation.mutate(collectionId)}>
              <Tooltip title="删除测试集">
                <ProjectActionButton
                  action="write"
                  danger
                  type="text"
                  shape="circle"
                  className="action-btn-delete"
                  operation="delete"
                  iconOnly
                  aria-label="删除API测试集"
                  loading={deleteCollectionMutation.isPending && deleteCollectionMutation.variables === collectionId}
                />
              </Tooltip>
            </Popconfirm>
          </>
        }
        onOpen={() => openCollectionDetail(collectionId)}
      >
        <p
          className={`entity-card-desc ${entityCardDescClass}${collection.description ? '' : ` ${entityCardDescEmptyClass}`}`}
          title={collectionDescription}
        >
          {collectionDescription}
        </p>
      </EntityCard>
    )
  }

  return (
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface api-test-page tp-surface [--font-mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace]">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-panel-flat workbench-board-panel tp-board tp-list-panel">
          {/* 设计稿里筛选行与环境信息条在同一张卡片里，中间一条分隔线。 */}
          <div className="panel-header api-panel-header api-test-header tp-list-toolbar flex flex-col items-stretch">
            <div className="api-test-header-main flex flex-wrap items-center justify-between gap-2 p-0">
              <div className="api-panel-head-main flex min-w-0 flex-wrap items-center gap-2 max-[900.01px]:w-full max-[900.01px]:flex-col max-[900.01px]:items-start max-[900.01px]:gap-2.5">
                <h1 className="tp-list-title">API测试</h1>
                {!isRequirementLocked ? (
                  <div className="api-filter-group">
                    <div className="api-filter-field">
                      <span className="api-filter-field-label font-medium text-[var(--srf-text-muted)]">需求</span>
                      <Select
                        className="api-filter-select business-filter-select"
                        value={currentRequirementSelection === null ? 'all' : selectedRequirementId ?? 'all'}
                        options={requirementFilterOptions}
                        loading={requirementsLoading}
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
                <div className="api-inline-environment flex flex-wrap items-center gap-3 pl-0 max-[1200px]:w-full max-[1200px]:pl-0 max-narrow:flex-col max-narrow:items-start max-narrow:gap-2.5">
                  <div className="api-environment-selector flex items-center gap-2 max-narrow:w-full max-narrow:flex-col max-narrow:items-start">
                    <span className="api-environment-label whitespace-nowrap text-[12px] leading-[18px] text-[var(--app-glass-text-caption)]">当前环境</span>
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
                <div className="api-test-search-field w-72 min-w-[240px] max-w-full">
                  <Input
                    ref={keywordInputRef}
                    className="api-filter-input api-test-search-input"
                    allowClear
                    prefix={<SearchOutlined />}
                    suffix={<span className="api-test-search-hint font-mono text-[10px] text-[var(--srf-text-muted)]">⌘K</span>}
                    placeholder="搜索测试集名称 / 描述"
                    value={keyword}
                    onChange={(event) => {
                      setKeyword(event.target.value)
                      setPage(1)
                    }}
                  />
                </div>
              </div>
              <Space size={8} className="api-test-header-actions flex-none items-center">
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


          </div>

          {sprintsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} /> : null}
          {!isRequirementLocked ? <>{allRequirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(allRequirementsQuery.error)} /> : null}</> : null}
          {collectionsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(collectionsQuery.error)} /> : null}
          {environmentsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(environmentsQuery.error)} /> : null}


          <div className="api-test-card-body tp-list-body">
            <div className="flex min-h-0 flex-col p-4 api-test-card-scroll tp-list-scroll">
              {sprintsQuery.isLoading ? (
                <div className="grid min-h-[220px] place-items-center">
                  <Empty description="迭代加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
              ) : !activeProjectId ? (
                <div className="grid min-h-[220px] place-items-center">
                  <Empty description="请先选择项目" />
                </div>
              ) : isRequirementLocked && !selectedRequirementId ? (
                <div className="grid min-h-[220px] place-items-center">
                  <Empty description="当前需求不可用" />
                </div>
              ) : collectionsQuery.isLoading ? (
                <div className="grid min-h-[220px] place-items-center">
                  <Empty description="API测试集加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
              ) : filteredCollections.length === 0 ? (
                <div className="grid min-h-[220px] place-items-center">
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
                <div className={`entity-card-grid ${entityCardGridClass}`}>
                  {pagedCollections.map(renderCollectionCard)}
                </div>
              )}
            </div>

            <div className={`table-footer api-test-footer ${tableFooterClass}`}>
              <ListPagination loading={collectionsQuery.isFetching || collectionsQuery.isError}
                current={page}
                pageSize={pageSize}
                total={filteredCollections.length}
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
        error={saveCollectionMutation.error ?? allRequirementsQuery.error}
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

      <EnvironmentDrawer
        open={environmentDrawerOpen}
        projectId={activeProjectId}
        kind="api"
        currentEnvironmentId={resolvedEnvironmentId}
        onClose={() => setEnvironmentDrawerOpen(false)}
        onSelectEnvironment={setSelectedEnvironmentId}
      />
    </div>
  )
}
