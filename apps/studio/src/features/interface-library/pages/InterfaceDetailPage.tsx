import {
  ArrowLeftOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Empty, Input, Modal, Select, Spin, Tag, Tooltip } from 'antd'
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { AssetLibraryTabs } from '@/app/pages/AssetLibraryTabs'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { useProjectRequirementOptions } from '@/features/projects/hooks/useProjectRequirementOptions'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { ApiError } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import { ApiAppEditorDrawer } from '../components/ApiAppEditorDrawer'
import { InterfaceAppTree } from '../components/InterfaceAppTree'
import { InterfaceBodyPanel } from '../components/InterfaceBodyPanel'
import { InterfaceHeadersPanel } from '../components/InterfaceHeadersPanel'
import { InterfaceParamsPanel } from '../components/InterfaceParamsPanel'
import { InterfaceResponsePanel } from '../components/InterfaceResponsePanel'
import { InterfaceSettingsPanel } from '../components/InterfaceSettingsPanel'
import { OpenApiImportModal } from '../components/OpenApiImportModal'
import { useApiAppManager } from '../hooks/useApiAppManager'
import type { ApiInterface, CreateApiInterfacePayload, InterfaceRow } from '../types'
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
import '@/shared/styles/surface-tokens.css'
import '../styles/index.css'

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

export function InterfaceDetailPage() {
  const { interfaceId } = useParams<{ interfaceId: string }>()
  const isCreate = !interfaceId
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const projectId = useWorkbenchStore(state => state.activeProjectId) ?? ''
  const { can } = useProjectAccess(projectId)
  const canWrite = can('write')
  const canManage = can('manage')
  const { allRequirements } = useProjectRequirementOptions({ activeProjectId: projectId })
  const {
    apps,
    appsQuery,
    editorOpen,
    editingApp,
    openCreate,
    openEdit,
    closeEditor,
    toggleApp,
    deleteApp,
  } = useApiAppManager(projectId)

  const [draft, setDraft] = useState<ApiInterface | null>(null)
  const [tagsText, setTagsText] = useState('')
  const [jsonTexts, setJsonTexts] = useState<JsonTexts>(EMPTY_JSON_TEXTS)
  const [activeTab, setActiveTab] = useState<TabKey>('params')
  const [importOpen, setImportOpen] = useState(false)

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
    if (!isCreate || draft || appsQuery.isLoading) return
    const requestedAppId = searchParams.get('appId') ?? ''
    const app =
      apps.find(item => item.appId === requestedAppId) ??
      apps.find(item => item.enabled) ??
      apps[0]
    if (!app) return
    const next = blankInterface(app.appId)
    next.appName = app.name
    setDraft(next)
  }, [apps, appsQuery.isLoading, draft, isCreate, searchParams])

  const selectedApp = apps.find(app => app.appId === draft?.appId)
  const interfaceInActiveProject =
    isCreate || apps.some(app => app.appId === draft?.appId)

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!draft) throw new Error('接口尚未加载')
      if (!isCreate && draft.interfaceId !== interfaceId) {
        throw new Error('接口正在切换，请稍候再保存')
      }
      if (!interfaceInActiveProject) throw new Error('接口不属于当前项目')
      const payload = buildPayload(draft, tagsText, jsonTexts)
      if (isCreate) {
        if (!draft.appId) throw new Error('请选择所属应用')
        return interfaceLibraryApi.createApiInterface(draft.appId, payload)
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
      queryClient.invalidateQueries({ queryKey: ['apiApps', projectId] })
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
      queryClient.invalidateQueries({ queryKey: ['apiApps', projectId] })
      navigate('/asset-library?tab=interfaces')
    },
    onError: error => message.error(errorMessage(error)),
  })

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

  function changeApp(appId: string) {
    const app = apps.find(item => item.appId === appId)
    setDraft(previous =>
      previous ? { ...previous, appId, appName: app?.name ?? '' } : previous,
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
    if (isCreate && appsQuery.isError) {
      return (
        <InterfaceWorkspaceShell>
          <Alert
            type="error"
            showIcon
            title="接口应用加载失败"
            description="请检查当前项目权限后重试。"
            action={<Button onClick={() => void appsQuery.refetch()}>重试</Button>}
          />
        </InterfaceWorkspaceShell>
      )
    }
    if (isCreate && !appsQuery.isLoading && !apps.length) {
      return (
        <InterfaceWorkspaceShell>
          <Empty
            description={
              canManage ? '还没有接口应用，请先创建应用' : '当前项目还没有接口应用，请联系项目所有者创建'
            }
          >
            {canManage ? (
              <Button type="primary" onClick={openCreate}>
                新建应用
              </Button>
            ) : null}
          </Empty>
          {canManage ? (
            <ApiAppEditorDrawer
              open={editorOpen}
              projectId={projectId}
              app={editingApp}
              onClose={closeEditor}
              onSaved={closeEditor}
            />
          ) : null}
        </InterfaceWorkspaceShell>
      )
    }
    return (
      <InterfaceWorkspaceShell className="if-detail-loading">
        <Spin />
      </InterfaceWorkspaceShell>
    )
  }

  if (!isCreate && !appsQuery.isLoading && !interfaceInActiveProject) {
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

  const appBasePath = selectedApp?.basePath || ''
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
              <span className={`if-status ${draft.enabled ? 'is-enabled' : 'is-disabled'}`}>
                {draft.enabled ? '启用' : '停用'}
              </span>
              {isCreate ? <Tag>草稿</Tag> : null}
              {!canWrite ? <Tag>只读成员 · 不可编辑</Tag> : null}
            </div>
            <div className="if-detail-meta">
              <Tag className={`if-method if-method-${methodToneClass}`}>{draft.method}</Tag>
              <code>{draft.path || '未填写路径'}</code>
              <span className="if-meta-dot">·</span>
              <span>{draft.appName || selectedApp?.name || '未选择应用'}</span>
              <span className="if-meta-dot">·</span>
              <span>{draft.updatedAt ? `更新于 ${formatTime(draft.updatedAt)}` : '尚未保存'}</span>
            </div>
          </div>
        </div>
        <div className="if-detail-topbar-actions">
          {canWrite && !isCreate ? (
            <Button
              icon={<PlusOutlined />}
              onClick={() =>
                navigate(`/asset-library/interfaces/new?appId=${encodeURIComponent(draft.appId)}`)
              }
            >
              新建接口
            </Button>
          ) : null}
          {canWrite && !isCreate ? (
            <Button
              icon={<UploadOutlined />}
              disabled={!apps.length}
              onClick={() => setImportOpen(true)}
            >
              导入 OpenAPI
            </Button>
          ) : null}
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
        <InterfaceAppTree
          apps={apps}
          loading={appsQuery.isLoading}
          selectedAppId={draft.appId}
          selectedInterfaceId={draft.interfaceId}
          mode="detail"
          canManageApps={canManage}
          onSelectApp={() => undefined}
          onShowAll={() => navigate('/asset-library?tab=interfaces')}
          onOpenInterface={id => navigate(`/asset-library/interfaces/${id}`)}
          onCreateApp={openCreate}
          onEditApp={openEdit}
          onToggleApp={toggleApp}
          onDeleteApp={deleteApp}
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
                <span>所属应用</span>
                {isCreate ? (
                  <Select
                    className="if-app-select"
                    aria-label="所属应用"
                    value={draft.appId || undefined}
                    placeholder="选择应用"
                    disabled={!canWrite}
                    options={apps.map(app => ({
                      label: `${app.name}${app.enabled ? '' : '（已停用）'}`,
                      value: app.appId,
                    }))}
                    onChange={changeApp}
                  />
                ) : (
                  <span className="if-editor-app">{draft.appName || selectedApp?.name || '—'}</span>
                )}
                <span className="if-meta-dot">·</span>
                <span>{draft.updatedAt ? formatTime(draft.updatedAt) : '新建'}</span>
                <span className={`if-status ${draft.enabled ? 'is-enabled' : 'is-disabled'}`}>
                  {draft.enabled ? '启用' : '停用'}
                </span>
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
                <span className="if-base-prefix" title={appBasePath || '应用未设置 base path'}>
                  {appBasePath || '/…'}
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
                    !draft.appId ||
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
                  app={selectedApp}
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
        apps={apps}
        defaultAppId={draft.appId}
        onClose={() => setImportOpen(false)}
        onImported={() => {
          setImportOpen(false)
          queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
          queryClient.invalidateQueries({ queryKey: ['apiApps', projectId] })
          if (interfaceId) void interfaceQuery.refetch()
        }}
      />
      <ApiAppEditorDrawer
        open={editorOpen}
        projectId={projectId}
        app={editingApp}
        onClose={closeEditor}
        onSaved={closeEditor}
      />
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
  const navigate = useNavigate()
  return (
    <div className="workbench-page asset-library-page">
      <AssetLibraryTabs
        activeTab="interfaces"
        onSelect={tab => {
          if (tab !== 'interfaces') navigate(`/asset-library?tab=${tab}`)
        }}
      />
      <div className="asset-library-tab-panel">
        <div className="asset-library-tab-pane">
          <div className={`workbench-page interface-library-page tp-surface${className ? ` ${className}` : ''}`}>
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
    enabled: draft.enabled,
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
