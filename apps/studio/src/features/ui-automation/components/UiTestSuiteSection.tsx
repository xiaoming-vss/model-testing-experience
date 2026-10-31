import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { ListPagination } from '@/shared/components/ListPagination'
import '@/shared/styles/list-table.css'
import '@/shared/styles/surface-tokens.css'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { AppstoreOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Form, Space, Table, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { UiSuiteNameCell, UiSuiteRowActions, UiSuiteScopeCell } from './UiSuiteListCells'
import { UiSuiteRunConfigCell } from './UiSuiteRunConfigCell'
import { UiTestSuiteDrawer, type UiTestSuiteFormValues } from './UiTestSuiteDrawer'
import { DEFAULT_UI_TEST_SUITE_RUN_CONFIG } from '../constants/defaultRunConfig'
import { buildUiSuiteRunPayload } from '../utils/runHelpers'
import { api, ApiError, type UiTestSuite, type UiTestSuiteRunSummary } from '@/services/api'
import { formatTime, getErrorMessage, normalizeUiTestSuiteId, pickCreatedAt, pickUpdatedAt } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { buildUiTestSuiteUpdatePayload } from '@/utils/updatePayload'

const { Text } = Typography

export type UiTestSuiteSectionRef = {
  openCreateDrawer: () => void
  refresh: () => void
}

function isUiSuiteRunPollingStatus(status?: string) {
  return status === 'pending' || status === 'claimed' || status === 'running'
}

function getUiSuiteRunId(run?: UiTestSuiteRunSummary | null) {
  return run?.suiteRunId ?? ''
}

export const UiTestSuiteSection = forwardRef<
  UiTestSuiteSectionRef,
  {
    requirementId?: string
    requirementIds?: string[]
    selectedSprintId?: string
    sprintOptions?: Array<{ label: string; value: string }>
    requirementOptions?: Array<{ label: string; value: string }>
    sprintName?: string
    requirementName?: string
    sprintNameResolver?: (suite: UiTestSuite) => string
    requirementNameResolver?: (suite: UiTestSuite) => string
    onCreateSprintChange?: (value?: string) => void
    /** 工具栏里的搜索词，前端过滤名称与描述；空态里的「清空搜索」回调也在这里。 */
    keyword?: string
    onClearKeyword?: () => void
    /** 把查询的加载态回传给工具栏的刷新按钮。 */
    onRefreshingChange?: (refreshing: boolean) => void
    /** 项目当前选中的 UI 环境；为空时不允许直接运行。 */
    environmentId?: string
    onOpenEnvironments?: () => void
  }
>(function UiTestSuiteSection(
  {
    requirementId,
    requirementIds,
    selectedSprintId,
    sprintOptions,
    requirementOptions,
    sprintName,
    requirementName,
    sprintNameResolver,
    requirementNameResolver,
    onCreateSprintChange,
    keyword = '',
    onClearKeyword,
    onRefreshingChange,
    environmentId = '',
    onOpenEnvironments,
  },
  ref,
) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingSuite, setEditingSuite] = useState<UiTestSuite | null>(null)
  const [form] = Form.useForm<UiTestSuiteFormValues>()

  const suitesQuery = useQuery({
    queryKey: ['uiTestSuites', requirementId ?? requirementIds?.join(',') ?? ''],
    queryFn: async () => {
      if (requirementId) {
        const suites = await api.getUiTestSuites(requirementId)
        return suites.map((suite) => ({
          ...suite,
          requirementId: suite.requirementId ?? suite.requirement_id ?? requirementId,
        }))
      }

      if (!requirementIds || requirementIds.length === 0) return []

      const suiteGroups = await Promise.all(
        requirementIds.map(async (currentRequirementId) => {
          const suites = await api.getUiTestSuites(currentRequirementId)
          return suites.map((suite) => ({
            ...suite,
            requirementId: suite.requirementId ?? suite.requirement_id ?? currentRequirementId,
          }))
        }),
      )

      return suiteGroups.flat()
    },
    enabled: Boolean(requirementId) || Boolean(requirementIds?.length),
  })
  const suites = useMemo(() => suitesQuery.data ?? [], [suitesQuery.data])
  const resolvedSprintName = sprintName || sprintOptions?.find((item) => item.value === selectedSprintId)?.label || selectedSprintId || '-'
  const resolvedRequirementName =
    requirementName || requirementOptions?.find((item) => item.value === requirementId)?.label || requirementId || '-'

  const orderedSuites = useMemo(
    () =>
      [...suites].sort((left, right) => {
        const leftTime = new Date(pickCreatedAt(left) ?? '').getTime()
        const rightTime = new Date(pickCreatedAt(right) ?? '').getTime()
        return (Number.isNaN(leftTime) ? 0 : leftTime) - (Number.isNaN(rightTime) ? 0 : rightTime)
      }),
    [suites],
  )

  // 测试集数量不多（一个项目一个迭代下的全部），搜索与分页都在前端做，和另外三个列表页一致。
  const filteredSuites = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    if (!text) return orderedSuites
    return orderedSuites.filter((suite) => `${suite.name} ${suite.description ?? ''}`.toLowerCase().includes(text))
  }, [orderedSuites, keyword])

  const pagedSuites = useMemo(
    () => filteredSuites.slice((page - 1) * pageSize, page * pageSize),
    [filteredSuites, page, pageSize],
  )

  const requirementScopeKey = requirementIds?.join(",") ?? ""
  useEffect(() => {
    setPage(1)
  }, [keyword, requirementId, requirementScopeKey, selectedSprintId])


  const saveSuiteMutation = useMutation({
    mutationFn: (values: UiTestSuiteFormValues) => {
      const suiteId = editingSuite ? normalizeUiTestSuiteId(editingSuite) : ''
      if (suiteId && editingSuite) {
        return api.updateUiTestSuite(suiteId, buildUiTestSuiteUpdatePayload(editingSuite, values))
      }
      const targetRequirementId = values.requirementId || requirementId
      if (!targetRequirementId) throw new Error('请选择所属需求')
      return api.createUiTestSuite(targetRequirementId, {
        name: values.name,
        description: values.description,
        ...(values.headless !== undefined ? { headless: values.headless } : {}),
        ...(values.slowMoMs !== undefined ? { slowMoMs: values.slowMoMs } : {}),
        ...(values.viewportWidth !== undefined ? { viewportWidth: values.viewportWidth } : {}),
        ...(values.viewportHeight !== undefined ? { viewportHeight: values.viewportHeight } : {}),
        ...(values.defaultStepTimeoutMs !== undefined ? { defaultStepTimeoutMs: values.defaultStepTimeoutMs } : {}),
        screenshotPolicy: values.screenshotPolicy ?? DEFAULT_UI_TEST_SUITE_RUN_CONFIG.screenshotPolicy,
      })
    },
    onSuccess: (suite) => {
      const suiteId = normalizeUiTestSuiteId(suite)
      message.success(editingSuite ? 'UI测试集已更新' : 'UI测试集已创建')
      setDrawerOpen(false)
      setEditingSuite(null)
      form.resetFields()
      if (suiteId) {
        queryClient.setQueryData(['uiTestSuite', suiteId], suite)
      }
      queryClient.invalidateQueries({ queryKey: ['uiTestSuites'] })
    },
  })

  const deleteSuiteMutation = useMutation({
    mutationFn: (suiteId: string) => api.deleteUiTestSuite(suiteId),
    onSuccess: () => {
      message.success('UI测试集已删除')
      queryClient.invalidateQueries({ queryKey: ['uiTestSuites'] })
    },
  })

  const runSuiteMutation = useMutation({
    mutationFn: (suite: UiTestSuite) => {
      const suiteId = normalizeUiTestSuiteId(suite)
      if (!suiteId) throw new Error('未找到可运行的 UI测试集')
      if (!environmentId) throw new Error('请先选择 UI 环境')
      return api.runUiTestSuite(suiteId, buildUiSuiteRunPayload(environmentId, suite))
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        const missing = (error.data as { missingVariables?: Array<{ name?: string }> } | undefined)
          ?.missingVariables
        const names = Array.from(new Set((missing ?? []).map((item) => item.name).filter(Boolean)))
        if (names.length > 0) {
          message.error(`运行前缺少变量：${names.join('、')}。请在“环境”中补充后再运行。`)
          onOpenEnvironments?.()
          return
        }
      }
      message.error(getErrorMessage(error))
    },
    onSuccess: (runRecord, suite) => {
      const suiteId = normalizeUiTestSuiteId(suite)
      const suiteRunId = getUiSuiteRunId(runRecord)
      if (!suiteRunId) {
        message.error('未获取到运行记录 ID')
        return
      }

      queryClient.setQueryData<UiTestSuiteRunSummary[]>(['uiTestSuiteRuns', suiteId], (current) => {
        const currentItems = current ?? []
        return [runRecord, ...currentItems.filter((item) => item.suiteRunId !== suiteRunId)]
      })

      message.success(isUiSuiteRunPollingStatus(runRecord.status) ? '已开始运行测试集' : '测试集运行记录已创建')
      navigate(`/ui-automation/suites/${suiteId}?suiteRunId=${suiteRunId}`)
    },
  })

  const openCreateDrawer = useCallback(() => {
    setEditingSuite(null)
    form.setFieldsValue({
      sprintId: selectedSprintId,
      requirementId,
      name: '',
      description: '',
      ...DEFAULT_UI_TEST_SUITE_RUN_CONFIG,
    })
    setDrawerOpen(true)
  }, [form, requirementId, selectedSprintId])

  function openEditDrawer(suite: UiTestSuite) {
    setEditingSuite(suite)
    form.setFieldsValue({
      name: suite.name,
      description: suite.description,
      headless: suite.headless ?? DEFAULT_UI_TEST_SUITE_RUN_CONFIG.headless,
      slowMoMs: suite.slowMoMs ?? DEFAULT_UI_TEST_SUITE_RUN_CONFIG.slowMoMs,
      viewportWidth: suite.viewportWidth ?? DEFAULT_UI_TEST_SUITE_RUN_CONFIG.viewportWidth,
      viewportHeight: suite.viewportHeight ?? DEFAULT_UI_TEST_SUITE_RUN_CONFIG.viewportHeight,
      defaultStepTimeoutMs: suite.defaultStepTimeoutMs ?? DEFAULT_UI_TEST_SUITE_RUN_CONFIG.defaultStepTimeoutMs,
      screenshotPolicy: suite.screenshotPolicy ?? DEFAULT_UI_TEST_SUITE_RUN_CONFIG.screenshotPolicy,
    })
    setDrawerOpen(true)
  }

  function openSuiteCasePage(suiteId: string) {
    navigate(`/ui-automation/suites/${suiteId}`)
  }

  function getSuiteRowContext(suite: UiTestSuite) {
    const suiteId = normalizeUiTestSuiteId(suite)
    const suiteDescription = suite.description || '暂无测试集描述'
    const suiteSprintName = sprintNameResolver?.(suite) ?? resolvedSprintName
    const suiteRequirementName = requirementNameResolver?.(suite) ?? resolvedRequirementName

    return { suiteDescription, suiteId, suiteSprintName, suiteRequirementName }
  }

  const columns: TableProps<UiTestSuite>['columns'] = [
    {
      title: '测试集名称',
      dataIndex: 'name',
      key: 'name',
      width: '19%',
      render: (name: UiTestSuite['name']) => <UiSuiteNameCell name={name} />,
    },
    {
      title: '运行配置',
      key: 'runConfig',
      // 23% 在 1600px 最小表宽下约 368px，配合 nowrap 保证三个徽标单行。
      width: '23%',
      render: (_, suite) => <UiSuiteRunConfigCell suite={suite} />,
    },
    {
      title: '所属迭代/需求',
      key: 'scope',
      width: '14%',
      render: (_, suite) => {
        const { suiteRequirementName, suiteSprintName } = getSuiteRowContext(suite)
        return <UiSuiteScopeCell sprintName={suiteSprintName} requirementName={suiteRequirementName} />
      },
    },
    {
      title: '创建时间',
      key: 'createdAt',
      width: '10%',
      render: (_, suite) => (
        <Text className="ui-suite-list-time-cell" type="secondary">
          {formatTime(pickCreatedAt(suite))}
        </Text>
      ),
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: '10%',
      render: (_, suite) => (
        <Text className="ui-suite-list-time-cell" type="secondary">
          {formatTime(pickUpdatedAt(suite))}
        </Text>
      ),
    },
    {
      title: '描述',
      key: 'description',
      width: '16%',
      ellipsis: true,
      render: (_, suite) => {
        const { suiteDescription } = getSuiteRowContext(suite)
        return (
          <Tooltip title={suiteDescription}>
            <Text
              className={`ui-suite-list-desc-cell${suite.description ? '' : ' is-empty'}`}
              type="secondary"
              ellipsis
            >
              {suiteDescription}
            </Text>
          </Tooltip>
        )
      },
    },
    {
      title: <span className="tp-actions-col-title" style={{ width: 92 }}>操作</span>,
      key: 'actions',
      width: '8%',
      align: 'right',
      fixed: 'right',
      render: (_, suite) => {
        const { suiteId } = getSuiteRowContext(suite)
        return (
          <UiSuiteRowActions
            running={runSuiteMutation.isPending && runSuiteMutation.variables === suite}
            runDisabled={!environmentId}
            deleting={deleteSuiteMutation.isPending && deleteSuiteMutation.variables === suiteId}
            onRun={() => runSuiteMutation.mutate(suite)}
            onEdit={() => openEditDrawer(suite)}
            onDelete={() => deleteSuiteMutation.mutate(suiteId)}
          />
        )
      },
    },
  ]

  // 只把「用户点了刷新」这一种情况报给工具栏，首屏加载不点亮刷新按钮的转圈。
  const refresh = useCallback(() => {
    onRefreshingChange?.(true)
    suitesQuery.refetch().finally(() => onRefreshingChange?.(false))
  }, [onRefreshingChange, suitesQuery])

  useImperativeHandle(
    ref,
    () => ({
      openCreateDrawer,
      refresh,
    }),
    [openCreateDrawer, refresh],
  )
  return (
    <div className="ui-test-suite-section">
      {suitesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(suitesQuery.error)} /> : null}

      <div className="ui-suite-list-table-card tp-list-body">
        <div className="table-body-scroll sprint-card-scroll ui-suite-list-table-scroll tp-list-scroll">
          {suitesQuery.isLoading ? (
            <div className="sprint-card-loading">
              <Empty description="UI测试集加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </div>
          ) : filteredSuites.length === 0 ? (
            <div className="sprint-card-loading">
              <Empty
                image={<AppstoreOutlined />}
                description={
                  <Space orientation="vertical" size={4}>
                    <Text strong>{keyword.trim() ? '没有符合搜索条件的 UI测试集' : '当前需求下还没有 UI测试集'}</Text>
                    <Text type="secondary">
                      {keyword.trim()
                        ? '换个关键词，或者清空搜索看全部测试集。'
                        : '支持创建测试集，并进入详情管理用例、步骤与正式运行报告。'}
                    </Text>
                  </Space>
                }
              >
                {keyword.trim() ? (
                  <Button onClick={onClearKeyword}>清空搜索</Button>
                ) : (
                  <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateDrawer}>
                    新建测试集
                  </ProjectActionButton>
                )}
              </Empty>
            </div>
          ) : (
            <Table<UiTestSuite>
              className="functional-suite-list-table tp-list-table ui-suite-list-table"
              columns={columns}
              dataSource={pagedSuites}
              rowKey={(suite) => getSuiteRowContext(suite).suiteId || suite.name}
              pagination={false}
              // 列宽按百分比分配；容器不足 1600px 时改为表格内部横向滚动，避免名称和描述被压成 0 宽。
              tableLayout="fixed"
              scroll={{ x: 1600 }}
              onRow={(suite) => ({
                onClick: () => openSuiteCasePage(getSuiteRowContext(suite).suiteId),
              })}
            />
          )}
        </div>

        <div className="table-footer ui-suite-list-footer">
          <ListPagination loading={suitesQuery.isFetching || suitesQuery.isError}
            current={page}
            pageSize={pageSize}
            total={filteredSuites.length}
            onChange={(nextPage, nextPageSize) => {
              setPage(nextPage)
              setPageSize(nextPageSize)
            }}
          />
        </div>
      </div>

      <UiTestSuiteDrawer
        title={editingSuite ? '编辑 UI测试集' : '新建 UI测试集'}
        open={drawerOpen}
        form={form}
        loading={saveSuiteMutation.isPending}
        error={saveSuiteMutation.error}
        onClose={() => {
          setDrawerOpen(false)
          setEditingSuite(null)
          form.resetFields()
        }}
        sprintOptions={editingSuite ? undefined : sprintOptions}
        requirementOptions={editingSuite ? undefined : requirementOptions}
        onSprintChange={
          editingSuite
            ? undefined
            : (value) => {
                form.setFieldValue('requirementId', undefined)
                onCreateSprintChange?.(value)
              }
        }
        onFinish={(values) => saveSuiteMutation.mutate(values)}
      />
    </div>
  )
})
