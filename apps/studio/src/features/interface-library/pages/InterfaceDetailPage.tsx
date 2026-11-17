import {
  ArrowLeftOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  AutoComplete,
  Button,
  Empty,
  Input,
  Modal,
  Radio,
  Select,
  Spin,
  Tag,
  Tooltip,
} from 'antd'
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { useProjectRequirementOptions } from '@/features/projects/hooks/useProjectRequirementOptions'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { ApiError } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import { SoftwareRepositoryTree } from '../components/SoftwareRepositoryTree'
import { InterfaceBodyPanel } from '../components/InterfaceBodyPanel'
import { InterfaceHeadersPanel } from '../components/InterfaceHeadersPanel'
import { InterfaceParamsPanel } from '../components/InterfaceParamsPanel'
import { InterfaceResponsePanel } from '../components/InterfaceResponsePanel'
import { InterfaceSettingsPanel } from '../components/InterfaceSettingsPanel'
import { OpenApiImportModal } from '../components/OpenApiImportModal'
import { useSoftwareRepositoryList } from '../hooks/useSoftwareRepositoryManager'
import type {
  ApiInterface,
  ApiInterfaceListItem,
  CreateApiInterfacePayload,
  InterfaceRow,
  SoftwareRepository,
} from '../types'
import {
  blankInterface,
  INTERFACE_METHODS,
  jsonText,
  methodTone,
  parseJsonText,
  pathParameterNames,
  splitTags,
  syncPathParams,
} from '../utils/interfaceForm'
import {
  firstTag,
  replaceFirstTag,
  type InterfaceGroup,
} from '../utils/interfaceGroups'
import '@/shared/styles/surface-tokens.css'
import styles from '../styles/interface-library.module.css'
import methodStyles from '../styles/interface-method.module.css'
import openapiStyles from '../styles/interface-openapi.module.css'
import detailStyles from '../styles/interface-detail.module.css'
import editorStyles from '../styles/interface-editor.module.css'

const interfaceScopes = `${styles.scope} ${methodStyles.scope} ${openapiStyles.scope} ${detailStyles.scope} ${editorStyles.scope}`

type TabKey = 'params' | 'headers' | 'body' | 'response' | 'settings'

type JsonTexts = {
  bodySchema: string
  bodyExample: string
  responseSchema: string
  responseExample: string
}

const EMPTY_JSON_TEXTS: JsonTexts = {
  bodySchema: '',
  bodyExample: '',
  responseSchema: '',
  responseExample: '',
}

type GroupTarget = {
  repository: SoftwareRepository
  group: InterfaceGroup
}

type MoveTarget = {
  repository: SoftwareRepository
  item: ApiInterfaceListItem
  groups: string[]
}

export function InterfaceDetailPage() {
  const { interfaceId } = useParams<{ interfaceId: string }>()
  const isCreate = !interfaceId
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const projectId = useWorkbenchStore(state => state.activeProjectId) ?? ''
  const { can } = useProjectAccess(projectId)
  const canWrite = can('write')
  const { allRequirements } = useProjectRequirementOptions({ activeProjectId: projectId })
  const { repositories, repositoriesQuery } = useSoftwareRepositoryList(projectId)

  const [draft, setDraft] = useState<ApiInterface | null>(null)
  const [tagsText, setTagsText] = useState('')
  const [jsonTexts, setJsonTexts] = useState<JsonTexts>(EMPTY_JSON_TEXTS)
  const [activeTab, setActiveTab] = useState<TabKey>('params')
  const [importOpen, setImportOpen] = useState(false)
  const [groupRenameTarget, setGroupRenameTarget] = useState<GroupTarget | null>(null)
  const [groupRenameValue, setGroupRenameValue] = useState('')
  const [moveTarget, setMoveTarget] = useState<MoveTarget | null>(null)
  const [moveMode, setMoveMode] = useState<'group' | 'clear'>('group')
  const [moveGroupName, setMoveGroupName] = useState('')
  const [createGroupRepository, setCreateGroupRepository] =
    useState<SoftwareRepository | null>(null)
  const [createGroupName, setCreateGroupName] = useState('')

  const interfaceQuery = useQuery({
    queryKey: ['apiInterface', projectId, interfaceId],
    queryFn: () => interfaceLibraryApi.getApiInterface(interfaceId!),
    enabled: Boolean(interfaceId),
  })
  // Reset all editable state when the route changes so a stale draft can never be saved to
  // the interface or project now shown in the URL.
  const routeKey = `${projectId}:${interfaceId ?? 'new'}`
  useEffect(() => {
    setDraft(null)
    setTagsText('')
    setJsonTexts(EMPTY_JSON_TEXTS)
    setActiveTab('params')
  }, [routeKey])
  useEffect(() => {
    if (!interfaceQuery.data) return
    const data = interfaceQuery.data
    setDraft(data)
    setTagsText(data.tags.join(', '))
    setJsonTexts(jsonTextsOf(data))
  }, [interfaceQuery.data])

  useEffect(() => {
    if (!isCreate || draft || repositoriesQuery.isLoading) return
    const requestedRepositoryId = searchParams.get('softwareRepositoryId') ?? ''
    const repository =
      repositories.find(
        item => item.softwareRepositoryId === requestedRepositoryId,
      ) ?? repositories[0]
    if (!repository) return
    const next = blankInterface(repository.softwareRepositoryId)
    next.softwareRepositoryName = repository.name
    setDraft(next)
  }, [repositories, repositoriesQuery.isLoading, draft, isCreate, searchParams])

  const selectedRepository = repositories.find(
    repository => repository.softwareRepositoryId === draft?.softwareRepositoryId,
  )
  const interfaceInActiveProject =
    isCreate ||
    repositories.some(
      repository => repository.softwareRepositoryId === draft?.softwareRepositoryId,
    )

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!draft) throw new Error('接口尚未加载')
      if (!isCreate && draft.interfaceId !== interfaceId) {
        throw new Error('接口正在切换，请稍候再保存')
      }
      if (!interfaceInActiveProject) throw new Error('接口不属于当前项目')
      const payload = buildPayload(draft, tagsText, jsonTexts)
      if (isCreate) {
        if (!draft.softwareRepositoryId) throw new Error('请选择所属软件仓库')
        return interfaceLibraryApi.createApiInterface(draft.softwareRepositoryId, payload)
      }
      return interfaceLibraryApi.updateApiInterface(draft.interfaceId, payload)
    },
    onSuccess: data => {
      setDraft(data)
      setTagsText(data.tags.join(', '))
      setJsonTexts(jsonTextsOf(data))
      message.success(isCreate ? '接口已创建' : '接口已保存')
      queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
      queryClient.invalidateQueries({ queryKey: ['apiInterface', projectId, data.interfaceId] })
      queryClient.invalidateQueries({ queryKey: ['softwareRepositories', projectId] })
      if (isCreate) {
        navigate(`/asset-library/interfaces/${data.interfaceId}`, { replace: true })
      }
    },
    onError: error => message.error(errorMessage(error)),
  })
  const deleteMutation = useMutation({
    mutationFn: () => interfaceLibraryApi.deleteApiInterface(draft!.interfaceId),
    onSuccess: () => {
      message.success('接口已删除')
      queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
      queryClient.invalidateQueries({ queryKey: ['softwareRepositories', projectId] })
      navigate('/asset-library?tab=interfaces')
    },
    onError: error => message.error(errorMessage(error)),
  })
  const renameGroupMutation = useMutation({
    mutationFn: ({
      target,
      newGroupName,
    }: {
      target: GroupTarget
      newGroupName: string
    }) =>
      interfaceLibraryApi.renameApiInterfaceGroup(
        target.repository.softwareRepositoryId,
        {
          currentGroupName: target.group.tag,
          newGroupName,
        },
      ),
    onSuccess: (data, variables) => {
      syncDraftAfterGroupRename(
        variables.target.repository.softwareRepositoryId,
        variables.target.group.tag,
        data.newGroupName,
      )
      message.success(
        data.updatedCount
          ? `已将分组「${data.groupName}」重命名为「${data.newGroupName}」，更新 ${data.updatedCount} 个接口`
          : `已将分组「${data.groupName}」重命名为「${data.newGroupName}」`,
      )
      setGroupRenameTarget(null)
      void queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
      void queryClient.invalidateQueries({
        queryKey: ['softwareRepositories', projectId],
      })
    },
    onError: error => message.error(errorMessage(error)),
  })
  const deleteGroupMutation = useMutation({
    mutationFn: (target: GroupTarget) =>
      interfaceLibraryApi.deleteApiInterfaceGroup(
        target.repository.softwareRepositoryId,
        { groupName: target.group.tag },
      ),
    onSuccess: (data, target) => {
      syncDraftAfterGroupRemoval(target.repository.softwareRepositoryId, target.group.tag)
      message.success(
        data.updatedCount
          ? `已移除分组「${data.groupName}」，${data.updatedCount} 个接口归入「未分类」`
          : `已移除分组「${data.groupName}」`,
      )
      void queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
      void queryClient.invalidateQueries({
        queryKey: ['softwareRepositories', projectId],
      })
    },
    onError: error => message.error(errorMessage(error)),
  })
  const moveMutation = useMutation({
    mutationFn: ({
      item,
      groupName,
    }: {
      item: ApiInterfaceListItem
      groupName: string
    }) => interfaceLibraryApi.moveApiInterfaceToGroup(item.interfaceId, { groupName }),
    onSuccess: (data, variables) => {
      if (draft?.interfaceId && draft.interfaceId === data.interfaceId) {
        setDraft(previous =>
          previous && previous.interfaceId === data.interfaceId
            ? {
                ...previous,
                tags: data.tags,
                version: data.version,
                updatedAt: data.updatedAt,
              }
            : previous,
        )
        setTagsText(data.tags.join(', '))
      }
      message.success(
        variables.groupName
          ? `已将「${data.name}」移动到分组「${variables.groupName}」`
          : `已清除「${data.name}」的标签并归入「未分类」`,
      )
      setMoveTarget(null)
      void queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
    },
    onError: error => message.error(errorMessage(error)),
  })
  const createGroupMutation = useMutation({
    mutationFn: ({
      repository,
      groupName,
    }: {
      repository: SoftwareRepository
      groupName: string
    }) =>
      interfaceLibraryApi.createApiInterfaceGroup(repository.softwareRepositoryId, {
        groupName,
      }),
    onSuccess: data => {
      message.success(`已创建分组「${data.newGroupName}」`)
      setCreateGroupRepository(null)
      void queryClient.invalidateQueries({
        queryKey: ['softwareRepositories', projectId],
      })
    },
    onError: error => message.error(errorMessage(error)),
  })

  function syncDraftAfterGroupRename(
    softwareRepositoryId: string,
    currentGroup: string,
    newGroup: string,
  ) {
    if (draft?.softwareRepositoryId !== softwareRepositoryId) return
    setDraft(previous => {
      if (
        !previous?.interfaceId ||
        previous.softwareRepositoryId !== softwareRepositoryId ||
        firstTag(previous.tags) !== currentGroup
      ) {
        return previous
      }
      return { ...previous, tags: replaceFirstTag(previous.tags, newGroup) }
    })
    setTagsText(previous => {
      const parsed = splitTags(previous)
      if (firstTag(parsed) !== currentGroup) return previous
      return replaceFirstTag(parsed, newGroup).join(', ')
    })
  }

  function syncDraftAfterGroupRemoval(
    softwareRepositoryId: string,
    groupName: string,
  ) {
    if (draft?.softwareRepositoryId !== softwareRepositoryId) return
    setDraft(previous => {
      if (
        !previous?.interfaceId ||
        previous.softwareRepositoryId !== softwareRepositoryId ||
        firstTag(previous.tags) !== groupName
      ) {
        return previous
      }
      return { ...previous, tags: [] }
    })
    setTagsText(previous =>
      firstTag(splitTags(previous)) === groupName ? '' : previous,
    )
  }

  function openCreateGroup(repository: SoftwareRepository) {
    setCreateGroupRepository(repository)
    setCreateGroupName('')
  }

  function submitCreateGroup() {
    if (!createGroupRepository) return
    const groupName = createGroupName.trim()
    if (!groupName) {
      message.warning('请输入分组名称')
      return
    }
    createGroupMutation.mutate({ repository: createGroupRepository, groupName })
  }

  function openRenameGroup(repository: SoftwareRepository, group: InterfaceGroup) {
    setGroupRenameTarget({ repository, group })
    setGroupRenameValue(group.tag)
  }

  function submitRenameGroup() {
    if (!groupRenameTarget) return
    const newGroupName = groupRenameValue.trim()
    if (!newGroupName) {
      message.warning('请输入分组名称')
      return
    }
    if (newGroupName === groupRenameTarget.group.tag) {
      setGroupRenameTarget(null)
      return
    }
    renameGroupMutation.mutate({ target: groupRenameTarget, newGroupName })
  }

  function openRemoveGroup(repository: SoftwareRepository, group: InterfaceGroup) {
    Modal.confirm({
      title: '移除分组',
      content: `该组 ${group.items.length} 个接口将清除全部标签并归入「未分类」，接口不会被删除，次要标签也会被清除。`,
      okText: '移除分组',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteGroupMutation.mutateAsync({ repository, group }),
    })
  }

  function openMoveInterface(
    repository: SoftwareRepository,
    item: ApiInterfaceListItem,
    groups: string[],
  ) {
    setMoveTarget({ repository, item, groups })
    setMoveMode('group')
    setMoveGroupName('')
  }

  function submitMoveInterface() {
    if (!moveTarget) return
    const groupName = moveMode === 'clear' ? '' : moveGroupName.trim()
    if (moveMode === 'group' && !groupName) {
      message.warning('请选择或输入目标分组')
      return
    }
    moveMutation.mutate({ item: moveTarget.item, groupName })
  }

  function patch(patchValue: Partial<ApiInterface>) {
    setDraft(previous => (previous ? { ...previous, ...patchValue } : previous))
  }

  function changePath(path: string) {
    setDraft(previous =>
      previous
        ? { ...previous, path, pathParams: syncPathParams(path, previous.pathParams) }
        : previous,
    )
  }

  function changeRepository(softwareRepositoryId: string) {
    const repository = repositories.find(
      item => item.softwareRepositoryId === softwareRepositoryId,
    )
    setDraft(previous =>
      previous
        ? {
            ...previous,
            softwareRepositoryId,
            softwareRepositoryName: repository?.name ?? '',
          }
        : previous,
    )
  }

  function confirmDelete() {
    if (!draft || isCreate) return
    if (draft.interfaceId !== interfaceId) {
      message.info('接口正在切换，请稍候再操作')
      return
    }
    Modal.confirm({
      title: '删除接口',
      content: `确定删除「${draft.name || draft.path}」吗？删除后不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteMutation.mutateAsync(),
    })
  }

  const tabs: { key: TabKey; label: string; count?: number }[] = draft
    ? [
        { key: 'params', label: '参数', count: enabledCount(draft.pathParams) + enabledCount(draft.queryParams) },
        { key: 'headers', label: '请求头', count: enabledCount(draft.headers) },
        { key: 'body', label: '请求体', count: draft.bodyType === 'none' ? 0 : 1 },
        { key: 'response', label: '响应', count: 1 },
        { key: 'settings', label: '设置' },
      ]
    : []

  if (interfaceId && interfaceQuery.isError) {
    return (
      <InterfaceWorkspaceShell>
        <Alert
          type="error"
          showIcon
          title="接口加载失败"
          description={errorMessage(interfaceQuery.error)}
          action={<Button onClick={() => navigate('/asset-library?tab=interfaces')}>返回接口库</Button>}
        />
      </InterfaceWorkspaceShell>
    )
  }

  if (!draft) {
    if (isCreate && !projectId) {
      return (
        <InterfaceWorkspaceShell>
          <Empty description="请先在顶部选择一个项目" />
        </InterfaceWorkspaceShell>
      )
    }
    if (isCreate && repositoriesQuery.isError) {
      return (
        <InterfaceWorkspaceShell>
          <Alert
            type="error"
            showIcon
            title="软件仓库加载失败"
            description="请检查当前项目权限后重试。"
            action={<Button onClick={() => void repositoriesQuery.refetch()}>重试</Button>}
          />
        </InterfaceWorkspaceShell>
      )
    }
    if (isCreate && !repositoriesQuery.isLoading && !repositories.length) {
      return (
        <InterfaceWorkspaceShell>
          <Empty description="当前项目还没有软件仓库，请先在「软件仓库」页创建。" />
        </InterfaceWorkspaceShell>
      )
    }
    return (
      <InterfaceWorkspaceShell className="if-detail-loading">
        <Spin />
      </InterfaceWorkspaceShell>
    )
  }

  if (!isCreate && !repositoriesQuery.isLoading && !interfaceInActiveProject) {
    return (
      <InterfaceWorkspaceShell>
        <Alert
          type="error"
          showIcon
          title="接口不属于当前项目"
          description="请切换回接口所属项目后重试。"
          action={<Button onClick={() => navigate('/asset-library?tab=interfaces')}>返回接口库</Button>}
        />
      </InterfaceWorkspaceShell>
    )
  }

  const repositoryBasePath = selectedRepository?.basePath || ''
  const methodToneClass = methodTone(draft.method)

  return (
    <InterfaceWorkspaceShell>
      <header className="if-detail-topbar">
        <div className="if-detail-topbar-main">
          <Tooltip title="返回接口库">
            <Button
              type="text"
              aria-label="返回接口库"
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate(-1)}
            />
          </Tooltip>
          <div className="if-detail-heading">
            <div className="if-detail-title-row">
              <h1>{draft.name.trim() || (isCreate ? '新建接口' : '未命名接口')}</h1>
              {isCreate ? <Tag>草稿</Tag> : null}
              {!canWrite ? <Tag>只读成员 · 不可编辑</Tag> : null}
            </div>
            <div className="if-detail-meta">
              <Tag className={`if-method if-method-${methodToneClass}`}>{draft.method}</Tag>
              <code>{draft.path || '未填写路径'}</code>
              <span className="if-meta-dot">·</span>
              <span>{draft.softwareRepositoryName || selectedRepository?.name || '未选择软件仓库'}</span>
              <span className="if-meta-dot">·</span>
              <span>{draft.updatedAt ? `更新于 ${formatTime(draft.updatedAt)}` : '尚未保存'}</span>
            </div>
          </div>
        </div>
        <div className="if-detail-topbar-actions">
          <Tooltip title="刷新">
            <Button
              aria-label="刷新接口"
              icon={<ReloadOutlined />}
              onClick={() => {
                if (interfaceId) void interfaceQuery.refetch()
                void queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
              }}
            />
          </Tooltip>
          {canWrite && !isCreate ? (
            <Button
              icon={<PlusOutlined />}
              onClick={() =>
                navigate(`/asset-library/interfaces/new?softwareRepositoryId=${encodeURIComponent(draft.softwareRepositoryId)}`)
              }
            >
              新建接口
            </Button>
          ) : null}
          {canWrite ? (
            <Button
              icon={<UploadOutlined />}
              disabled={!repositories.length}
              onClick={() => setImportOpen(true)}
            >
              导入 OpenAPI
            </Button>
          ) : null}
          {canWrite && !isCreate ? (
            <Button
              danger
              icon={<DeleteOutlined />}
              disabled={draft.interfaceId !== interfaceId}
              onClick={confirmDelete}
            >
              删除
            </Button>
          ) : null}
        </div>
      </header>

      <div className="if-detail-shell">
        <SoftwareRepositoryTree
          repositories={repositories}
          loading={repositoriesQuery.isLoading}
          selectedSoftwareRepositoryId={draft.softwareRepositoryId}
          selectedInterfaceId={draft.interfaceId}
          mode="detail"
          canManageInterfaces={canWrite}
          onSelectRepository={() => undefined}
          onShowAll={() => navigate('/asset-library?tab=interfaces')}
          onOpenInterface={id => navigate(`/asset-library/interfaces/${id}`)}
          onCreateGroup={openCreateGroup}
          onRenameGroup={openRenameGroup}
          onRemoveGroup={openRemoveGroup}
          onMoveInterface={openMoveInterface}
        />

        <main className="if-detail-main">
          <section className="if-editor-card">
            <div className="if-editor-head">
              <Input
                className="if-name-input"
                value={draft.name}
                maxLength={120}
                disabled={!canWrite}
                placeholder="接口名称，例如：查询订单详情"
                aria-label="接口名称"
                onChange={event => patch({ name: event.target.value })}
              />
              <div className="if-editor-meta">
                <span>所属软件仓库</span>
                {isCreate ? (
                  <Select
                    className="if-app-select"
                    aria-label="所属软件仓库"
                    value={draft.softwareRepositoryId || undefined}
                    placeholder="选择软件仓库"
                    disabled={!canWrite}
                    options={repositories.map(repository => ({
                      label: repository.name,
                      value: repository.softwareRepositoryId,
                    }))}
                    onChange={changeRepository}
                  />
                ) : (
                  <span className="if-editor-app">{draft.softwareRepositoryName || selectedRepository?.name || '—'}</span>
                )}
                <span className="if-meta-dot">·</span>
                <span>{draft.updatedAt ? formatTime(draft.updatedAt) : '新建'}</span>
              </div>
            </div>

            <div className="if-request-bar">
              <Select
                className={`if-method-select if-method-${methodToneClass}`}
                aria-label="请求方法"
                value={draft.method}
                disabled={!canWrite}
                options={INTERFACE_METHODS.map(method => ({ label: method, value: method }))}
                onChange={method => patch({ method })}
              />
              <div className="if-path-input-wrap">
                <span className="if-base-prefix" title={repositoryBasePath || '软件仓库未设置 base path'}>
                  {repositoryBasePath || '/…'}
                </span>
                <Input
                  className="if-path-input"
                  value={draft.path}
                  disabled={!canWrite}
                  placeholder="/orders/{orderId}"
                  aria-label="接口路径"
                  onChange={event => changePath(event.target.value)}
                  onBlur={() => changePath(draft.path.trim())}
                />
              </div>
              {canWrite ? (
                <Button
                  type="primary"
                  className="if-save-button"
                  loading={saveMutation.isPending}
                  disabled={
                    !draft.name.trim() ||
                    !draft.path.trim() ||
                    !draft.softwareRepositoryId ||
                    !interfaceInActiveProject ||
                    (!isCreate && draft.interfaceId !== interfaceId)
                  }
                  onClick={() => saveMutation.mutate()}
                >
                  {isCreate ? '创建接口' : '保存'}
                </Button>
              ) : (
                <Tag className="if-readonly-tag">只读</Tag>
              )}
            </div>

            <div className="if-editor-tabs" role="tablist" aria-label="接口编辑分区">
              {tabs.map(tab => (
                <button
                  key={tab.key}
                  type="button"
                  role="tab"
                  id={`if-editor-tab-${tab.key}`}
                  aria-controls={`if-editor-panel-${tab.key}`}
                  aria-selected={activeTab === tab.key}
                  className={`if-editor-tab${activeTab === tab.key ? ' is-active' : ''}`}
                  onClick={() => setActiveTab(tab.key)}
                >
                  {tab.label}
                  {tab.count !== undefined ? <span className="if-tab-count">{tab.count}</span> : null}
                </button>
              ))}
            </div>

            <div
              className="if-editor-body"
              role="tabpanel"
              id={`if-editor-panel-${activeTab}`}
              aria-labelledby={`if-editor-tab-${activeTab}`}
            >
              {activeTab === 'params' ? (
                <div className="if-tab-section">
                  <InterfaceParamsPanel
                    title="Path 参数"
                    hint="路径占位符自动同步；Path 参数始终必填。"
                    location="path"
                    rows={draft.pathParams}
                    readOnly={!canWrite}
                    onChange={rows => patch({ pathParams: rows })}
                  />
                  <InterfaceParamsPanel
                    title="Query 参数"
                    hint="查询参数会保存在接口定义中，后续可用于生成用例。"
                    location="query"
                    rows={draft.queryParams}
                    readOnly={!canWrite}
                    onChange={rows => patch({ queryParams: rows })}
                  />
                </div>
              ) : null}

              {activeTab === 'headers' ? (
                <div className="if-tab-section">
                  <InterfaceHeadersPanel
                    rows={draft.headers}
                    readOnly={!canWrite}
                    onChange={rows => patch({ headers: rows })}
                  />
                </div>
              ) : null}

              {activeTab === 'body' ? (
                <InterfaceBodyPanel
                  draft={draft}
                  readOnly={!canWrite}
                  schemaText={jsonTexts.bodySchema}
                  exampleText={jsonTexts.bodyExample}
                  onSchemaText={value => setJsonTexts(previous => ({ ...previous, bodySchema: value }))}
                  onExampleText={value => setJsonTexts(previous => ({ ...previous, bodyExample: value }))}
                  onChange={patch}
                />
              ) : null}

              {activeTab === 'response' ? (
                <InterfaceResponsePanel
                  draft={draft}
                  readOnly={!canWrite}
                  schemaText={jsonTexts.responseSchema}
                  exampleText={jsonTexts.responseExample}
                  onSchemaText={value => setJsonTexts(previous => ({ ...previous, responseSchema: value }))}
                  onExampleText={value => setJsonTexts(previous => ({ ...previous, responseExample: value }))}
                  onChange={patch}
                />
              ) : null}

              {activeTab === 'settings' ? (
                <InterfaceSettingsPanel
                  draft={draft}
                  readOnly={!canWrite}
                  tagsText={tagsText}
                  onTagsText={setTagsText}
                  requirementOptions={allRequirements}
                  onChange={patch}
                />
              ) : null}
            </div>
          </section>
        </main>
      </div>
      <OpenApiImportModal
        open={importOpen}
        repositories={repositories}
        defaultSoftwareRepositoryId={draft.softwareRepositoryId}
        onClose={() => setImportOpen(false)}
        onImported={() => {
          setImportOpen(false)
          queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
          queryClient.invalidateQueries({ queryKey: ['softwareRepositories', projectId] })
          if (isCreate) {
            const target = draft.softwareRepositoryId
              ? `?tab=interfaces&softwareRepositoryId=${encodeURIComponent(draft.softwareRepositoryId)}`
              : '?tab=interfaces'
            navigate(`/asset-library${target}`)
            return
          }
          if (interfaceId) void interfaceQuery.refetch()
        }}
      />
      <Modal
        rootClassName={interfaceScopes}
        open={Boolean(createGroupRepository)}
        title="新建分组"
        okText="创建"
        cancelText="取消"
        confirmLoading={createGroupMutation.isPending}
        destroyOnHidden
        onOk={submitCreateGroup}
        onCancel={() => setCreateGroupRepository(null)}
      >
        <div className="if-group-modal">
          <div className="if-group-modal-label">
            <span>软件仓库</span>
            <Tag>{createGroupRepository?.name}</Tag>
          </div>
          <Input
            aria-label="分组名称"
            value={createGroupName}
            maxLength={50}
            showCount
            placeholder="输入分组名称"
            onChange={event => setCreateGroupName(event.target.value)}
            onPressEnter={submitCreateGroup}
          />
          <p className="if-group-modal-hint">
            分组会保存在软件仓库中，即使暂时没有接口也会保留；可在接口的「更多操作」中移动接口进来。
          </p>
        </div>
      </Modal>
      <Modal
        rootClassName={interfaceScopes}
        open={Boolean(groupRenameTarget)}
        title="重命名分组"
        okText="保存"
        cancelText="取消"
        confirmLoading={renameGroupMutation.isPending}
        destroyOnHidden
        onOk={submitRenameGroup}
        onCancel={() => setGroupRenameTarget(null)}
      >
        <div className="if-group-modal">
          <div className="if-group-modal-label">
            <span>当前分组</span>
            <Tag>{groupRenameTarget?.group.tag}</Tag>
          </div>
          <Input
            aria-label="新分组名称"
            value={groupRenameValue}
            maxLength={50}
            showCount
            placeholder="输入新的分组名称"
            onChange={event => setGroupRenameValue(event.target.value)}
            onPressEnter={submitRenameGroup}
          />
          <p className="if-group-modal-hint">
            将修改该分组下接口的首个标签；若目标分组已存在，操作会被拒绝，不会自动合并。
          </p>
        </div>
      </Modal>
      <Modal
        rootClassName={interfaceScopes}
        open={Boolean(moveTarget)}
        title="移动到分组"
        okText="移动"
        cancelText="取消"
        confirmLoading={moveMutation.isPending}
        destroyOnHidden
        onOk={submitMoveInterface}
        onCancel={() => setMoveTarget(null)}
      >
        <div className="if-group-modal">
          <div className="if-group-modal-label">
            <span>接口</span>
            <span className="if-group-modal-interface">
              {moveTarget?.item.name || moveTarget?.item.path}
            </span>
          </div>
          <Radio.Group
            value={moveMode}
            onChange={event => setMoveMode(event.target.value)}
          >
            <Radio value="group">移动到分组</Radio>
            <Radio value="clear">清除全部标签（归入「未分类」）</Radio>
          </Radio.Group>
          {moveMode === 'group' ? (
            <AutoComplete
              className="if-group-move-select"
              aria-label="目标分组"
              value={moveGroupName}
              options={(moveTarget?.groups ?? []).map(name => ({
                value: name,
                label: name,
              }))}
              placeholder="选择已有分组，或输入新分组名称"
              onChange={value => setMoveGroupName(value)}
            />
          ) : null}
          <p className="if-group-modal-hint">
            移动到已有或新分组会将该标签置顶；清除标签后接口归入「未分类」，次要标签也会被清除。
          </p>
        </div>
      </Modal>
    </InterfaceWorkspaceShell>
  )
}

function InterfaceWorkspaceShell({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className="workbench-page asset-library-page">
      <div className="asset-library-tab-panel">
        <div className="asset-library-tab-pane">
          <div className={`workbench-page interface-library-page tp-surface ${styles.pageRoot} ${interfaceScopes}${className ? ` ${className}` : ''}`}>
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}

function enabledCount(rows: InterfaceRow[]) {
  return rows.filter(row => row.enabled && row.name.trim()).length
}

function jsonTextsOf(data: ApiInterface): JsonTexts {
  return {
    bodySchema: jsonText(data.bodySchema),
    bodyExample: jsonText(data.bodyExample),
    responseSchema: jsonText(data.responseSchema),
    responseExample: jsonText(data.responseExample),
  }
}

function buildPayload(
  draft: ApiInterface,
  tagsText: string,
  jsonTexts: JsonTexts,
): CreateApiInterfacePayload {
  const name = draft.name.trim()
  if (!name) throw new Error('请填写接口名称')
  const path = draft.path.trim()
  if (!path) throw new Error('请填写接口路径')

  const pathParams = cleanRows(draft.pathParams, 'Path 参数', true)
  const queryParams = cleanRows(draft.queryParams, 'Query 参数', false)
  const headers = cleanRows(draft.headers, '请求头', false)
  validatePathRows(path, pathParams)

  const hasJsonBody = draft.bodyType === 'json' || draft.bodyType === 'form'
  const bodySchema = hasJsonBody ? parseEditorJson(jsonTexts.bodySchema, '请求体 Schema') : null
  const bodyExample = hasJsonBody ? parseEditorJson(jsonTexts.bodyExample, '请求体示例') : null
  const responseSchema = parseEditorJson(jsonTexts.responseSchema, '响应 Schema')
  const responseExample = parseEditorJson(jsonTexts.responseExample, '响应示例')
  const tags = splitTags(tagsText)
  const description = draft.description.trim()
  const responseDescription = draft.responseDescription.trim()

  if (description.length > 1024) throw new Error('接口描述不能超过 1024 个字符')
  if (responseDescription.length > 512) throw new Error('响应说明不能超过 512 个字符')
  if (tags.length > 20) throw new Error('标签不能超过 20 个')
  if (draft.bodyText.length > 20000) throw new Error('Raw 请求体不能超过 20000 个字符')
  for (const [label, rows] of [
    ['请求头', headers],
    ['Path 参数', pathParams],
    ['Query 参数', queryParams],
  ] as const) {
    if (rows.length > 200) throw new Error(`${label}不能超过 200 行`)
  }

  return {
    name,
    method: draft.method,
    path,
    description,
    tags,
    headers,
    pathParams,
    queryParams,
    bodyType: draft.bodyType,
    // Hidden editors for raw/none body types must not block saving their stale text.
    bodySchema,
    bodyExample,
    bodyText: draft.bodyType === 'raw' ? draft.bodyText : '',
    responseStatus: draft.responseStatus,
    responseDescription,
    responseSchema,
    responseExample,
    requirementIds: draft.requirements.map(requirement => requirement.requirementId),
  }
}

function cleanRows(rows: InterfaceRow[], label: string, forceRequired: boolean): InterfaceRow[] {
  const kept = rows.filter(
    row => row.name.trim() || row.example.trim() || row.description.trim(),
  )
  const missingName = kept.find(row => !row.name.trim())
  if (missingName) throw new Error(`${label}中存在未填写名称的行`)
  const seen = new Set<string>()
  return kept.map(row => {
    const rowName = row.name.trim()
    const identity = label === '请求头' ? rowName.toLowerCase() : rowName
    if (seen.has(identity)) throw new Error(`${label}名称重复：${rowName}`)
    seen.add(identity)
    return {
      ...row,
      name: rowName,
      required: forceRequired ? true : row.required,
      example: row.example,
      description: row.description.trim(),
    }
  })
}

function validatePathRows(path: string, rows: InterfaceRow[]) {
  const expected = new Set(pathParameterNames(path))
  const actual = new Set(rows.map(row => row.name))
  const missing = [...expected].filter(name => !actual.has(name))
  const extra = [...actual].filter(name => !expected.has(name))
  if (!missing.length && !extra.length) return
  const parts: string[] = []
  if (missing.length) parts.push(`缺少 ${missing.join('、')}`)
  if (extra.length) parts.push(`多余 ${extra.join('、')}`)
  throw new Error(`Path 参数与路径占位符不一致（${parts.join('；')}）`)
}

function parseEditorJson(text: string, label: string): unknown {
  const parsed = parseJsonText(text)
  if (!parsed.valid) throw new Error(`${label}格式错误：${parsed.error}`)
  return parsed.value
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return getErrorMessage(error)
}
