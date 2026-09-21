import { footerRange } from '@/shared/utils/pagination'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { AppstoreOutlined } from '@ant-design/icons'
import { Alert, Empty, Form, Pagination, Popconfirm, Space, Table, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { UiTestSuiteDrawer, type UiTestSuiteFormValues } from './UiTestSuiteDrawer'
import { DEFAULT_UI_TEST_SUITE_RUN_CONFIG, formatUiScreenshotPolicy } from '../constants/defaultRunConfig'
import { buildUiSuiteRunPayload } from '../utils/runHelpers'
import { api, type UiTestSuite, type UiTestSuiteRunSummary } from '@/services/api'
import { formatTime, getErrorMessage, normalizeUiTestSuiteId, pickCreatedAt, pickUpdatedAt } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { buildUiTestSuiteUpdatePayload } from '@/utils/updatePayload'

const { Text } = Typography

function formatSuiteViewport(suite: UiTestSuite) {
  if (!suite.viewportWidth || !suite.viewportHeight) return '-'
  return `${suite.viewportWidth} x ${suite.viewportHeight}`
}

function formatSuiteRunConfig(suite: UiTestSuite) {
  return `${suite.headless === undefined ? '未设置模式' : suite.headless ? '无头' : '可视'} / ${formatSuiteViewport(suite)} / ${suite.defaultStepTimeoutMs ? `${suite.defaultStepTimeoutMs}ms` : '未设置超时'
  } / ${formatUiScreenshotPolicy(suite.screenshotPolicy)}`
}

export type UiTestSuiteSectionRef = {
  openCreateDrawer: () => void
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
    showInlineCreateButton?: boolean
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
    showInlineCreateButton = true,
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

  const pagedSuites = useMemo(
    () => orderedSuites.slice((page - 1) * pageSize, page * pageSize),
    [orderedSuites, page, pageSize],
  )

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(orderedSuites.length / pageSize))
    if (page > maxPage) setPage(maxPage)
  }, [orderedSuites.length, page, pageSize])

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
    const resolvedSuiteSprintName = sprintNameResolver?.(suite) ?? resolvedSprintName
    const resolvedSuiteRequirementName = requirementNameResolver?.(suite) ?? resolvedRequirementName
    const suiteDescription = suite.description || '暂无测试集描述'
    const suiteScopeText = `${resolvedSuiteSprintName} / ${resolvedSuiteRequirementName}`
    const suiteRunConfig = formatSuiteRunConfig(suite)

    return { suiteDescription, suiteId, suiteRunConfig, suiteScopeText }
  }

  const columns: TableProps<UiTestSuite>['columns'] = [
    {
      title: '测试集名称',
      dataIndex: 'name',
      key: 'name',
      width: '30%',
      render: (name: UiTestSuite['name']) => (
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
      title: '创建时间',
      key: 'createdAt',
      width: 180,
      render: (_, suite) => <Text type="secondary">{formatTime(pickCreatedAt(suite))}</Text>,
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: 180,
      render: (_, suite) => <Text type="secondary">{formatTime(pickUpdatedAt(suite))}</Text>,
    },
    {
      title: '运行配置',
      key: 'runConfig',
      ellipsis: true,
      render: (_, suite) => {
        const { suiteRunConfig } = getSuiteRowContext(suite)
        return (
          <Tooltip title={suiteRunConfig}>
            <Text className="functional-suite-list-meta" type="secondary" ellipsis>
              {suiteRunConfig}
            </Text>
          </Tooltip>
        )
      },
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
            <Tooltip title="运行测试集">
              <ProjectActionButton action="execute"
                type="text"
                shape="circle"
                className="action-btn-read"
                operation="run" iconOnly
                aria-label="运行 UI测试集"
                loading={runSuiteMutation.isPending && runSuiteMutation.variables === suite}
                onClick={() => runSuiteMutation.mutate(suite)}
              />
            </Tooltip>
            <Tooltip title="编辑测试集">
              <ProjectActionButton action="write"
                type="text"
                shape="circle"
                className="action-btn-update"
                operation="edit" iconOnly
                aria-label="编辑 UI测试集"
                onClick={() => openEditDrawer(suite)}
              />
            </Tooltip>
            <Popconfirm title="确认删除该 UI测试集？" onConfirm={() => deleteSuiteMutation.mutate(suiteId)}>
              <Tooltip title="删除测试集">
                <ProjectActionButton action="write"
                  danger
                  type="text"
                  shape="circle"
                  className="action-btn-delete"
                  operation="delete" iconOnly
                  aria-label="删除 UI测试集"
                  loading={deleteSuiteMutation.isPending && deleteSuiteMutation.variables === suiteId}
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        )
      },
    },
  ]

  useImperativeHandle(
    ref,
    () => ({
      openCreateDrawer,
    }),
    [openCreateDrawer],
  )
  return (
    <div className="ui-test-suite-section">
      {showInlineCreateButton ? (
        <div className="ui-test-suite-toolbar">
          <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateDrawer}>
            新建测试集
          </ProjectActionButton>
        </div>
      ) : null}

      {suitesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(suitesQuery.error)} /> : null}

      <div className="table-body-scroll sprint-card-scroll ui-test-suite-scroll">
        {suitesQuery.isLoading ? (
          <div className="sprint-card-loading">
            <Empty description="UI测试集加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        ) : orderedSuites.length === 0 ? (
          <div className="sprint-card-loading">
            <Empty
              image={<AppstoreOutlined />}
              description={
                <Space orientation="vertical" size={4}>
                  <Text strong>当前需求下还没有 UI测试集</Text>
                  <Text type="secondary">支持创建测试集，并进入详情管理用例、步骤与正式运行报告。</Text>
                </Space>
              }
            >
              <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateDrawer}>
                新建测试集
              </ProjectActionButton>
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
