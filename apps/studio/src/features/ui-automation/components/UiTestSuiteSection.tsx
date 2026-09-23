import { footerRange } from '@/shared/utils/pagination'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { AppstoreOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Form, Pagination, Space, Table, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { UiSuiteNameCell, UiSuiteRowActions, UiSuiteScopeCell } from './UiSuiteListCells'
import { UiSuiteRunConfigCell } from './UiSuiteRunConfigCell'
import { UiTestSuiteDrawer, type UiTestSuiteFormValues } from './UiTestSuiteDrawer'
import { DEFAULT_UI_TEST_SUITE_RUN_CONFIG } from '../constants/defaultRunConfig'
import { buildUiSuiteRunPayload } from '../utils/runHelpers'
import { api, type UiTestSuite, type UiTestSuiteRunSummary } from '@/services/api'
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
  },
  ref,
) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
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

  useEffect(() => {
    setPage(1)
  }, [keyword])

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(filteredSuites.length / pageSize))
    if (page > maxPage) setPage(maxPage)
  }, [filteredSuites.length, page, pageSize])

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
      return api.runUiTestSuite(suiteId, buildUiSuiteRunPayload(suite))
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
      width: '26%',
      render: (name: UiTestSuite['name']) => <UiSuiteNameCell name={name} />,
    },
    {
      title: '所属迭代/需求',
      key: 'scope',
      width: 200,
      render: (_, suite) => {
        const { suiteRequirementName, suiteSprintName } = getSuiteRowContext(suite)
        return <UiSuiteScopeCell sprintName={suiteSprintName} requirementName={suiteRequirementName} />
      },
    },
    {
      title: '创建时间',
      key: 'createdAt',
      width: 168,
      render: (_, suite) => (
        <Text className="ui-suite-list-time-cell" type="secondary">
          {formatTime(pickCreatedAt(suite))}
        </Text>
      ),
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: 168,
      render: (_, suite) => (
        <Text className="ui-suite-list-time-cell" type="secondary">
          {formatTime(pickUpdatedAt(suite))}
        </Text>
      ),
    },
    {
      title: '运行配置',
      key: 'runConfig',
      // 320 是三个徽标（可视 / 视口 / 超时 + 截图策略）能排成一行所需的宽度，再窄「每个步骤后截图」会换行。
      width: 320,
      render: (_, suite) => <UiSuiteRunConfigCell suite={suite} />,
    },
    {
      title: '描述',
      key: 'description',
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
      title: '操作',
      key: 'actions',
      width: 138,
      align: 'right',
      render: (_, suite) => {
        const { suiteId } = getSuiteRowContext(suite)
        return (
          <UiSuiteRowActions
            running={runSuiteMutation.isPending && runSuiteMutation.variables === suite}
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

      <div className="ui-suite-list-table-card">
        <div className="table-body-scroll sprint-card-scroll ui-suite-list-table-scroll">
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
              className="functional-suite-list-table ui-suite-list-table"
              columns={columns}
              dataSource={pagedSuites}
              rowKey={(suite) => getSuiteRowContext(suite).suiteId || suite.name}
              pagination={false}
              onRow={(suite) => ({
                onClick: () => openSuiteCasePage(getSuiteRowContext(suite).suiteId),
              })}
            />
          )}
        </div>

        <div className="table-footer ui-suite-list-footer">
          <Text type="secondary">{footerRange(filteredSuites.length, page, pageSize)}</Text>
          <Pagination
            current={page}
            pageSize={pageSize}
            total={filteredSuites.length}
            showSizeChanger
            pageSizeOptions={['10', '20', '30', '50']}
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
