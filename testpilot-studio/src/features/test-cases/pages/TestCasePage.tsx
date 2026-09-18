import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { usePersonalConnectionChoice } from '@/features/base-services/components/usePersonalConnectionChoice'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { AppstoreOutlined } from '@ant-design/icons'
import { Alert, Drawer, Empty, Form, Input, InputNumber, Pagination, Popconfirm, Select, Space, Table, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useProjectRequirements } from '@/features/projects/hooks/useProjectRequirements'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { useSprintRequirementScope } from '@/features/projects/hooks/useSprintRequirementScope'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { useTestCasePageStore } from '@/features/test-cases/store/testCasePage.store'
import { api, listItems, type FunctionTestSuite, type FunctionTestSuitesZentaoImportResult, type Requirement } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import {
  formatTime,
  getErrorMessage,
  normalizeFunctionTestSuiteId,
  normalizeRequirementId,
  normalizeSprintId,
  pickCreatedAt,
  pickUpdatedAt,
} from '@/utils/format'

const { Text } = Typography

type FunctionalTestSuiteFormValues = {
  sprintId?: string
  requirementId?: string
  name: string
  description?: string
}

type ZentaoImportFormValues = {
  productId: number
  moduleId?: number
}

type TestCasePageScope = {
  projectId?: string
  sprintId?: string
  sprintName?: string
  requirementId: string
  requirementName?: string
}

function footerRange(total: number, currentPage: number, currentPageSize: number) {
  if (total === 0) return '显示第 0 条 - 第 0 条，共 0 条'
  const start = (currentPage - 1) * currentPageSize + 1
  const end = Math.min(currentPage * currentPageSize, total)
  return `显示第 ${start} 条 - 第 ${end} 条，共 ${total} 条`
}

export function TestCasePage({ scope }: { scope?: TestCasePageScope }) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const workbenchActiveProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const functionalSelectionsByProject = useTestCasePageStore((state) => state.functionalSelectionsByProject)
  const updateFunctionalSelection = useTestCasePageStore((state) => state.updateFunctionalSelection)
  const activeProjectId = scope?.projectId ?? workbenchActiveProjectId
  const queryClient = useQueryClient()
  const personalZentao = usePersonalConnectionChoice('zentao')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerSprintId, setDrawerSprintId] = useState<string | undefined>(undefined)
  const [editingSuite, setEditingSuite] = useState<FunctionTestSuite | null>(null)
  const [form] = Form.useForm<FunctionalTestSuiteFormValues>()
  const [zentaoImportSuite, setZentaoImportSuite] = useState<FunctionTestSuite | null>(null)
  const [zentaoImportForm] = Form.useForm<ZentaoImportFormValues>()
  const [requirementZentaoImportOpen, setRequirementZentaoImportOpen] = useState(false)
  const [requirementZentaoImportForm] = Form.useForm<ZentaoImportFormValues>()
  const [selectedRequirementSuiteIds, setSelectedRequirementSuiteIds] = useState<string[]>([])
  const [requirementImportResult, setRequirementImportResult] = useState<FunctionTestSuitesZentaoImportResult | null>(null)
  const isRequirementLocked = Boolean(scope?.requirementId)
  const { activeSprintId: globalSprintId, selectSprint: selectGlobalSprint } = useActiveSprint()

  const functionalSprintParam = searchParams.get('functionalSprintId')
  const functionalRequirementParam = searchParams.get('functionalRequirementId')
  const storedFunctionalSelection = activeProjectId ? functionalSelectionsByProject[activeProjectId] : undefined
  const initialFunctionalSprintId =
    functionalSprintParam !== null
      ? functionalSprintParam === 'all'
        ? null
        : functionalSprintParam
      : storedFunctionalSelection?.sprintId
  const initialFunctionalRequirementId =
    functionalRequirementParam !== null
      ? functionalRequirementParam === 'all'
        ? null
        : functionalRequirementParam
      : storedFunctionalSelection?.requirementId

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
    initialRequirementId: initialFunctionalRequirementId,
    initialSprintId: initialFunctionalSprintId,
    sprintScope: scope ? undefined : { value: globalSprintId, onChange: selectGlobalSprint },
  })

  const selectedSprintId = scope?.sprintId ?? resolvedSelectedSprintId
  const selectedRequirementId = scope?.requirementId ?? resolvedSelectedRequirementId
  const batchImportRequirementId = scope?.requirementId ?? selectedRequirementId
  const drawerSprintOptions = useMemo(
    () => sprints.map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) })),
    [sprints],
  )

  const { allRequirements, allRequirementsQuery, requirementNameMap, requirementSprintMap, sprintNameMap } =
    useProjectRequirements({
      activeProjectId,
      enabled: !sprintsQuery.isLoading && !isRequirementLocked,
      sprints,
    })

  const drawerRequirementsQuery = useQuery({
    queryKey: ['requirements', 'functionalSuiteDrawer', drawerSprintId],
    queryFn: () => api.getRequirements(drawerSprintId!),
    enabled: Boolean(drawerSprintId) && !editingSuite && !isRequirementLocked,
  })
  const drawerRequirementOptions = useMemo(
    () =>
      listItems(drawerRequirementsQuery.data).map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    [drawerRequirementsQuery.data],
  )

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

  const suitesQuery = useQuery({
    queryKey: [
      'functionTestSuites',
      activeProjectId,
      selectedSprintId,
      selectedRequirementId,
      allRequirements.map(normalizeRequirementId).join(','),
    ],
    queryFn: async () => {
      if (selectedRequirementId) {
        const suites = await api.getFunctionTestSuites(selectedRequirementId)
        return suites.map((suite) => ({
          ...suite,
          requirementId: suite.requirementId ?? suite.requirement_id ?? selectedRequirementId,
        }))
      }

      const targetRequirements: Requirement[] = selectedSprintId
        ? allRequirements.filter((item) => (item.sprintId ?? item.sprint_id) === selectedSprintId)
        : allRequirements

      if (targetRequirements.length === 0) return []

      const suiteGroups = await Promise.all(
        targetRequirements.map(async (requirement) => {
          const requirementId = normalizeRequirementId(requirement)
          const suites = await api.getFunctionTestSuites(requirementId)
          return suites.map((suite) => ({
            ...suite,
            requirementId: suite.requirementId ?? suite.requirement_id ?? requirementId,
          }))
        }),
      )

      return suiteGroups.flat()
    },
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading && !allRequirementsQuery.isLoading,
  })
  const suites = useMemo(() => suitesQuery.data ?? [], [suitesQuery.data])
  const orderedSuites = useMemo(
    () =>
      [...suites].sort((left, right) => {
        const leftTime = new Date(pickCreatedAt(left) ?? '').getTime()
        const rightTime = new Date(pickCreatedAt(right) ?? '').getTime()
        return (Number.isNaN(leftTime) ? 0 : leftTime) - (Number.isNaN(rightTime) ? 0 : rightTime)
      }),
    [suites],
  )
  const requirementImportableSuiteIds = useMemo(
    () => orderedSuites.map((suite) => normalizeFunctionTestSuiteId(suite)).filter((value): value is string => Boolean(value)),
    [orderedSuites],
  )
  const suiteNameMap = useMemo(
    () => new Map(orderedSuites.map((suite) => [normalizeFunctionTestSuiteId(suite), suite.name])),
    [orderedSuites],
  )
  const pagedSuites = useMemo(
    () => orderedSuites.slice((page - 1) * pageSize, page * pageSize),
    [orderedSuites, page, pageSize],
  )
  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(orderedSuites.length / pageSize))
    if (page > maxPage) setPage(maxPage)
  }, [orderedSuites.length, page, pageSize])

  useEffect(() => {
    setPage(1)
    setSelectedRequirementSuiteIds([])
  }, [selectedRequirementId, selectedSprintId])

  useEffect(() => {
    setSelectedRequirementSuiteIds((current) => current.filter((suiteId) => requirementImportableSuiteIds.includes(suiteId)))
  }, [requirementImportableSuiteIds])

  useEffect(() => {
    if (scope?.requirementId) return
    if (!activeProjectId) return

    updateFunctionalSelection(activeProjectId, {
      sprintId: currentSprintSelection === null ? null : selectedSprintId ?? null,
      requirementId: currentRequirementSelection === null ? null : selectedRequirementId ?? null,
    })

    const nextSearchParams = new URLSearchParams(searchParams)
    const nextSprintParam = currentSprintSelection === null ? 'all' : selectedSprintId ?? 'all'
    const nextRequirementParam = currentRequirementSelection === null ? 'all' : selectedRequirementId ?? 'all'
    const prevSprintParam = searchParams.get('functionalSprintId')
    const prevRequirementParam = searchParams.get('functionalRequirementId')

    if (
      searchParams.get('tab') === 'functional' &&
      prevSprintParam === nextSprintParam &&
      prevRequirementParam === nextRequirementParam
    ) {
      return
    }

    nextSearchParams.set('tab', 'functional')
    nextSearchParams.set('functionalSprintId', nextSprintParam)
    nextSearchParams.set('functionalRequirementId', nextRequirementParam)
    setSearchParams(nextSearchParams, { replace: true })
  }, [
    activeProjectId,
    currentRequirementSelection,
    currentSprintSelection,
    scope?.requirementId,
    searchParams,
    selectedRequirementId,
    selectedSprintId,
    setSearchParams,
    updateFunctionalSelection,
  ])

  function closeDrawer() {
    setDrawerOpen(false)
    setEditingSuite(null)
    setDrawerSprintId(undefined)
    form.resetFields()
  }

  function openCreateDrawer() {
    setEditingSuite(null)
    setDrawerSprintId(scope?.sprintId ?? resolvedSelectedSprintId)
    form.setFieldsValue({
      sprintId: scope?.sprintId ?? resolvedSelectedSprintId,
      requirementId: selectedRequirementId,
      name: '',
      description: '',
    })
    setDrawerOpen(true)
  }

  function openEditDrawer(suite: FunctionTestSuite) {
    setEditingSuite(suite)
    setDrawerSprintId(undefined)
    form.setFieldsValue({
      name: suite.name,
      description: suite.description,
    })
    setDrawerOpen(true)
  }

  function openZentaoImportModal(suite: FunctionTestSuite) {
    zentaoImportForm.setFieldsValue({
      productId: 1,
      moduleId: 0,
    })
    setZentaoImportSuite(suite)
  }

  function closeZentaoImportModal() {
    if (importZentaoTestCasesMutation.isPending) return
    setZentaoImportSuite(null)
  }

  function openRequirementZentaoImportModal() {
    requirementZentaoImportForm.setFieldsValue({
      productId: 1,
      moduleId: 0,
    })
    setRequirementImportResult(null)
    setRequirementZentaoImportOpen(true)
  }

  function closeRequirementZentaoImportModal() {
    if (importRequirementZentaoTestCasesMutation.isPending) return
    setRequirementZentaoImportOpen(false)
    setRequirementImportResult(null)
    requirementZentaoImportForm.resetFields()
  }

  const saveSuiteMutation = useMutation({
    mutationFn: (values: FunctionalTestSuiteFormValues) => {
      if (editingSuite) {
        const suiteId = normalizeFunctionTestSuiteId(editingSuite)
        if (!suiteId) throw new Error('未获取到功能测试集 ID')
        return api.updateFunctionTestSuite(suiteId, {
          name: values.name,
          description: values.description,
        })
      }

      const targetRequirementId = values.requirementId || selectedRequirementId
      if (!targetRequirementId) throw new Error('请选择所属需求')
      return api.createFunctionTestSuite(targetRequirementId, {
        name: values.name,
        description: values.description,
      })
    },
    onSuccess: (suite, values) => {
      const suiteId = normalizeFunctionTestSuiteId(suite)
      const nextRequirementId = suite.requirementId ?? values.requirementId ?? selectedRequirementId
      message.success(editingSuite ? '功能测试集已更新' : '功能测试集已创建')
      if (suiteId) {
        queryClient.setQueryData(['functionTestSuite', suiteId], suite)
      }
      if (nextRequirementId) {
        queryClient.invalidateQueries({ queryKey: ['functionTestSuites', nextRequirementId] })
      }
      queryClient.invalidateQueries({ queryKey: ['functionTestSuites'] })
      closeDrawer()
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const deleteSuiteMutation = useMutation({
    mutationFn: (suiteId: string) => api.deleteFunctionTestSuite(suiteId),
    onSuccess: async () => {
      message.success('功能测试集已删除')
      await queryClient.invalidateQueries({ queryKey: ['functionTestSuites'] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const importZentaoTestCasesMutation = useMutation({
    mutationFn: async (values: ZentaoImportFormValues) => {
      const suiteId = zentaoImportSuite ? normalizeFunctionTestSuiteId(zentaoImportSuite) : ''
      if (!suiteId) throw new Error('未获取到功能测试集 ID')

      const response = await api.getFunctionTestCases(suiteId)
      const caseIds = response.items.map((item) => item.caseId).filter((value): value is string => Boolean(value))
      if (caseIds.length === 0) throw new Error('当前测试集还没有可导入的用例')

      return api.importFunctionTestCasesToZentao(suiteId, {
        connectionId: await personalZentao.forZentaoRequirement(activeProjectId!, zentaoImportSuite?.requirementId ?? zentaoImportSuite?.requirement_id ?? ''),
        productId: values.productId,
        moduleId: values.moduleId ?? 0,
        caseIds,
      })
    },
    onSuccess: (result) => {
      const importedCount = result.importedCaseCount ?? result.imported_case_count ?? result.items?.length ?? 0
      message.success(`已导入禅道：${importedCount} 条用例`)
      setZentaoImportSuite(null)
      zentaoImportForm.resetFields()
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const importRequirementZentaoTestCasesMutation = useMutation({
    mutationFn: async (values: ZentaoImportFormValues & { suiteIds: string[] }) => {
      const requirementId = batchImportRequirementId
      if (!requirementId) throw new Error('未获取到需求 ID')
      if (values.suiteIds.length === 0) throw new Error('请至少选择一个测试集')

      return api.importFunctionTestSuitesToZentao(requirementId, {
        connectionId: await personalZentao.forZentaoRequirement(activeProjectId!, requirementId),
        productId: values.productId,
        moduleId: values.moduleId ?? 0,
        suiteIds: [...new Set(values.suiteIds)],
      })
    },
    onSuccess: (result) => {
      setRequirementImportResult(result)
      if (result.status === 'success') {
        message.success(`批量导入成功：${result.importedCaseCount} 条用例`)
      } else if (result.status === 'partial_failure') {
        message.warning(`批量导入部分成功：${result.succeededSuiteCount} 个成功，${result.failedSuiteCount} 个失败`)
      } else {
        message.error(`批量导入失败：${result.failedSuiteCount} 个测试集未导入`)
      }
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  async function importSelectedRequirementSuites(suiteIds: string[]) {
    if (suiteIds.length === 0) {
      message.warning('请至少选择一个测试集')
      return
    }
    const values = await requirementZentaoImportForm.validateFields()
    importRequirementZentaoTestCasesMutation.mutate({ ...values, suiteIds })
  }

  function retryFailedRequirementSuites(suiteIds: string[]) {
    const previousValues = importRequirementZentaoTestCasesMutation.variables
    if (!previousValues || suiteIds.length === 0) return
    importRequirementZentaoTestCasesMutation.mutate({ ...previousValues, suiteIds })
  }

  function handleOpenSuite(suite: FunctionTestSuite) {
    const suiteId = normalizeFunctionTestSuiteId(suite)
    if (!suiteId) {
      message.error('未获取到功能测试集 ID')
      return
    }
    const nextSearchParams = new URLSearchParams(searchParams)
    nextSearchParams.set('tab', 'functional')
    navigate(`/test-cases/suites/${suiteId}?${nextSearchParams.toString()}`)
  }

  function getSuiteRowContext(suite: FunctionTestSuite) {
    const suiteId = normalizeFunctionTestSuiteId(suite) ?? ''
    const requirementId = suite.requirementId ?? suite.requirement_id
    const suiteRequirementName = scope?.requirementName || (requirementId ? requirementNameMap.get(requirementId) ?? requirementId : '-')
    const sprintIdForSuite = scope?.sprintId ?? (requirementId ? requirementSprintMap.get(requirementId) : undefined)
    const suiteSprintName = scope?.sprintName || (sprintIdForSuite ? sprintNameMap.get(sprintIdForSuite) ?? sprintIdForSuite : '-')
    const suiteDescription = suite.description || '暂无功能测试集描述'
    const suiteScopeText = `${suiteSprintName} / ${suiteRequirementName}`

    return { suiteDescription, suiteId, suiteScopeText }
  }

  const columns: TableProps<FunctionTestSuite>['columns'] = [
    {
      title: '测试集名称',
      dataIndex: 'name',
      key: 'name',
      width: '24%',
      render: (name: FunctionTestSuite['name']) => (
        <Space size={0} className="functional-suite-list-name">
          <Tooltip title={name}>
            <Text ellipsis>{name}</Text>
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '所属迭代/需求',
      key: 'scope',
      width: '24%',
      ellipsis: true,
      render: (_, suite) => {
        const { suiteScopeText } = getSuiteRowContext(suite)
        return (
          <Tooltip title={suiteScopeText}>
            <Text className="functional-suite-list-scope" ellipsis>
              {suiteScopeText}
            </Text>
          </Tooltip>
        )
      },
    },
    {
      title: '用例数',
      key: 'caseCount',
      width: 90,
      align: 'center',
      render: (_, suite) => suite.caseCount ?? suite.case_count ?? suite.testcaseCount ?? suite.testcase_count ?? 0,
    },
    {
      title: '描述',
      key: 'description',
      ellipsis: true,
      render: (_, suite) => {
        const { suiteDescription } = getSuiteRowContext(suite)
        return (
          <Tooltip title={suiteDescription}>
            <Text className="functional-suite-list-description" type="secondary" ellipsis>
              {suiteDescription}
            </Text>
          </Tooltip>
        )
      },
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: 180,
      render: (_, suite) => <Text className="functional-suite-list-time" type="secondary">{formatTime(pickUpdatedAt(suite))}</Text>,
    },
    {
      title: '创建时间',
      key: 'createdAt',
      width: 180,
      render: (_, suite) => <Text className="functional-suite-list-time" type="secondary">{formatTime(pickCreatedAt(suite))}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 138,
      align: 'right',
      render: (_, suite) => {
        const { suiteId } = getSuiteRowContext(suite)
        return (
          <Space
            size={8}
            className="functional-suite-list-actions"
            onClick={(event) => event.stopPropagation()}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <Tooltip title="导入禅道">
              <ProjectActionButton action="execute"
                type="text"
                shape="circle"
                className="action-btn-update"
                operation="upload" iconOnly
                aria-label="导入禅道"
                onClick={() => openZentaoImportModal(suite)}
              />
            </Tooltip>
            <Tooltip title="编辑测试集">
              <ProjectActionButton action="write"
                type="text"
                shape="circle"
                className="action-btn-update"
                operation="edit" iconOnly
                aria-label="编辑功能测试集"
                onClick={() => openEditDrawer(suite)}
              />
            </Tooltip>
            <Popconfirm title="确认删除该功能测试集？" onConfirm={() => deleteSuiteMutation.mutate(suiteId)}>
              <Tooltip title="删除测试集">
                <ProjectActionButton action="write"
                  danger
                  type="text"
                  shape="circle"
                  className="action-btn-delete"
                  operation="delete" iconOnly
                  aria-label="删除功能测试集"
                  loading={deleteSuiteMutation.isPending && deleteSuiteMutation.variables === suiteId}
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        )
      },
    },
  ]

  return (
    <div className="workbench-page api-automation-page functional-test-page">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel">
          <div className="panel-header api-panel-header">
            <div className="requirement-panel-head">
              <Text strong>功能测试集</Text>
              {!isRequirementLocked ? (
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
                        setPage(1)
                      }}
                    />
                  </div>
                </div>
              ) : null}
            </div>
            <Space size={8}>

              {batchImportRequirementId ? (
                <ProjectActionButton action="execute"
                  className="action-btn-update"
                  operation="upload"
                  disabled={selectedRequirementSuiteIds.length === 0}
                  onClick={openRequirementZentaoImportModal}
                >
                  批量导入禅道{selectedRequirementSuiteIds.length > 0 ? `（${selectedRequirementSuiteIds.length}）` : ''}
                </ProjectActionButton>
              ) : null}
              <ProjectActionButton action="write"
                type="primary"
                className="action-btn-create"
                operation="create"
                disabled={!activeProjectId || sprints.length === 0}
                onClick={openCreateDrawer}
              >
                新建测试集
              </ProjectActionButton>
            </Space>
          </div>

          {sprintsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} /> : null}
          {requirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(requirementsQuery.error)} /> : null}
          {allRequirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(allRequirementsQuery.error)} /> : null}
          {suitesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(suitesQuery.error)} /> : null}

          {!activeProjectId ? (
            <div className="sprint-card-loading">
              <Empty description="请先选择项目" />
            </div>
          ) : !isRequirementLocked && !sprintsQuery.isLoading && sprints.length === 0 ? (
            <div className="sprint-card-loading">
              <Empty description="当前项目下暂无迭代" />
            </div>
          ) : (
            <div className="table-body-scroll sprint-card-scroll functional-suite-scroll">
              {suitesQuery.isLoading ? (
                <div className="sprint-card-loading">
                  <Empty description="功能测试集加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
              ) : orderedSuites.length === 0 ? (
                <div className="sprint-card-loading">
                  <Empty
                    image={<AppstoreOutlined />}
                    description={
                      <Space orientation="vertical" size={4}>
                        <Text strong>当前需求下还没有功能测试集</Text>
                        <Text type="secondary">先创建测试集，后续接口补齐后可进入详情管理用例与执行记录。</Text>
                      </Space>
                    }
                  >
                    <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" disabled={!activeProjectId || sprints.length === 0} onClick={openCreateDrawer}>
                      新建测试集
                    </ProjectActionButton>
                  </Empty>
                </div>
              ) : (
                <Table<FunctionTestSuite>
                  className="functional-suite-list-table"
                  columns={columns}
                  dataSource={pagedSuites}
                  rowKey={(suite) => normalizeFunctionTestSuiteId(suite) ?? suite.name}
                  rowSelection={batchImportRequirementId ? {
                    preserveSelectedRowKeys: true,
                    selectedRowKeys: selectedRequirementSuiteIds,
                    onChange: (keys) => setSelectedRequirementSuiteIds(keys.map(String)),
                    getCheckboxProps: (suite) => ({ disabled: !normalizeFunctionTestSuiteId(suite) }),
                  } : undefined}
                  pagination={false}
                  onRow={(suite) => ({
                    onClick: (event) => {
                      if ((event.target as HTMLElement).closest('.ant-table-selection-column')) return
                      handleOpenSuite(suite)
                    },
                  })}
                />
              )}
            </div>
          )}

          <div className="table-footer">
            <Text type="secondary">{footerRange(orderedSuites.length, page, pageSize)}</Text>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={orderedSuites.length}
              showSizeChanger
              pageSizeOptions={['10', '20', '30', '50']}
              onChange={(nextPage, nextPageSize) => {
                setPage(nextPage)
                setPageSize(nextPageSize)
              }}
            />
          </div>
        </section>
      </div>

      <Drawer
        title={editingSuite ? '编辑功能测试集' : '新建功能测试集'}
        open={drawerOpen}
        onClose={closeDrawer}
        size={520}
        extra={
          <ProjectActionButton action="write" type="primary" className="action-btn-save" onClick={() => form.submit()}>
            {saveSuiteMutation.isPending ? '保存中...' : '保存'}
          </ProjectActionButton>
        }
      >
        {drawerRequirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(drawerRequirementsQuery.error)} /> : null}
        <Form<FunctionalTestSuiteFormValues> form={form} layout="vertical" requiredMark={false} onFinish={(values) => saveSuiteMutation.mutate(values)}>
          {!editingSuite && !isRequirementLocked ? (
            <>
              <Form.Item name="sprintId" label="所属迭代" rules={[{ required: true, message: '请选择所属迭代' }]}>
                <Select
                  placeholder="请选择迭代"
                  options={drawerSprintOptions}
                  onChange={(value) => {
                    setDrawerSprintId(value)
                    form.setFieldValue('requirementId', undefined)
                  }}
                />
              </Form.Item>
              <Form.Item name="requirementId" label="所属需求" rules={[{ required: true, message: '请选择所属需求' }]}>
                <Select
                  placeholder="请选择需求"
                  options={drawerRequirementOptions}
                  loading={drawerRequirementsQuery.isLoading}
                  disabled={!drawerSprintId || drawerRequirementOptions.length === 0}
                />
              </Form.Item>
            </>
          ) : null}
          <Form.Item name="name" label="测试集名称" rules={[{ required: true, message: '请输入测试集名称' }]}>
            <Input maxLength={120} placeholder="例如：登录主流程 / 订单核心链路" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={5} maxLength={512} placeholder="补充测试集目标、范围或备注" />
          </Form.Item>
        </Form>
      </Drawer>

      {personalZentao.dialog}
      <ProjectActionModal action="execute"
        mask={{ closable: false }}
        open={Boolean(zentaoImportSuite)}
        title="导入到禅道"
        okText={importZentaoTestCasesMutation.isPending ? '导入中...' : '开始导入'}
        cancelText="取消"
        confirmLoading={importZentaoTestCasesMutation.isPending}
        onCancel={closeZentaoImportModal}
        onOk={async () => {
          const values = await zentaoImportForm.validateFields()
          importZentaoTestCasesMutation.mutate(values)
        }}
      >
        <Form<ZentaoImportFormValues> form={zentaoImportForm} layout="vertical" requiredMark={false}>
          <Form.Item
            name="productId"
            label="禅道产品 ID"
            rules={[{ required: true, message: '请输入禅道产品 ID' }]}
          >
            <InputNumber min={1} precision={0} placeholder="例如：1" />
          </Form.Item>
          <Form.Item name="moduleId" label="禅道模块 ID">
            <InputNumber min={0} precision={0} placeholder="默认 0" />
          </Form.Item>
        </Form>
      </ProjectActionModal>

      <ProjectActionModal action="execute"
        mask={{ closable: false }}
        open={requirementZentaoImportOpen}
        title={requirementImportResult ? '批量导入结果' : '批量导入禅道'}
        width={720}
        okText={requirementImportResult ? '关闭' : importRequirementZentaoTestCasesMutation.isPending ? '导入中...' : '开始导入'}
        cancelText="取消"
        confirmLoading={importRequirementZentaoTestCasesMutation.isPending}
        cancelButtonProps={{ style: requirementImportResult ? { display: 'none' } : undefined }}
        onCancel={closeRequirementZentaoImportModal}
        onOk={async () => {
          if (requirementImportResult) {
            closeRequirementZentaoImportModal()
            return
          }
          await importSelectedRequirementSuites(selectedRequirementSuiteIds)
        }}
      >
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          {requirementImportResult ? (
            <>
              <Alert
                showIcon
                type={requirementImportResult.status === 'success' ? 'success' : requirementImportResult.status === 'partial_failure' ? 'warning' : 'error'}
                title={
                  requirementImportResult.status === 'success'
                    ? '全部测试集导入成功'
                    : requirementImportResult.status === 'partial_failure'
                      ? '部分测试集导入失败'
                      : '全部测试集导入失败'
                }
                description={`成功 ${requirementImportResult.succeededSuiteCount} 个，失败 ${requirementImportResult.failedSuiteCount} 个，共导入 ${requirementImportResult.importedCaseCount} 条用例。`}
              />
              <Table
                size="small"
                pagination={false}
                rowKey="suiteId"
                dataSource={requirementImportResult.items}
                columns={[
                  {
                    title: '测试集',
                    dataIndex: 'suiteId',
                    render: (suiteId: string) => suiteNameMap.get(suiteId) ?? suiteId,
                  },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    width: 90,
                    render: (status: 'success' | 'failed') => (
                      <Text type={status === 'success' ? 'success' : 'danger'}>{status === 'success' ? '成功' : '失败'}</Text>
                    ),
                  },
                  {
                    title: '导入数量/失败原因',
                    key: 'result',
                    render: (_, item) => item.status === 'success'
                      ? `${item.importedCaseCount} 条用例`
                      : `${item.errorMessage || '导入失败'}${item.errorCode ? `（${item.errorCode}）` : ''}`,
                  },
                ]}
              />
              {requirementImportResult.failedSuiteCount > 0 ? (
                <ProjectActionButton action="execute"
                  type="primary"
                  className="action-btn-save"
                  loading={importRequirementZentaoTestCasesMutation.isPending}
                  onClick={() => retryFailedRequirementSuites(
                    requirementImportResult.items.filter((item) => item.status === 'failed').map((item) => item.suiteId),
                  )}
                >
                  重试失败项
                </ProjectActionButton>
              ) : null}
            </>
          ) : (
            <>
              <Alert
                showIcon
                type="info"
                title={`将导入当前需求“${scope?.requirementName ?? selectedRequirementId ?? '-'}”下选中的 ${selectedRequirementSuiteIds.length} 个测试集`}
                description="每个测试集的全部用例将通过一次批量请求导入禅道。"
              />
              <Form<ZentaoImportFormValues> form={requirementZentaoImportForm} layout="vertical" requiredMark={false}>
                <Form.Item
                  name="productId"
                  label="禅道产品 ID"
                  rules={[{ required: true, message: '请输入禅道产品 ID' }]}
                >
                  <InputNumber min={1} precision={0} placeholder="例如：1" />
                </Form.Item>
                <Form.Item name="moduleId" label="禅道模块 ID">
                  <InputNumber min={0} precision={0} placeholder="默认 0" />
                </Form.Item>
              </Form>
            </>
          )}
        </Space>
      </ProjectActionModal>
    </div>
  )
}
