import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { Button, Empty, Spin, Table, Tooltip } from 'antd'
import type { TableProps } from 'antd'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { DebouncedSearchInput } from '@/shared/components/DebouncedSearchInput'
import { formatTime } from '@/utils/format'
import { SoftwareRepositoryEditorDrawer } from '../components/SoftwareRepositoryEditorDrawer'
import { useSoftwareRepositoryManager } from '../hooks/useSoftwareRepositoryManager'
import type { SoftwareRepository } from '../types'
import '@/shared/styles/surface-tokens.css'
import '../styles/index.css'

/** 项目级软件仓库管理；接口库左侧软件仓库树提供同一批仓库的快捷入口。 */
export function SoftwareRepositoriesPage() {
  const navigate = useNavigate()
  const projectId = useWorkbenchStore(state => state.activeProjectId) ?? ''
  const { can } = useProjectAccess(projectId)
  const canManage = can('manage')
  const {
    repositories,
    repositoriesQuery,
    editorOpen,
    editingRepository,
    openCreate,
    openEdit,
    closeEditor,
    deleteRepository,
  } = useSoftwareRepositoryManager(projectId)
  const [keyword, setKeyword] = useState('')
  const [searchResetKey, setSearchResetKey] = useState(0)

  const filteredRepositories = useMemo(() => {
    const search = keyword.trim().toLowerCase()
    if (!search) return repositories
    return repositories.filter(
      repository =>
        repository.name.toLowerCase().includes(search) ||
        repository.basePath.toLowerCase().includes(search) ||
        (repository.repository?.path ?? '').toLowerCase().includes(search),
    )
  }, [repositories, keyword])

  function openRepositoryInterfaces(repository: SoftwareRepository) {
    navigate(
      `/asset-library?tab=interfaces&softwareRepositoryId=${encodeURIComponent(repository.softwareRepositoryId)}`,
    )
  }

  const columns: TableProps<SoftwareRepository>['columns'] = [
    {
      title: '软件仓库',
      key: 'name',
      width: 300,
      render: (_, repository) => (
        <div className="if-app-name-cell">
          <button
            type="button"
            className="if-name-link"
            onClick={event => {
              event.stopPropagation()
              openRepositoryInterfaces(repository)
            }}
          >
            {repository.name}
          </button>
        </div>
      ),
    },
    {
      title: '代码仓库',
      key: 'repository',
      render: (_, repository) => (
        <span className="if-path">{repository.repository?.path || '—'}</span>
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
      width: 100,
      render: (_, repository) => <span>{repository.interfaceCount}</span>,
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
      width: 100,
      align: 'right',
      render: (_, repository) =>
        canManage ? (
          <div className="if-row-actions" onClick={event => event.stopPropagation()}>
            <Tooltip title="编辑">
              <Button
                type="text"
                size="small"
                aria-label={`编辑${repository.name}`}
                icon={<EditOutlined />}
                onClick={() => openEdit(repository)}
              />
            </Tooltip>
            <Tooltip
              title={
                repository.interfaceCount > 0
                  ? '先删除该软件仓库下的接口'
                  : '删除软件仓库'
              }
            >
              <Button
                type="text"
                size="small"
                danger
                disabled={repository.interfaceCount > 0}
                aria-label={`删除${repository.name}`}
                icon={<DeleteOutlined />}
                onClick={() => deleteRepository(repository)}
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
            <h1 className="tp-list-title">软件仓库</h1>
            <span className="if-app-tree-total">{repositories.length}</span>
            <DebouncedSearchInput
              ariaLabel="搜索软件仓库"
              placeholder="搜索软件仓库名称 / 仓库 / base path"
              className="if-search-input"
              prefix={<SearchOutlined />}
              resetKey={searchResetKey}
              onCommit={setKeyword}
            />
          </div>
          <div className="if-toolbar-actions">
            <Tooltip title="刷新">
              <Button
                aria-label="刷新软件仓库列表"
                icon={<ReloadOutlined />}
                onClick={() => void repositoriesQuery.refetch()}
              />
            </Tooltip>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              disabled={!canManage}
              onClick={openCreate}
            >
              新建软件仓库
            </Button>
          </div>
        </div>
        <div className="if-apps-body tp-list-body">
          <div className="if-list-scroll tp-list-scroll">
            <Table
              rowKey="softwareRepositoryId"
              size="middle"
              loading={repositoriesQuery.isLoading}
              columns={columns}
              dataSource={filteredRepositories}
              pagination={false}
              className="if-interface-table"
              onRow={repository => ({
                onClick: () => openRepositoryInterfaces(repository),
              })}
              locale={{
                emptyText: repositoriesQuery.isLoading ? (
                  <Spin />
                ) : (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={keyword ? '没有匹配的软件仓库' : '还没有软件仓库'}
                  />
                ),
              }}
            />
          </div>
        </div>
      </section>
      <SoftwareRepositoryEditorDrawer
        open={editorOpen}
        projectId={projectId}
        repository={editingRepository}
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
