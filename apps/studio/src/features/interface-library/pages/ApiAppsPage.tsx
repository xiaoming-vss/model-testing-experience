import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { Button, Empty, Spin, Table, Tag, Tooltip } from 'antd'
import type { TableProps } from 'antd'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { DebouncedSearchInput } from '@/shared/components/DebouncedSearchInput'
import { formatTime } from '@/utils/format'
import { ApiAppEditorDrawer } from '../components/ApiAppEditorDrawer'
import { useApiAppManager } from '../hooks/useApiAppManager'
import type { ApiApp } from '../types'
import '@/shared/styles/surface-tokens.css'
import '../styles/index.css'

/** 项目级接口应用管理；接口库左侧应用树提供同一批应用的快捷入口。 */
export function ApiAppsPage() {
  const navigate = useNavigate()
  const projectId = useWorkbenchStore(state => state.activeProjectId) ?? ''
  const { can } = useProjectAccess(projectId)
  const canManage = can('manage')
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
  const [keyword, setKeyword] = useState('')
  const [searchResetKey, setSearchResetKey] = useState(0)

  const filteredApps = useMemo(() => {
    const search = keyword.trim().toLowerCase()
    if (!search) return apps
    return apps.filter(app =>
      app.name.toLowerCase().includes(search) ||
      app.basePath.toLowerCase().includes(search) ||
      app.repository?.path.toLowerCase().includes(search),
    )
  }, [apps, keyword])

  function openAppInterfaces(app: ApiApp) {
    navigate(`/asset-library?tab=interfaces&appId=${encodeURIComponent(app.appId)}`)
  }

  const columns: TableProps<ApiApp>['columns'] = [
    {
      title: '应用',
      key: 'name',
      width: 300,
      render: (_, app) => (
        <div className="if-app-name-cell">
          <button
            type="button"
            className="if-name-link"
            onClick={event => {
              event.stopPropagation()
              openAppInterfaces(app)
            }}
          >
            {app.name}
          </button>
          {app.enabled ? null : <Tag>停用</Tag>}
        </div>
      ),
    },
    {
      title: '代码仓库',
      key: 'repository',
      render: (_, app) => (
        <span className="if-path">{app.repository?.path || '—'}</span>
      ),
    },
    {
      title: 'base path',
      dataIndex: 'basePath',
      key: 'basePath',
      width: 180,
      render: (basePath: string) => (
        <span className="if-path">{basePath || '—'}</span>
      ),
    },
    {
      title: '接口数',
      key: 'interfaceCount',
      width: 130,
      render: (_, app) => (
        <span title={`共 ${app.interfaceCount} 个，启用 ${app.enabledInterfaceCount} 个`}>
          {app.interfaceCount}
          <span className="if-app-enabled-count"> · 启用 {app.enabledInterfaceCount}</span>
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 90,
      render: (enabled: boolean) => (
        <span className={`if-status ${enabled ? 'is-enabled' : 'is-disabled'}`}>
          {enabled ? '启用' : '停用'}
        </span>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updatedAt',
      key: 'updatedAt',
      width: 160,
      render: (value?: string) => formatTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 132,
      align: 'right',
      render: (_, app) =>
        canManage ? (
          <div className="if-row-actions" onClick={event => event.stopPropagation()}>
            <Tooltip title="编辑">
              <Button
                type="text"
                size="small"
                aria-label={`编辑${app.name}`}
                icon={<EditOutlined />}
                onClick={() => openEdit(app)}
              />
            </Tooltip>
            <Tooltip title={app.enabled ? '停用' : '启用'}>
              <Button
                type="text"
                size="small"
                aria-label={`${app.enabled ? '停用' : '启用'}${app.name}`}
                icon={<ReloadOutlined />}
                onClick={() => toggleApp(app)}
              />
            </Tooltip>
            <Tooltip title={app.interfaceCount > 0 ? '先删除该应用下的接口' : '删除应用'}>
              <Button
                type="text"
                size="small"
                danger
                disabled={app.interfaceCount > 0}
                aria-label={`删除${app.name}`}
                icon={<DeleteOutlined />}
                onClick={() => deleteApp(app)}
              />
            </Tooltip>
          </div>
        ) : (
          '—'
        ),
    },
  ]

  return (
    <div className="workbench-page interface-library-page tp-surface tp-list-surface">
      <section className="tp-board tp-list-panel if-library-board">
        <div className="if-library-toolbar tp-list-toolbar">
          <div className="if-toolbar-filters">
            <h1 className="tp-list-title">应用</h1>
            <span className="if-app-tree-total">{apps.length}</span>
            <DebouncedSearchInput
              ariaLabel="搜索应用"
              placeholder="搜索应用名称 / 仓库 / base path"
              className="if-search-input"
              prefix={<SearchOutlined />}
              resetKey={searchResetKey}
              onCommit={setKeyword}
            />
          </div>
          <div className="if-toolbar-actions">
            <Tooltip title="刷新">
              <Button
                aria-label="刷新应用列表"
                icon={<ReloadOutlined />}
                onClick={() => void appsQuery.refetch()}
              />
            </Tooltip>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              disabled={!canManage}
              onClick={openCreate}
            >
              新建应用
            </Button>
          </div>
        </div>
        <div className="if-apps-body tp-list-body">
          <div className="if-list-scroll tp-list-scroll">
            <Table
              rowKey="appId"
              size="middle"
              loading={appsQuery.isLoading}
              columns={columns}
              dataSource={filteredApps}
              pagination={false}
              className="if-interface-table"
              onRow={app => ({
                onClick: () => openAppInterfaces(app),
              })}
              locale={{
                emptyText: appsQuery.isLoading ? (
                  <Spin />
                ) : (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={keyword ? '没有匹配的应用' : '还没有接口应用'}
                  />
                ),
              }}
            />
          </div>
        </div>
      </section>
      <ApiAppEditorDrawer
        open={editorOpen}
        projectId={projectId}
        app={editingApp}
        onClose={closeEditor}
        onSaved={() => {
          closeEditor()
          setKeyword('')
          setSearchResetKey(value => value + 1)
        }}
      />
    </div>
  )
}
