import {
  AppstoreOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import { Alert, Empty, Popconfirm, Tooltip } from 'antd'
import { ListEmptyState } from '@/shared/components/ListEmptyState'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { getErrorMessage, normalizeFunctionTestSuiteId } from '@/utils/format'
import { suiteCaseCount, type CaseLibraryPageModel } from '../hooks/useCaseLibraryPage'

export function CaseLibrarySidebar({ page }: { page: CaseLibraryPageModel }) {
  const {
    suiteId,
    setSuiteId,
    setPage,
    suitesQuery,
    suites,
    hasSuiteData,
    allCaseCount,
  } = page

  return (
    <aside className="api-case-sidebar case-library-tree flex min-h-0 flex-col overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-[0_1px_2px_var(--srf-shadow-color)]">
      <div className="case-library-tree-head flex flex-none items-center justify-between gap-2 border-b border-[var(--srf-divider)] p-3">
        <span className="case-library-tree-title inline-flex items-center gap-1.5 text-[12px] font-bold leading-[18px] text-[var(--srf-text)]">
          <FolderOpenOutlined />
          测试集导航
        </span>
      </div>
      <div className="api-case-sidebar-scroll case-library-tree-scroll min-h-0 flex-1 overflow-auto px-3 pt-2.5 pb-3 max-[1180.01px]:max-h-[420px]">
        <div className="api-case-nav-list case-library-nav-list flex flex-col gap-0.5">
          <button
            type="button"
            className={`api-case-nav-item case-library-nav-item group flex w-full cursor-pointer appearance-none items-center justify-between gap-2 rounded-[var(--srf-radius-control)] border border-transparent px-2.5 py-1.5 text-left font-[inherit] text-inherit transition-colors hover:bg-[var(--srf-hover)] ${suiteId ? 'bg-transparent' : 'bg-[var(--srf-accent-soft)]'}`}
            aria-current={!suiteId}
            onClick={() => {
              setSuiteId(null)
              setPage(1)
            }}
          >
            <span className="case-library-nav-main flex min-w-0 items-center gap-2">
              <AppstoreOutlined className={`case-library-tree-icon flex-none text-[16px] ${suiteId ? 'text-[var(--srf-folder)]' : 'text-[var(--srf-accent)]'}`} />
              <span className={`case-library-nav-name min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] leading-[18px] ${suiteId ? 'font-medium text-[var(--srf-text-secondary)] group-hover:text-[var(--srf-text)]' : 'font-semibold text-[var(--srf-accent-strong)]'}`}>全部用例</span>
            </span>
            <span className={`case-library-nav-count flex-none rounded-[4px] px-1.5 py-0.5 font-mono text-[11px] leading-[14px] ${suiteId ? 'text-[var(--srf-text-muted)]' : 'bg-[var(--srf-count-badge)] text-[var(--srf-accent-strong)]'}`}>{hasSuiteData ? allCaseCount : '—'}</span>
          </button>
          {suitesQuery.error ? (
            <Alert showIcon type="error" title="测试集加载失败"
              description={getErrorMessage(suitesQuery.error)}
              action={<ProjectActionButton action="read" loading={suitesQuery.isFetching}
                onClick={() => suitesQuery.refetch()}>重试测试集</ProjectActionButton>} />
          ) : null}
          {suitesQuery.isLoading ? (
            <ListEmptyState className="max-[1180.01px]:min-h-24" description="测试集加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : suitesQuery.error && suites.length === 0 ? null : suites.length === 0 ? (
            <ListEmptyState className="max-[1180.01px]:min-h-24" description="当前范围暂无测试集" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            suites.map((suite) => {
              const id = normalizeFunctionTestSuiteId(suite)
              const active = Boolean(id) && id === suiteId
              return (
                <button
                  key={id ?? suite.name}
                  type="button"
                  className={`api-case-nav-item case-library-nav-item group flex w-full cursor-pointer appearance-none items-center justify-between gap-2 rounded-[var(--srf-radius-control)] border border-transparent px-2.5 py-1.5 text-left font-[inherit] text-inherit transition-colors hover:bg-[var(--srf-hover)] ${active ? 'bg-[var(--srf-accent-soft)]' : 'bg-transparent'}`}
                  aria-current={active}
                  onClick={() => {
                    setSuiteId(id ?? null)
                    setPage(1)
                  }}
                >
                  <span className="case-library-nav-main flex min-w-0 items-center gap-2">
                    {active ? (
                      <FolderOpenOutlined className="case-library-tree-icon flex-none text-[16px] text-[var(--srf-accent)]" />
                    ) : (
                      <FolderOutlined className="case-library-tree-icon flex-none text-[16px] text-[var(--srf-folder)]" />
                    )}
                    <span className={`case-library-nav-name min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] leading-[18px] ${active ? 'font-semibold text-[var(--srf-accent-strong)]' : 'font-medium text-[var(--srf-text-secondary)] group-hover:text-[var(--srf-text)]'}`}>{suite.name}</span>
                  </span>
                  <span className={`case-library-nav-count flex-none rounded-[4px] px-1.5 py-0.5 font-mono text-[11px] leading-[14px] ${active ? 'bg-[var(--srf-count-badge)] text-[var(--srf-accent-strong)]' : 'text-[var(--srf-text-muted)]'}`}>{suiteCaseCount(suite)}</span>
                </button>
              )
            })
          )}
        </div>
      </div>
      {/* 三个动作排一行：新建常驻且带文字，编辑 / 删除要靠选中测试集，收成图标按钮。 */}
      <SuiteSidebarFooter page={page} />
    </aside>
  )
}

function SuiteSidebarFooter({ page }: { page: CaseLibraryPageModel }) {
  const {
    activeProjectId,
    sprints,
    selectedSuite,
    openCreateSuiteDrawer,
    openEditSuiteDrawer,
    deleteSuiteMutation,
  } = page

  return (
    <div className="case-library-sidebar-foot flex flex-none items-center gap-2 border-t border-[var(--srf-divider)] bg-[var(--srf-hover)] px-3 py-2.5">
      <Tooltip title="新建测试集">
        <ProjectActionButton
          action="write"
          type="text"
          className="action-btn-create case-library-foot-create mr-auto flex-none px-0 text-xs"
          operation="create"
          icon={<PlusOutlined />}
          disabled={!activeProjectId || sprints.length === 0}
          onClick={openCreateSuiteDrawer}
        >
          新建测试集
        </ProjectActionButton>
      </Tooltip>
      <Tooltip title={selectedSuite ? '编辑测试集' : '编辑按测试集执行，请先选中一个测试集'}>
        <ProjectActionButton
          action="write"
          type="text"
          shape="circle"
          className="action-btn-update"
          operation="edit"
          iconOnly
          aria-label="编辑测试集"
          disabled={!selectedSuite}
          onClick={() => selectedSuite && openEditSuiteDrawer(selectedSuite)}
        />
      </Tooltip>
      <Popconfirm
        title="确认删除该功能测试集？"
        description="测试集下若还有用例需先删除用例，删除后不可恢复。"
        okText="确认删除"
        okButtonProps={{ danger: true }}
        disabled={!selectedSuite}
        onConfirm={() =>
          selectedSuite?.suiteId && deleteSuiteMutation.mutate(selectedSuite.suiteId)
        }
      >
        <Tooltip title={selectedSuite ? '删除测试集' : '删除按测试集执行，请先选中一个测试集'}>
          <ProjectActionButton
            action="write"
            type="text"
            shape="circle"
            className="action-btn-delete"
            operation="delete"
            iconOnly
            aria-label="删除测试集"
            disabled={!selectedSuite}
            loading={deleteSuiteMutation.isPending}
          />
        </Tooltip>
      </Popconfirm>
    </div>
  )
}
