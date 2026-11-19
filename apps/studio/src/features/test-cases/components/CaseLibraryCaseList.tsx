import { AppstoreOutlined } from '@ant-design/icons'
import { Alert, Empty, Space, Table, Typography } from 'antd'
import { ListEmptyState } from '@/shared/components/ListEmptyState'
import { ListPagination } from '@/shared/components/ListPagination'
import { tableFooterClass, tableScrollClass } from '@/shared/utils/surfaceClasses'
import { getErrorMessage, normalizeFunctionTestCaseId } from '@/utils/format'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import type { FunctionCaseLibraryItem } from '@/services/api'
import type { CaseLibraryPageModel } from '../hooks/useCaseLibraryPage'
import { useCaseLibraryColumns } from './caseLibraryColumns'

const { Text } = Typography

/** 快速过滤条上的优先级档位，顺序即展示顺序（P0 在最前）。 */
const PRIORITY_QUICK_FILTERS = ['P0', 'P1', 'P2', 'P3']

export function CaseLibraryCaseList({ page }: { page: CaseLibraryPageModel }) {
  const {
    selectedCaseIds,
    setSelectedCaseIds,
    selectedSuite,
    hasCaseData,
    total,
    casesQuery,
    cases,
    hasCaseFilters,
    noSuites,
    canCreateCase,
    openCreateSuiteDrawer,
    openCreateCase,
    page: currentPage,
    pageSize,
    setPage,
    setPageSize,
    openEditCase,
  } = page
  const columns = useCaseLibraryColumns(page)

  return (
    <div className="case-library-main flex min-h-0 flex-col rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-[0_1px_2px_var(--srf-shadow-color)]">
      <CaseLibraryQuickBar page={page} />
      <div className={`table-body-scroll flex flex-auto min-h-0 flex-col p-4 case-library-table-scroll ${tableScrollClass}`}>
        {casesQuery.error ? (
          <Alert showIcon type="error" title="用例加载失败"
            description={getErrorMessage(casesQuery.error)}
            action={<ProjectActionButton action="read" loading={casesQuery.isFetching}
              onClick={() => casesQuery.refetch()}>重试用例</ProjectActionButton>} />
        ) : null}
        {casesQuery.isLoading ? (
          <ListEmptyState description="用例加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : casesQuery.isError && cases.length === 0 ? null : cases.length === 0 ? (
          <ListEmptyState
            image={<AppstoreOutlined />}
            description={
              <Space orientation="vertical" size={4}>
                <Text strong>
                  {hasCaseFilters ? '没有符合筛选条件的用例' : noSuites ? '当前范围暂无测试集' : selectedSuite ? '这个测试集还没有用例' : '当前范围暂无用例'}
                </Text>
                <Text type="secondary">
                  {hasCaseFilters
                    ? '清除用例类型、优先级和名称筛选；保留当前迭代、需求和测试集范围。'
                    : noSuites
                      ? '先创建测试集，再添加或导入用例。'
                      : selectedSuite
                        ? '可以直接新建用例，也可以用例导入或 AI 生成后导入。'
                        : '在左栏选择测试集后添加用例，或调整需求与当前迭代范围。'}
                </Text>
              </Space>
            }
          >
            {hasCaseFilters ? null : noSuites ? (
              <ProjectActionButton action="write" type="primary" operation="create"
                className="action-btn-create" onClick={openCreateSuiteDrawer}>新建测试集</ProjectActionButton>
            ) : !canCreateCase ? null : (
              <ProjectActionButton
                action="write"
                type="primary"
                className="action-btn-create"
                operation="create"
                onClick={openCreateCase}
              >
                新建用例
              </ProjectActionButton>
            )}
          </ListEmptyState>
        ) : (
          <Table<FunctionCaseLibraryItem>
            className="functional-suite-list-table tp-list-table"
            scroll={{ x: 1200 }}
            columns={columns}
            dataSource={cases}
            rowKey={(item) => normalizeFunctionTestCaseId(item) ?? item.title}
            rowSelection={{
              preserveSelectedRowKeys: true,
              selectedRowKeys: selectedCaseIds,
              onChange: (keys) => setSelectedCaseIds(keys.map(String)),
              getCheckboxProps: (item) => ({
                disabled: !normalizeFunctionTestCaseId(item),
                'aria-label': `选择用例：${item.title}`,
              }),
            }}
            pagination={false}
            onRow={(item) => ({
              onClick: (event) => {
                if ((event.target as HTMLElement).closest('.ant-table-selection-column'))
                  return
                openEditCase(item)
              },
            })}
          />
        )}
      </div>

      <div className={`table-footer case-library-footer ${tableFooterClass}`}>
        {!hasCaseData ? <Text type="secondary">{casesQuery.isError ? '用例数量暂不可用' : '正在加载用例…'}</Text> : (
          <ListPagination loading={casesQuery.isFetching || casesQuery.isError}
            current={currentPage}
            pageSize={pageSize}
            total={total}
            onChange={(nextPage, nextPageSize) => {
              setPageSize(nextPageSize)
              setPage(nextPageSize === pageSize ? nextPage : 1)
            }}
          />
        )}
      </div>
    </div>
  )
}

function CaseLibraryQuickBar({ page }: { page: CaseLibraryPageModel }) {
  const {
    priority,
    setPriority,
    setPage,
    selectedCaseIds,
    setSelectedCaseIds,
    selectedSuite,
    hasCaseData,
    total,
    casesQuery,
    hasCaseFilters,
    clearCaseFilters,
  } = page

  return (
    // 优先级不进筛选下拉：档位只有四档，摊平成一排比藏在二级菜单里快。
    <div className="tp-quickbar case-library-quickbar flex flex-none flex-wrap items-center justify-between gap-2 border-b border-[var(--srf-divider)] px-4 py-2.5">
      <div className="tp-quick-filters flex flex-wrap items-center gap-2">
        <span className="tp-quick-label text-[12px] text-[var(--srf-text-secondary)]">快速过滤:</span>
        <button
          type="button"
          className={`tp-chip${priority ? '' : ' active'}`}
          aria-pressed={!priority}
          onClick={() => {
            setPriority(null)
            setPage(1)
          }}
        >
          全部
        </button>
        {PRIORITY_QUICK_FILTERS.map((level) => (
          <button
            key={level}
            type="button"
            className={`tp-chip case-library-chip-priority font-mono${priority === level ? ' active' : ''}`}
            aria-pressed={priority === level}
            onClick={() => {
              setPriority(priority === level ? null : level)
              setPage(1)
            }}
          >
            {level}
          </button>
        ))}
      </div>
      <div className="tp-selection case-library-selection flex min-w-0 flex-wrap items-center justify-end gap-x-2 gap-y-1 whitespace-normal text-[12px] text-[var(--srf-text-muted)] [&_strong]:font-semibold [&_strong]:text-[var(--srf-text-secondary)]" aria-live="polite">
        {selectedCaseIds.length > 0 ? (
          <>
            <span className="case-library-selection-scope max-w-[180px] overflow-hidden text-ellipsis whitespace-nowrap" title={selectedSuite?.name ?? '全部用例'}>
              {selectedSuite?.name ?? '全部用例'}
            </span>
            <span>已选 <strong>{selectedCaseIds.length}</strong> 项</span>
            <ProjectActionButton action="read" size="small" type="link" onClick={() => setSelectedCaseIds([])}>清空选择</ProjectActionButton>
          </>
        ) : null}
        <span>{hasCaseData ? <>共 <strong>{total}</strong> 条用例</> : casesQuery.isError ? '数量暂不可用' : '正在加载用例'}</span>
        {hasCaseFilters ? <ProjectActionButton action="read" size="small" type="link" onClick={clearCaseFilters}>清除用例筛选</ProjectActionButton> : null}
      </div>
    </div>
  )
}
