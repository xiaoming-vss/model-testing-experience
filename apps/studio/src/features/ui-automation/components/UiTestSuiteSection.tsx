import { ListEmptyState } from '@/shared/components/ListEmptyState'
import { DEFAULT_PAGE_SIZE, pageSlice } from '@/shared/utils/pagination'
import { ListPagination } from '@/shared/components/ListPagination'
import { EntityCard } from '@/shared/components/EntityCard'
import '@/shared/styles/surface-tokens.css'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { AppstoreOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Form, Space, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { UiSuiteCardActions } from './UiSuiteCardActions'
import { UiSuiteRunConfigCell } from './UiSuiteRunConfigCell'
import { UiTestSuiteDrawer, type UiTestSuiteFormValues } from './UiTestSuiteDrawer'
import { DEFAULT_UI_TEST_SUITE_RUN_CONFIG } from '../constants/defaultRunConfig'
import { buildUiSuiteRunPayload } from '../utils/runHelpers'
import { api, ApiError, listItems, type UiTestSuite, type UiTestSuiteRunSummary } from '@/services/api'
import { formatTime, getErrorMessage, normalizeUiTestSuiteId, pickCreatedAt, pickUpdatedAt } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { entityCardBadgesClass, entityCardDescClass, entityCardDescEmptyClass, entityCardGridClass, tableFooterClass } from '@/shared/utils/surfaceClasses'
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
    projectId?: string
    requirementId?: string
    requirementOptions?: Array<{ label: string; value: string }>
    requirementName?: string
    requirementNameResolver?: (suite: UiTestSuite) => string
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
    projectId,
    requirementId,
    requirementOptions,
    requirementName,
    requirementNameResolver,
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
    queryKey: ['uiTestSuites', projectId ?? '', requirementId ?? 'all'],
    queryFn: async () => {
      if (!projectId) return []
      return listItems(await api.getProjectUiTestSuites(projectId))
    },
    enabled: Boolean(projectId),
  })
  const suites = useMemo(() => {
    const data = suitesQuery.data ?? []
    if (!requirementId) return data
    return data.filter(
      (suite) => suite.requirementId === requirementId,
    )
  }, [requirementId, suitesQuery.data])
  const resolvedRequirementName =
    requirementName ||
    requirementOptions?.find((item) => item.value === requirementId)?.label ||
    (requirementId ? requirementId : '项目级')

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
    () => pageSlice(filteredSuites, page, pageSize),
    [filteredSuites, page, pageSize],
  )

  useEffect(() => {
    setPage(1)
  }, [keyword, requirementId, projectId])


  const saveSuiteMutation = useMutation({
    mutationFn: (values: UiTestSuiteFormValues) => {
      const suiteId = editingSuite ? normalizeUiTestSuiteId(editingSuite) : ''
      if (suiteId && editingSuite) {
        return api.updateUiTestSuite(suiteId, buildUiTestSuiteUpdatePayload(editingSuite, values))
      }
      const targetRequirementId = values.requirementId || requirementId
      const payload = {
        name: values.name,
        description: values.description,
        ...(values.headless !== undefined ? { headless: values.headless } : {}),
        ...(values.slowMoMs !== undefined ? { slowMoMs: values.slowMoMs } : {}),
        ...(values.viewportWidth !== undefined ? { viewportWidth: values.viewportWidth } : {}),
        ...(values.viewportHeight !== undefined ? { viewportHeight: values.viewportHeight } : {}),
        ...(values.defaultStepTimeoutMs !== undefined ? { defaultStepTimeoutMs: values.defaultStepTimeoutMs } : {}),
        screenshotPolicy: values.screenshotPolicy ?? DEFAULT_UI_TEST_SUITE_RUN_CONFIG.screenshotPolicy,
      }
      if (targetRequirementId) return api.createUiTestSuite(targetRequirementId, payload)
      if (!projectId) throw new Error('请先选择项目')
      return api.createProjectUiTestSuite(projectId, payload)
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
      requirementId,
      name: '',
      description: '',
      ...DEFAULT_UI_TEST_SUITE_RUN_CONFIG,
    })
    setDrawerOpen(true)
  }, [form, requirementId])

  function openEditDrawer(suite: UiTestSuite) {
    setEditingSuite(suite)
    form.setFieldsValue({
      requirementId: suite.requirementId ?? undefined,
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
    const suiteRequirementId = suite.requirementId
    const suiteRequirementName = requirementNameResolver?.(suite) ?? resolvedRequirementName

    return { suiteDescription, suiteId, suiteRequirementId, suiteRequirementName }
  }

  function renderSuiteCard(suite: UiTestSuite) {
    const { suiteDescription, suiteId, suiteRequirementId, suiteRequirementName } =
      getSuiteRowContext(suite)
    const title = suiteId ? (
      <Link to={`/ui-automation/suites/${suiteId}`} title={suite.name}>
        {suite.name}
      </Link>
    ) : suite.name

    return (
      <EntityCard
        key={suiteId || suite.name}
        title={title}
        meta={[
          { label: '所属需求', value: suiteRequirementName },
          { label: '范围', value: suiteRequirementId ? '需求关联' : '项目级' },
        ]}
        footerNote={<>最近更新 {formatTime(pickUpdatedAt(suite))}</>}
        actions={
          <UiSuiteCardActions
            running={runSuiteMutation.isPending && runSuiteMutation.variables === suite}
            runDisabled={!environmentId}
            deleting={deleteSuiteMutation.isPending && deleteSuiteMutation.variables === suiteId}
            onRun={() => runSuiteMutation.mutate(suite)}
            onEdit={() => openEditDrawer(suite)}
            onDelete={() => deleteSuiteMutation.mutate(suiteId)}
          />
        }
        onOpen={() => openSuiteCasePage(suiteId)}
      >
        <div className={`entity-card-badges ${entityCardBadgesClass}`}>
          <UiSuiteRunConfigCell suite={suite} />
        </div>
        <p className={`entity-card-desc ${entityCardDescClass}${suite.description ? '' : ` ${entityCardDescEmptyClass}`}`} title={suiteDescription}>
          {suiteDescription}
        </p>
      </EntityCard>
    )
  }

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
    <div className="ui-test-suite-section flex min-h-0 flex-1 flex-col gap-0 overflow-hidden">
      {suitesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(suitesQuery.error)} /> : null}

      <div className="ui-suite-card-body tp-list-body">
        <div className="flex min-h-0 flex-col p-4 ui-suite-card-scroll tp-list-scroll">
          {suitesQuery.isLoading ? (
            <ListEmptyState description="UI测试集加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : filteredSuites.length === 0 ? (
            <ListEmptyState
                image={<AppstoreOutlined />}
                description={
                  <Space orientation="vertical" size={4}>
                    <Text strong>{keyword.trim() ? '没有符合搜索条件的 UI测试集' : '当前项目下还没有 UI测试集'}</Text>
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
              </ListEmptyState>
          ) : (
            <div className={`entity-card-grid ${entityCardGridClass}`}>
              {pagedSuites.map(renderSuiteCard)}
            </div>
          )}
        </div>

        <div className={`table-footer ui-suite-list-footer ${tableFooterClass}`}>
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
        requirementOptions={requirementOptions}
        onFinish={(values) => saveSuiteMutation.mutate(values)}
      />
    </div>
  )
})
