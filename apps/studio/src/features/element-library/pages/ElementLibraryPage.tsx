import { SearchOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Form, Input, Modal, Select, Drawer } from 'antd'
import { Link, useSearchParams } from 'react-router-dom'
import { useProjectAccessContext } from '@/domain/projects/hooks/projectAccessContext'
import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { listItems } from '@/shared/api/request'
import { ActionButton } from '@/shared/components/ActionButton'
import { DebouncedSearchInput } from '@/shared/components/DebouncedSearchInput'
import { ListEmptyState } from '@/shared/components/ListEmptyState'
import { ListSurface } from '@/shared/components/ListSurface'
import { usePaneActive } from '@/shared/ui/paneActivity'
import { getErrorMessage } from '@/utils/format'
import '@/shared/styles/surface-tokens.css'
import '@/shared/styles/list-table.css'
import { common, useElementWorkspace } from '../hooks/useElementWorkspace'
import { ElementDetails } from '../components/ElementDetails'
import { ElementEditorDrawer } from '../components/ElementEditorDrawer'
import { ElementGroupSidebar } from '../components/ElementGroupSidebar'
import { ElementListCard } from '../components/ElementListCard'
import {
  elementBoardClass,
  elementLayoutClass,
  elementPageClass,
  elementToolbarActionsClass,
  elementToolbarGroupClass,
} from '../components/elementLibraryClasses'

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
  return <div className={elementPageClass}>
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
  const page = useElementWorkspace(repositoryId)
  const {
    activeGroup, createGroup, detail, editor, groupModal, groupsQuery, keyword, list, openEditor,
    pageGroups, refresh, saveElement, searchReset, selected, setEditor, setGroupModal, setKeyword,
    setPage, setSelected,
  } = page
  const refreshPending = list.isFetching || groupsQuery.isFetching

  const inspector = detail.data ? <ElementDetails
    key={detail.data.elementId + ':' + detail.data.version} item={detail.data}
    groupName={page.groups.find(item => item.groupId === detail.data?.groupId)?.name ?? ''}
    canWrite={canWrite} deleting={page.deleteElement.isPending} onEdit={() => openEditor(detail.data)}
    onDelete={() => { if (detail.data) page.deleteElement.mutate(detail.data) }} />
    : detail.isError ? <Alert type="error" showIcon title={getErrorMessage(detail.error)}
      action={<Button onClick={() => void detail.refetch()}>重试</Button>} />
    : <ListEmptyState description="正在加载元素详情" />
  const writeOptions = [{ value: common.key, label: common.name }, ...pageGroups.map(item => ({ value: item.groupId, label: item.name }))]

  return <div className={elementPageClass}>
    <section className={elementBoardClass} aria-labelledby="element-library-title">
      <div className="tp-list-toolbar flex flex-wrap items-center gap-2">
        <div className={elementToolbarGroupClass}>
          <h1 id="element-library-title" className="tp-list-title">元素库</h1>
          {repositoryPicker}
          <DebouncedSearchInput ariaLabel="搜索元素" placeholder="搜索元素、范围或定位" className="w-72 max-w-full"
            prefix={<SearchOutlined />} resetKey={searchReset} onCommit={value => {
              if (value === keyword) return
              setKeyword(value)
              setPage(1)
              setSelected('')
            }} />
        </div>
        <div className={elementToolbarActionsClass}>
          <ActionButton operation="refresh" iconOnly aria-label="刷新元素列表" loading={refreshPending}
            onClick={() => void refresh()} />
          {canWrite && <ActionButton operation="create" type="primary" className="action-btn-create"
            disabled={!groupsQuery.isSuccess} onClick={() => openEditor()}>新建元素</ActionButton>}
        </div>
      </div>

      <div className={elementLayoutClass}>
        <ElementGroupSidebar page={page} canWrite={canWrite} />
        <ElementListCard page={page} canWrite={canWrite} />
      </div>
    </section>

    <Drawer title="元素详情" rootClassName="tp-surface" open={Boolean(selected)} size="min(440px, 100vw)"
      onClose={() => setSelected('')}>
      {selected ? inspector : null}
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
