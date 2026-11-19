import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { Alert, Popconfirm, Select, Space, Tooltip } from 'antd'
import { DebouncedSearchInput } from '@/shared/components/DebouncedSearchInput'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { CASE_TYPE_PRESETS } from '../utils/caseTone'
import { getErrorMessage } from '@/utils/format'
import { suiteCaseCount, type CaseLibraryPageModel } from '../hooks/useCaseLibraryPage'

const CASE_TYPE_FILTER_OPTIONS = [
  { label: '全部类型', value: 'all' },
  ...CASE_TYPE_PRESETS.map((value) => ({ label: value, value })),
]

function CaseLibraryFilterGroup({ page }: { page: CaseLibraryPageModel }) {
  const {
    currentRequirementSelection,
    selectedRequirementId,
    displayRequirementFilterOptions,
    requirementsLoading,
    allRequirementsQuery,
    selectedSprintId,
    allRequirements,
    selectRequirement,
    setSuiteId,
    setPage,
    caseType,
    setCaseType,
    keywordInputRef,
    searchResetKey,
    commitKeyword,
    searchShortcut,
  } = page

  return (
    <div className="api-filter-group case-library-filters flex flex-wrap items-center gap-2">
      <h1 className="tp-list-title">用例库</h1>
      <div className="api-filter-field">
        <span className="api-filter-field-label">需求</span>
        <Select
          className="api-filter-select business-filter-select"
          aria-label="筛选需求"
          value={
            currentRequirementSelection === null ? 'all' : selectedRequirementId ?? 'all'
          }
          options={displayRequirementFilterOptions}
          loading={requirementsLoading || allRequirementsQuery.isLoading}
          placeholder="请选择需求"
          disabled={!selectedSprintId && allRequirements.length === 0}
          onChange={(value: string) => {
            selectRequirement(value === 'all' ? null : value)
            setSuiteId(null)
            setPage(1)
          }}
        />
      </div>
      <div className="api-filter-field">
        <span className="api-filter-field-label">用例类型</span>
        <Select
          className="api-filter-select business-filter-select"
          aria-label="筛选用例类型"
          value={caseType ?? 'all'}
          options={CASE_TYPE_FILTER_OPTIONS}
          onChange={(value: string) => {
            setCaseType(value === 'all' ? null : value)
            setPage(1)
          }}
        />
      </div>
      <div className="api-filter-field case-library-search-field w-72 min-w-0 max-w-full">
        <DebouncedSearchInput
          className="api-filter-input case-library-search-input min-w-0 flex-1 rounded-[var(--srf-radius-control)]"
          inputRef={keywordInputRef}
          prefix={<SearchOutlined />}
          suffix={<span className="case-library-search-hint font-mono text-[10px] text-[var(--srf-text-muted)]" aria-hidden="true">{searchShortcut}</span>}
          ariaLabel="搜索用例名称或模块"
          placeholder="搜索用例名称 / 模块"
          resetKey={searchResetKey}
          onCommit={commitKeyword}
        />
      </div>
    </div>
  )
}

function CaseLibraryToolbarActions({ page }: { page: CaseLibraryPageModel }) {
  const {
    casesQuery,
    suitesQuery,
    selectedSuite,
    suiteId,
    setCaseImportOpen,
    openZentaoImport,
    selectedCaseIds,
    batchDeleteCasesMutation,
    openCreateCase,
  } = page

  return (
    <Space size={8} className="case-library-toolbar-actions tp-refresh-actions flex-none items-center">
      <Tooltip title="刷新用例列表">
        <ProjectActionButton
          action="read"
          type="text"
          shape="circle"
          className="action-btn-read case-library-refresh"
          operation="refresh"
          icon={<ReloadOutlined />}
          iconOnly
          aria-label="刷新用例列表"
          loading={casesQuery.isFetching || suitesQuery.isFetching}
          onClick={() => {
            casesQuery.refetch()
            suitesQuery.refetch()
          }}
        />
      </Tooltip>
      {selectedSuite ? (
        <Space size={8} className="case-library-main-actions">
          <ProjectActionButton
            action="execute"
            className="action-btn-update"
            operation="upload"
            onClick={() => setCaseImportOpen(true)}
          >
            用例导入
          </ProjectActionButton>
          <ProjectActionButton
            action="execute"
            className="action-btn-update"
            operation="upload"
            disabled={suiteCaseCount(selectedSuite) === 0}
            onClick={() => openZentaoImport(selectedCaseIds)}
          >
            导入禅道
          </ProjectActionButton>
        </Space>
      ) : null}

      <Popconfirm
        title={`确认删除「${selectedSuite?.name ?? '当前测试集'}」中选中的 ${selectedCaseIds.length} 条用例？`}
        description="删除后不可恢复。"
        okText="确认删除"
        okButtonProps={{ danger: true }}
        disabled={!suiteId || selectedCaseIds.length === 0}
        onConfirm={() => batchDeleteCasesMutation.mutate()}
      >
        <Tooltip
          title={
            suiteId ? undefined : '批量删除按测试集执行，请先在左栏选中一个测试集'
          }
        >
          <ProjectActionButton
            action="write"
            danger
            className="action-btn-delete"
            operation="delete"
            disabled={!suiteId || selectedCaseIds.length === 0}
            loading={batchDeleteCasesMutation.isPending}
          >
            批量删除{selectedCaseIds.length > 0 ? `（${selectedCaseIds.length}）` : ''}
          </ProjectActionButton>
        </Tooltip>
      </Popconfirm>
      {selectedSuite ? (
        <ProjectActionButton
          action="write"
          type="primary"
          className="action-btn-create"
          operation="create"
          onClick={openCreateCase}
        >
          新建用例
        </ProjectActionButton>
      ) : null}
    </Space>
  )
}

export function CaseLibraryToolbar({ page }: { page: CaseLibraryPageModel }) {
  const { sprintsQuery, allRequirementsQuery } = page

  return <>
    <div className="panel-header api-panel-header case-library-toolbar tp-list-toolbar">
      <CaseLibraryFilterGroup page={page} />
      <CaseLibraryToolbarActions page={page} />
    </div>

    {sprintsQuery.error ? (
      <Alert showIcon type="error" title="迭代加载失败" description={getErrorMessage(sprintsQuery.error)}
        action={<ProjectActionButton action="read" onClick={() => sprintsQuery.refetch()}>重试迭代</ProjectActionButton>} />
    ) : null}
    {allRequirementsQuery.error ? (
      <Alert showIcon type="error" title="需求加载失败"
        description={getErrorMessage(allRequirementsQuery.error)}
        action={<ProjectActionButton action="read" onClick={() => void allRequirementsQuery.refetch()}>重试需求</ProjectActionButton>} />
    ) : null}
  </>
}
