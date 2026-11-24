import {
  CheckCircleOutlined,
  DeleteOutlined,
  DownOutlined,
  FilterOutlined,
  LinkOutlined,
  ReloadOutlined,
  SearchOutlined,
  StopOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { Alert, Button, Dropdown, Modal, Popover, Select, Space, Tooltip, type MenuProps } from 'antd'
import { useState } from 'react'
import { DebouncedSearchInput } from '@/shared/components/DebouncedSearchInput'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { SprintFilterSelect } from '@/domain/projects/components/SprintFilterSelect'
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
    sprintFilterOptions,
    selectSprint,
    sprintsQuery,
    setSuiteId,
    setPage,
    caseType,
    setCaseType,
    keywordInputRef,
    searchResetKey,
    commitKeyword,
    searchShortcut,
  } = page
  const [filterOpen, setFilterOpen] = useState(false)
  const activeFilterCount = Number(Boolean(selectedRequirementId)) + Number(Boolean(caseType))

  const filterPanel = (
    <div className="flex w-[300px] flex-col gap-3">
      <label className="case-library-filter-field flex flex-col gap-1.5">
        <span className="case-library-filter-label text-[12px] text-[var(--srf-text-secondary)]">需求</span>
        <Select
          className="w-full"
          aria-label="筛选需求"
          value={currentRequirementSelection === null ? 'all' : selectedRequirementId ?? 'all'}
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
      </label>
      <label className="case-library-filter-field flex flex-col gap-1.5">
        <span className="case-library-filter-label text-[12px] text-[var(--srf-text-secondary)]">用例类型</span>
        <Select
          className="w-full"
          aria-label="筛选用例类型"
          value={caseType ?? 'all'}
          options={CASE_TYPE_FILTER_OPTIONS}
          onChange={(value: string) => {
            setCaseType(value === 'all' ? null : value)
            setPage(1)
          }}
        />
      </label>
      <div className="flex justify-end gap-2 pt-1">
        <Button
          type="text"
          size="small"
          onClick={() => {
            selectRequirement(null)
            setCaseType(null)
            setSuiteId(null)
            setPage(1)
          }}
        >
          重置
        </Button>
        <Button type="primary" size="small" onClick={() => setFilterOpen(false)}>
          应用
        </Button>
      </div>
    </div>
  )

  return (
    <div className="api-filter-group case-library-filters flex flex-wrap items-center gap-2">
      <h1 className="tp-list-title">用例库</h1>
      <SprintFilterSelect value={selectedSprintId ?? 'all'} options={sprintFilterOptions}
        loading={sprintsQuery.isLoading} onChange={selectSprint} />
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
      <Popover
        title="筛选"
        trigger="click"
        placement="bottomLeft"
        open={filterOpen}
        onOpenChange={setFilterOpen}
        content={filterPanel}
      >
        <Button className="action-btn-update case-library-filter-trigger" icon={<FilterOutlined />} aria-label="筛选用例">
          筛选{activeFilterCount > 0 ? `（${activeFilterCount}）` : ''} <DownOutlined />
        </Button>
      </Popover>
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
    batchInvalidateCasesMutation,
    batchDeleteCasesMutation,
    openCreateCase,
  } = page
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const batchPending = batchInvalidateCasesMutation.isPending || batchDeleteCasesMutation.isPending

  const importItems: MenuProps['items'] = [
    { key: 'file', icon: <UploadOutlined />, label: '用例导入' },
    {
      key: 'zentao',
      icon: <LinkOutlined />,
      label: '导入禅道',
      disabled: !selectedSuite || suiteCaseCount(selectedSuite) === 0,
    },
  ]

  const batchItems: MenuProps['items'] = [
    {
      key: 'invalidate',
      icon: <StopOutlined />,
      label: '标记失效',
      disabled: batchInvalidateCasesMutation.isPending,
    },
    {
      key: 'restore',
      icon: <CheckCircleOutlined />,
      label: '恢复有效',
      disabled: batchInvalidateCasesMutation.isPending,
    },
    { type: 'divider' },
    {
      key: 'delete',
      icon: <DeleteOutlined />,
      danger: true,
      disabled: !suiteId || batchDeleteCasesMutation.isPending,
      label: (
        <span title={suiteId ? undefined : '批量删除按测试集执行，请先在左栏选中一个测试集'}>
          批量删除
        </span>
      ),
    },
  ]

  return (
    <>
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
          <Dropdown
            trigger={['click']}
            menu={{
              items: importItems,
              onClick: ({ key }) => {
                if (key === 'file') setCaseImportOpen(true)
                if (key === 'zentao') openZentaoImport(selectedCaseIds)
              },
            }}
          >
            <span className="inline-flex">
              <ProjectActionButton action="execute" className="action-btn-update" operation="upload">
                导入 <DownOutlined />
              </ProjectActionButton>
            </span>
          </Dropdown>
        ) : null}
        {selectedCaseIds.length > 0 ? (
          <Dropdown
            trigger={['click']}
            menu={{
              items: batchItems,
              onClick: ({ key }) => {
                if (key === 'invalidate') batchInvalidateCasesMutation.mutate(true)
                if (key === 'restore') batchInvalidateCasesMutation.mutate(false)
                if (key === 'delete') setDeleteConfirmOpen(true)
              },
            }}
          >
            <span className="inline-flex">
              <ProjectActionButton action="write" className="action-btn-update" loading={batchPending}>
                批量操作（{selectedCaseIds.length}） <DownOutlined />
              </ProjectActionButton>
            </span>
          </Dropdown>
        ) : null}
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
      <Modal
        open={deleteConfirmOpen}
        title={`确认删除「${selectedSuite?.name ?? '当前测试集'}」中选中的 ${selectedCaseIds.length} 条用例？`}
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        onOk={() => {
          setDeleteConfirmOpen(false)
          batchDeleteCasesMutation.mutate()
        }}
        onCancel={() => setDeleteConfirmOpen(false)}
      >
        删除后不可恢复。
      </Modal>
    </>
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
