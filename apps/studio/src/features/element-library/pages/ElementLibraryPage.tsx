import {
  AppstoreOutlined, CloseOutlined, CodeOutlined, FileOutlined, SearchOutlined, UnorderedListOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Drawer, Form, Grid, Input, Modal, Popconfirm, Select, Table } from 'antd'
import type { TableProps } from 'antd'
import { Link, useSearchParams } from 'react-router-dom'
import { useProjectAccessContext } from '@/domain/projects/hooks/projectAccessContext'
import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { listItems, listTotal } from '@/shared/api/request'
import { ActionButton } from '@/shared/components/ActionButton'
import { DebouncedSearchInput } from '@/shared/components/DebouncedSearchInput'
import { ListEmptyState } from '@/shared/components/ListEmptyState'
import { ListPagination } from '@/shared/components/ListPagination'
import { ListSurface } from '@/shared/components/ListSurface'
import { usePaneActive } from '@/shared/ui/paneActivity'
import { getErrorMessage } from '@/utils/format'
import '@/shared/styles/surface-tokens.css'
import '@/shared/styles/list-table.css'
import { all, common, useElementWorkspace } from '../hooks/useElementWorkspace'
import { ElementDetails, VerificationBadge } from '../components/ElementDetails'
import { ElementEditorDrawer } from '../components/ElementEditorDrawer'
import styles from '../styles/element-library.module.css'
import type { ElementSummary } from '../types'

const pageClass = `workbench-page tp-surface tp-list-surface ${styles.page}`
const statuses = [
  { value: 'all', label: '全部状态' },
  { value: 'verified', label: '已验证' },
  { value: 'pending', label: '待验证' },
]

export function ElementLibraryPage() {
  const projectId = useWorkbenchStore(state => state.activeProjectId) ?? ''
  const canWrite = useProjectAccessContext(projectId)?.can('write') ?? false
  const paneActive = usePaneActive()
  const [params, setParams] = useSearchParams()
  const repositories = useQuery({
    queryKey: ['softwareRepositories', projectId],
    queryFn: () => interfaceLibraryApi.getSoftwareRepositories(projectId),
    enabled: Boolean(projectId) && paneActive,
  })
  if (!paneActive) return null

  const options = listItems(repositories.data).map(repository => ({ value: repository.softwareRepositoryId, label: repository.name }))
  const active = options.find(option => option.value === params.get('softwareRepositoryId')) ?? options[0]
  if (active) {
    return <ElementWorkspace key={projectId + ':' + active.value} repositoryId={active.value} canWrite={canWrite}
      repositoryPicker={<Select aria-label="前端应用" className="w-[160px] max-w-full" value={active.value}
        options={options} onChange={value => setParams(previous => {
          const next = new URLSearchParams(previous)
          next.set('softwareRepositoryId', value)
          return next
        }, { replace: true })} />} />
  }
  const message = !projectId ? '请先在顶部选择一个项目'
    : repositories.isPending ? '正在加载软件仓库'
    : repositories.isError ? '软件仓库加载失败'
    : '当前项目还没有软件仓库'
  return <div className={pageClass}>
    <ListSurface toolbar={<div className="tp-list-toolbar"><h1 className="tp-list-title">元素库</h1></div>}>
      <ListEmptyState description={message}>
        {repositories.isError && <Button onClick={() => void repositories.refetch()}>重试</Button>}
        {projectId && repositories.isSuccess && <Link to="/asset-library?tab=repositories">前往软件仓库</Link>}
      </ListEmptyState>
    </ListSurface>
  </div>
}

function ElementWorkspace({ repositoryId, repositoryPicker, canWrite }: {
  repositoryId: string
  repositoryPicker: React.ReactNode
  canWrite: boolean
}) {
  const {
    activeGroup, clearFilters, createGroup, current, deleteElement, deleteGroup, detail,
    editor, entries, group, groupModal, groups, groupsQuery, keyword, list, listEnabled,
    openEditor, page, pageGroups, pageSize, refresh, saveElement, searchReset, selectGroup,
    selected, setEditor, setGroupModal, setKeyword, setPage, setPageSize, setSelected, setStatus, status,
  } = useElementWorkspace(repositoryId)
  const compact = !(Grid.useBreakpoint().lg ?? matchMedia('(min-width: 992px)').matches)
  const columns: TableProps<ElementSummary>['columns'] = [
    {
      title: '元素名称', key: 'name', width: compact ? '44%' : '34%',
      render: (_, item) => <button type="button" className={styles.name} title={item.name}
        aria-pressed={selected === item.elementId} onClick={() => setSelected(item.elementId)}>
        {item.parameterized ? <CodeOutlined aria-hidden="true" /> : <AppstoreOutlined aria-hidden="true" />}<span>{item.name}</span>
      </button>,
    },
    ...(compact ? [] : [{
      title: group === all.key ? '分组 / 作用范围' : '作用范围', key: 'scope',
      render: (_: unknown, item: ElementSummary) => <span className="[overflow-wrap:anywhere]">
        {group === all.key && <span className="text-[var(--srf-text-secondary)]">
          {groups.find(candidate => candidate.groupId === item.groupId)?.name} · </span>}
        {item.scope}
      </span>,
    }]),
    { title: '定位', key: 'locator', width: compact ? '25%' : 110, render: (_, item) => item.parameterized ? '参数模板' : item.locatorType },
    { title: '验证状态', key: 'state', width: compact ? '31%' : 110, render: (_, item) => <VerificationBadge status={item.verificationStatus} /> },
  ]

  const inspector = detail.data ? <ElementDetails
    key={detail.data.elementId + ':' + detail.data.version} item={detail.data}
    groupName={groups.find(item => item.groupId === detail.data?.groupId)?.name ?? ''}
    canWrite={canWrite} deleting={deleteElement.isPending} onEdit={() => openEditor(detail.data)}
    onDelete={() => { if (detail.data) deleteElement.mutate(detail.data) }} />
    : detail.isError ? <Alert type="error" showIcon title={getErrorMessage(detail.error)}
      action={<Button onClick={() => void detail.refetch()}>重试</Button>} />
    : <ListEmptyState description="正在加载元素详情" />
  const writeOptions = [{ value: common.key, label: common.name }, ...pageGroups.map(item => ({ value: item.groupId, label: item.name }))]

  return <div className={pageClass}>
    <ListSurface ariaLabelledBy="element-library-title"
      toolbar={<div className="tp-list-toolbar flex flex-wrap items-center gap-2">
        <h1 id="element-library-title" className="tp-list-title">元素库</h1>
        {repositoryPicker}
        <DebouncedSearchInput ariaLabel="搜索元素" placeholder="搜索元素、范围或定位" className={styles.search}
          prefix={<SearchOutlined />} resetKey={searchReset} onCommit={value => {
            if (value === keyword) return
            setKeyword(value)
            setPage(1)
            setSelected('')
          }} />
        {canWrite && <div className={styles.toolbarActions}>
          <ActionButton operation="create" disabled={groupsQuery.isError} onClick={() => { createGroup.reset(); setGroupModal(true) }}>新建页面分组</ActionButton>
          <ActionButton operation="create" type="primary" className="action-btn-create" disabled={!groupsQuery.isSuccess}
            onClick={() => openEditor()}>新建元素</ActionButton>
        </div>}
      </div>}
      footer={<ListPagination total={listEnabled ? listTotal(list.data) : 0} current={page} pageSize={pageSize}
        loading={listEnabled && list.isPending} onChange={(next, size) => {
          setPage(next)
          setPageSize(size)
          setSelected('')
        }} />}>
      <div className={`${styles.layout} ${selected && !compact ? styles.withDetail : ''}`}>
        <nav className={styles.directory} aria-label="页面分组">
          {entries.map((item, index) => {
            const Icon = item.key === all.key ? UnorderedListOutlined : item.key === common.key ? AppstoreOutlined : FileOutlined
            return <div key={item.key} className={index === 2 ? 'mt-4' : undefined}>
              {(index === 0 || index === 2) && <h2 className={styles.groupHeading}>{index === 0 ? '分组' : '页面'}</h2>}
              <button type="button" className={styles.group} aria-pressed={group === item.key} onClick={() => selectGroup(item.key)}>
                <Icon aria-hidden="true" className={styles.groupIcon} /><span className="min-w-0">
                  <span className="block truncate">{item.name}</span>{item.route && <code className={styles.route}>{item.route}</code>}
                </span><span className={styles.count}>{item.count}</span>
              </button>
            </div>
          })}
        </nav>
        <div className={styles.mobileDirectory}>
          <Select aria-label="页面分组" className="w-full" value={group} onChange={selectGroup}
            options={entries.map(item => ({ value: item.key, label: item.route ? item.name + ' · ' + item.route : item.name }))} />
        </div>
        <section className="min-w-0" aria-label="元素列表">
          <div className={styles.listHeader}>
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h2 className="m-0 break-words text-sm font-semibold">{current.name}</h2>
              {current.route && <code className="tp-chip [overflow-wrap:anywhere]">{current.route}</code>}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Select aria-label="验证状态" value={status} options={statuses} className="w-26" onChange={value => {
                setStatus(value)
                setPage(1)
                setSelected('')
              }} />
              {canWrite && activeGroup && <Popconfirm title="删除该空分组？" okButtonProps={{ danger: true, loading: deleteGroup.isPending }}
                onConfirm={() => deleteGroup.mutate(activeGroup.groupId)}>
                <ActionButton operation="delete" iconOnly aria-label="删除分组" disabled={activeGroup.elementCount > 0} />
              </Popconfirm>}
            </div>
          </div>
          {groupsQuery.isError || (listEnabled && list.isError)
            ? <Alert type="error" showIcon title="元素库加载失败" action={<Button onClick={() => void refresh()}>重试</Button>} />
            : <Table rowKey="elementId" className="tp-list-table" columns={columns} tableLayout="fixed" pagination={false}
              loading={groupsQuery.isPending || (listEnabled && list.isPending)}
              dataSource={listEnabled ? listItems(list.data) : []} rowClassName={item => item.elementId === selected ? styles.selectedRow : ''}
              locale={{ emptyText: <ListEmptyState description={keyword || status !== 'all' ? '没有匹配的元素' : '这个分组还没有元素'}>
                {keyword || status !== 'all' ? <Button onClick={clearFilters}>清除筛选</Button>
                  : canWrite && !groupsQuery.isPending && <Button onClick={() => openEditor()}>新建元素</Button>}
              </ListEmptyState> }} />}
        </section>
        {selected && !compact && <aside className={styles.detail} aria-label="元素详情">
          <div className={styles.detailHeader}><h2 className="m-0 text-sm font-semibold">元素详情</h2>
            <Button type="text" icon={<CloseOutlined />} aria-label="关闭元素详情" onClick={() => setSelected('')} />
          </div>
          {inspector}
        </aside>}
      </div>
    </ListSurface>
    <Drawer title="元素详情" rootClassName="tp-surface" open={Boolean(selected && compact)} size="min(420px, 100vw)" onClose={() => setSelected('')}>
      {selected && compact && inspector}
    </Drawer>
    {editor && <ElementEditorDrawer editor={editor === 'new' ? null : editor} groups={writeOptions}
      defaultGroup={editor === 'new' ? activeGroup?.kind === 'page' ? activeGroup.groupId : common.key
        : pageGroups.find(item => item.groupId === editor.groupId)?.groupId ?? common.key}
      saving={saveElement.isPending} error={saveElement.error ? getErrorMessage(saveElement.error) : ''}
      onClose={() => setEditor(null)} onSave={draft => saveElement.mutate(draft)} />}
    <Modal title="新建页面分组" open={groupModal} destroyOnHidden footer={null}
      closable={!createGroup.isPending} keyboard={!createGroup.isPending} mask={{ closable: !createGroup.isPending }} onCancel={() => setGroupModal(false)}>
      {createGroup.isError && <Alert className="mb-3" type="error" showIcon title={getErrorMessage(createGroup.error)} />}
      <Form layout="vertical" preserve={false} onFinish={values => createGroup.mutate(values)}>
        <Form.Item name="name" label="分组名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={120} /></Form.Item>
        <Form.Item name="routeTemplate" label="路由模板" rules={[{ required: true, whitespace: true }]}>
          <Input placeholder="例如 /orders/:id" maxLength={512} />
        </Form.Item>
        <div className="flex justify-end gap-2">
          <Button disabled={createGroup.isPending} onClick={() => setGroupModal(false)}>取消</Button>
          <Button htmlType="submit" type="primary" loading={createGroup.isPending}>创建分组</Button>
        </div>
      </Form>
    </Modal>
  </div>
}
