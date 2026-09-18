import { AppstoreOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Input, Pagination, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { useProjectRequirements } from '@/features/projects/hooks/useProjectRequirements'
import { useSprintRequirementScope } from '@/features/projects/hooks/useSprintRequirementScope'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { FunctionCasePreviewDrawer } from '@/features/test-cases/components/FunctionCasePreviewDrawer'
import { useCaseLibraryStore } from '@/features/test-cases/store/caseLibrary.store'
import { priorityColor } from '@/features/test-cases/utils/casePriority'
import { api, listItems, listTotal, type FunctionCaseLibraryItem } from '@/services/api'
import {
  formatTime,
  getErrorMessage,
  normalizeFunctionTestCaseId,
  normalizeFunctionTestSuiteId,
  normalizeRequirementId,
  pickUpdatedAt,
} from '@/utils/format'
import '@/features/test-cases/styles/index.css'

const { Text } = Typography

const PAGE_SIZE_OPTIONS = ['10', '20', '30', '50']

const PRIORITY_FILTER_OPTIONS = [
  { label: '全部优先级', value: 'all' },
  { label: 'P0', value: 'P0' },
  { label: 'P1', value: 'P1' },
  { label: 'P2', value: 'P2' },
  { label: 'P3', value: 'P3' },
]

function footerRange(total: number, currentPage: number, currentPageSize: number) {
  if (total === 0) return '显示第 0 条 - 第 0 条，共 0 条'
  const start = (currentPage - 1) * currentPageSize + 1
  const end = Math.min(currentPage * currentPageSize, total)
  return `显示第 ${start} 条 - 第 ${end} 条，共 ${total} 条`
}

type CaseLibraryPageProps = {
  onLeaveToFunctional?: () => void
}

export function CaseLibraryPage({ onLeaveToFunctional }: CaseLibraryPageProps) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const selectionsByProject = useCaseLibraryStore((state) => state.selectionsByProject)
  const updateSelection = useCaseLibraryStore((state) => state.updateSelection)
  const { activeSprintId: globalSprintId, selectSprint: selectGlobalSprint } = useActiveSprint()

  const storedSelection = activeProjectId ? selectionsByProject[activeProjectId] : undefined
  const libraryRequirementParam = searchParams.get('libraryRequirementId')
  const initialRequirementId =
    libraryRequirementParam !== null
      ? libraryRequirementParam === 'all'
        ? null
        : libraryRequirementParam
      : storedSelection?.requirementId

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [suiteId, setSuiteId] = useState<string | null>(storedSelection?.suiteId ?? null)
  const [priority, setPriority] = useState<string | null>(storedSelection?.priority ?? null)
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [previewItem, setPreviewItem] = useState<FunctionCaseLibraryItem | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)

  const {
    currentRequirementSelection,
    currentSprintSelection,
    requirementFilterOptions,
    requirementsQuery,
    resolvedSelectedRequirementId,
    resolvedSelectedSprintId,
    selectRequirement,
    selectSprint,
    sprintFilterOptions,
    sprints,
    sprintsQuery,
  } = useSprintRequirementScope({
    activeProjectId,
    includeAllRequirementOption: true,
    includeAllSprintOption: true,
    defaultToAllWhenIncluded: true,
    initialRequirementId,
    sprintScope: { value: globalSprintId, onChange: selectGlobalSprint },
  })

  const selectedSprintId = resolvedSelectedSprintId
  const selectedRequirementId = resolvedSelectedRequirementId

  const { allRequirements, allRequirementsQuery } = useProjectRequirements({
    activeProjectId,
    enabled: !sprintsQuery.isLoading,
    sprints,
  })

  const displayRequirementFilterOptions = useMemo(() => {
    if (selectedSprintId) return requirementFilterOptions
    return [
      { label: '全部需求', value: 'all' },
      ...allRequirements.map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    ]
  }, [allRequirements, requirementFilterOptions, selectedSprintId])

  // 测试集筛选项跟随已选迭代 / 需求收敛，避免列出无关测试集。
  const suiteOptionsQuery = useQuery({
    queryKey: ['caseLibrarySuites', activeProjectId, selectedSprintId, selectedRequirementId],
    queryFn: () =>
      api.getProjectFunctionTestSuites(activeProjectId!, {
        sprintId: selectedSprintId ?? '',
        requirementId: selectedRequirementId ?? '',
      }),
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })
  const suiteFilterOptions = useMemo(
    () => [
      { label: '全部测试集', value: 'all' },
      ...listItems(suiteOptionsQuery.data).map((suite) => ({
        label: suite.name,
        value: normalizeFunctionTestSuiteId(suite) ?? suite.name,
      })),
    ],
    [suiteOptionsQuery.data],
  )

  const casesQuery = useQuery({
    queryKey: [
      'caseLibraryCases',
      activeProjectId,
      selectedSprintId,
      selectedRequirementId,
      suiteId,
      priority,
      keyword,
      page,
      pageSize,
    ],
    queryFn: () =>
      api.getProjectFunctionTestCases(activeProjectId!, {
        sprintId: selectedSprintId ?? '',
        requirementId: selectedRequirementId ?? '',
        suiteId: suiteId ?? '',
        priority: priority ?? '',
        keyword,
        page,
        pageSize,
      }),
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })

  const cases = listItems(casesQuery.data)
  const total = listTotal(casesQuery.data)
  const hasLocalFilters = Boolean(suiteId || priority || keyword)

  const renderedProjectRef = useRef<string | undefined>(activeProjectId)
  useEffect(() => {
    if (renderedProjectRef.current === activeProjectId) return
    renderedProjectRef.current = activeProjectId
    const nextStored = activeProjectId ? selectionsByProject[activeProjectId] : undefined
    setSuiteId(nextStored?.suiteId ?? null)
    setPriority(nextStored?.priority ?? null)
    setKeywordInput('')
    setKeyword('')
    setPage(1)
  }, [activeProjectId, selectionsByProject])

  useEffect(() => {
    const timer = setTimeout(() => {
      setKeyword(keywordInput.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [keywordInput])

  useEffect(() => {
    if (!activeProjectId) return
    updateSelection(activeProjectId, {
      requirementId: currentRequirementSelection === null ? null : selectedRequirementId ?? null,
      suiteId,
      priority,
    })

    const nextSearchParams = new URLSearchParams(searchParams)
    const nextRequirementParam = currentRequirementSelection === null ? 'all' : selectedRequirementId ?? 'all'
    const prevRequirementParam = searchParams.get('libraryRequirementId')

    if (searchParams.get('tab') === 'library' && prevRequirementParam === nextRequirementParam) {
      return
    }

    nextSearchParams.set('tab', 'library')
    nextSearchParams.set('libraryRequirementId', nextRequirementParam)
    setSearchParams(nextSearchParams, { replace: true })
  }, [
    activeProjectId,
    currentRequirementSelection,
    searchParams,
    selectedRequirementId,
    setSearchParams,
    suiteId,
    priority,
    updateSelection,
  ])

  function clearLocalFilters() {
    setSuiteId(null)
    setPriority(null)
    setKeywordInput('')
    setKeyword('')
    setPage(1)
  }

  function openPreview(item: FunctionCaseLibraryItem) {
    setPreviewItem(item)
    setPreviewOpen(true)
  }

  const columns: TableProps<FunctionCaseLibraryItem>['columns'] = [
    {
      title: '用例标题',
      key: 'title',
      width: '26%',
      render: (_, item) => (
        <Space size={0} className="functional-suite-list-name">
          <Tooltip title={item.title}>
            <Text ellipsis>{item.title}</Text>
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '所属测试集',
      key: 'suiteName',
      width: '16%',
      ellipsis: true,
      render: (_, item) => (
        <Tooltip title={item.suiteName}>
          <Text className="functional-suite-list-scope" ellipsis>
            {item.suiteName || '-'}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '迭代',
      key: 'sprintName',
      width: 140,
      ellipsis: true,
      render: (_, item) => <Text type="secondary">{item.sprintName || '-'}</Text>,
    },
    {
      title: '需求',
      key: 'requirementName',
      width: '16%',
      ellipsis: true,
      render: (_, item) => (
        <Tooltip title={item.requirementName}>
          <Text type="secondary" ellipsis>
            {item.requirementName || '-'}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '模块',
      key: 'module',
      width: 120,
      ellipsis: true,
      render: (_, item) => <Text type="secondary">{item.module || '-'}</Text>,
    },
    {
      title: '优先级',
      key: 'priority',
      width: 90,
      render: (_, item) => (item.priority ? <Tag color={priorityColor(item.priority)}>{item.priority}</Tag> : '-'),
    },
    {
      title: '用例类型',
      key: 'caseType',
      width: 110,
      ellipsis: true,
      render: (_, item) => <Text type="secondary">{item.caseType || '-'}</Text>,
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: 180,
      render: (_, item) => (
        <Text className="functional-suite-list-time" type="secondary">
          {formatTime(pickUpdatedAt(item))}
        </Text>
      ),
    },
  ]

  return (
    <div className="workbench-page api-automation-page functional-test-page">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel">
          <div className="panel-header api-panel-header">
            <div className="requirement-panel-head">
              <Text strong>用例库</Text>
              <div className="api-filter-group">
                <div className="api-filter-field">
                  <span className="api-filter-field-label">迭代</span>
                  <Select
                    className="api-filter-select business-filter-select"
                    value={currentSprintSelection === null ? 'all' : selectedSprintId ?? 'all'}
                    options={sprintFilterOptions}
                    loading={sprintsQuery.isLoading}
                    placeholder="请选择迭代"
                    onChange={(value: string) => {
                      selectSprint(value === 'all' ? null : value)
                      if (value === 'all') {
                        selectRequirement(null)
                      }
                      setSuiteId(null)
                      setPage(1)
                    }}
                  />
                </div>
                <div className="api-filter-field">
                  <span className="api-filter-field-label">需求</span>
                  <Select
                    className="api-filter-select business-filter-select"
                    value={currentRequirementSelection === null ? 'all' : selectedRequirementId ?? 'all'}
                    options={displayRequirementFilterOptions}
                    loading={requirementsQuery.isLoading || allRequirementsQuery.isLoading}
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
                  <span className="api-filter-field-label">测试集</span>
                  <Select
                    className="api-filter-select business-filter-select"
                    value={suiteId ?? 'all'}
                    options={suiteFilterOptions}
                    loading={suiteOptionsQuery.isLoading}
                    placeholder="请选择测试集"
                    onChange={(value: string) => {
                      setSuiteId(value === 'all' ? null : value)
                      setPage(1)
                    }}
                  />
                </div>
                <div className="api-filter-field">
                  <span className="api-filter-field-label">优先级</span>
                  <Select
                    className="api-filter-select business-filter-select"
                    value={priority ?? 'all'}
                    options={PRIORITY_FILTER_OPTIONS}
                    onChange={(value: string) => {
                      setPriority(value === 'all' ? null : value)
                      setPage(1)
                    }}
                  />
                </div>
                <div className="api-filter-field">
                  <Input
                    className="api-filter-input"
                    allowClear
                    placeholder="搜索用例名称 / 模块"
                    value={keywordInput}
                    onChange={(event) => setKeywordInput(event.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>

          {sprintsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} /> : null}
          {requirementsQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(requirementsQuery.error)} />
          ) : null}
          {allRequirementsQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(allRequirementsQuery.error)} />
          ) : null}
          {casesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(casesQuery.error)} /> : null}

          {!activeProjectId ? (
            <div className="sprint-card-loading">
              <Empty description="请先选择项目" />
            </div>
          ) : !sprintsQuery.isLoading && sprints.length === 0 ? (
            <div className="sprint-card-loading">
              <Empty description="当前项目下暂无迭代" />
            </div>
          ) : (
            <div className="table-body-scroll sprint-card-scroll functional-suite-scroll">
              {casesQuery.isLoading ? (
                <div className="sprint-card-loading">
                  <Empty description="用例加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
              ) : cases.length === 0 ? (
                <div className="sprint-card-loading">
                  <Empty
                    image={<AppstoreOutlined />}
                    description={
                      <Space orientation="vertical" size={4}>
                        <Text strong>{hasLocalFilters ? '没有符合筛选条件的功能用例' : '当前项目下还没有功能用例'}</Text>
                        <Text type="secondary">
                          {hasLocalFilters
                            ? '调整或清空筛选条件后再看。'
                            : '用例在功能测试的测试集里创建，创建后即可在这里跨迭代检索。'}
                        </Text>
                      </Space>
                    }
                  >
                    {hasLocalFilters ? (
                      <Button onClick={clearLocalFilters}>清空筛选</Button>
                    ) : (
                      <Button type="primary" className="action-btn-create" onClick={onLeaveToFunctional}>
                        去功能测试创建用例
                      </Button>
                    )}
                  </Empty>
                </div>
              ) : (
                <Table<FunctionCaseLibraryItem>
                  className="functional-suite-list-table"
                  columns={columns}
                  dataSource={cases}
                  rowKey={(item) => normalizeFunctionTestCaseId(item) ?? item.title}
                  pagination={false}
                  onRow={(item) => ({ onClick: () => openPreview(item) })}
                />
              )}
            </div>
          )}

          <div className="table-footer">
            <Text type="secondary">{footerRange(total, page, pageSize)}</Text>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={total}
              showSizeChanger
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              onChange={(nextPage, nextPageSize) => {
                setPage(nextPage)
                setPageSize(nextPageSize)
              }}
            />
          </div>
        </section>
      </div>

      <FunctionCasePreviewDrawer
        open={previewOpen}
        item={previewItem}
        onClose={() => setPreviewOpen(false)}
        onOpenSuite={(targetSuiteId) => {
          setPreviewOpen(false)
          navigate(`/test-cases/suites/${targetSuiteId}`)
        }}
      />
    </div>
  )
}
