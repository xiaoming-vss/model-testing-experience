import { ListPagination } from '@/shared/components/ListPagination'
import '@/shared/styles/list-table.css'
import '@/shared/styles/surface-tokens.css'
import '../styles/bugs-v2.css'
import { Alert, Empty, Table } from 'antd'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { getErrorMessage } from '@/utils/format'
import { BugFormModal } from '../components/BugFormModal'
import { BugZentaoImportModal } from '../components/BugZentaoImportModal'
import { BugTransitionModal } from '../components/BugTransitionModal'
import { BugListToolbar } from '../components/BugListToolbar'
import { useBugList } from '../hooks/useBugList'
import type { Bug } from '../types'

export function BugListPage() {
  const model = useBugList()
  const { navigate, activeProjectId, activeSprintId, total, bugsQuery, bugs,
    columns, page, pageSize, setPage, setPageSize, transition, setTransition,
    createOpen, setCreateOpen, importOpen, setImportOpen } = model
  return (
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface bugs-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board tp-list-panel">
          <BugListToolbar model={model} />

          {bugsQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(bugsQuery.error)} action={<ProjectActionButton action="bug_read" onClick={() => bugsQuery.refetch()}>重试</ProjectActionButton>} />
          ) : null}

          {!activeProjectId ? (
            <div className="sprint-card-loading">
              <Empty description="请先选择项目" />
            </div>
          ) : (
            <div className="bugs-table-card tp-list-body">
              <div className="table-body-scroll bugs-table-scroll tp-list-scroll">
                {bugsQuery.isLoading ? (
                  <div className="sprint-card-loading">
                    <Empty description="Bug 列表加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  </div>
                ) : bugs.length === 0 ? (
                  <div className="sprint-card-loading">
                    <Empty description="当前筛选范围内还没有 Bug" />
                  </div>
                ) : (
                  <Table<Bug>
                    className="functional-suite-list-table tp-list-table"
                    columns={columns}
                    dataSource={bugs}
                    rowKey={(bug) => bug.bugId}
                    pagination={false}
                    scroll={{ x: 1520 }}
                    onRow={(bug) => ({
                      onClick: (event) => {
                        if ((event.target as HTMLElement).closest('.bug-row-actions')) return
                        navigate(`/bugs/${bug.bugId}`)
                      },
                    })}
                  />
                )}
              </div>
              <div className="table-footer bugs-footer">
                <ListPagination loading={bugsQuery.isFetching || bugsQuery.isError} current={page} pageSize={pageSize} total={total}
                  onChange={(nextPage, nextSize) => { setPage(nextPage); setPageSize(nextSize) }} />
              </div>
            </div>
          )}
        </section>
      </div>

      <BugTransitionModal bug={transition?.bug ?? null} action={transition?.action ?? null}
        onClose={() => setTransition(null)} />
      <BugFormModal
        open={createOpen}
        projectId={activeProjectId}
        defaultSprintId={activeSprintId}
        onClose={() => setCreateOpen(false)}
        onSaved={(saved) => { setCreateOpen(false); navigate(`/bugs/${saved.bugId}`) }}
      />
      {activeProjectId && (
        <BugZentaoImportModal
          open={importOpen}
          projectId={activeProjectId}
          defaultSprintId={activeSprintId}
          onClose={() => { setImportOpen(false); void bugsQuery.refetch() }}
        />
      )}
    </div>
  )
}
