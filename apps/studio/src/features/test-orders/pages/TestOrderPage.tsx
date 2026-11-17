import { AppstoreOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Empty,
  Popconfirm,
  Space,
  Tooltip,
  Typography,
} from 'antd'
import type { InputRef } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { DebouncedSearchInput } from '@/shared/components/DebouncedSearchInput'
import { EntityCard } from '@/shared/components/EntityCard'
import { ListSurface } from '@/shared/components/ListSurface'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { api, listItems, type TestOrder } from '@/services/api'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { ListPagination } from '@/shared/components/ListPagination'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage, normalizeSprintId, pickUpdatedAt } from '@/utils/format'
import { TestOrderDrawer } from '../components/TestOrderDrawer'
import {
  formatEntryProgress,
  getTestOrderStatusMeta,
  getTestOrderStatusTone,
} from '../utils/testOrderStatus'
import { buildTestOrderProgress, type TestOrderProgressKey, type TestOrderProgressSegmentKey } from '../utils/testOrderProgress'
import '@/shared/styles/surface-tokens.css'
import '@/features/test-orders/styles/index.css'
import styles from '../styles/test-orders-list.module.css'

const { Text } = Typography

/** 进度条与指标文字用的色调，与条目结论一一对应。 */
const METRIC_TONES: Record<TestOrderProgressKey, string> = {
  passed: 'green',
  failed: 'red',
  blocked: 'amber',
  skipped: 'slate',
}

const SEGMENT_STYLES: Record<TestOrderProgressSegmentKey, string> = {
  passed: styles.segmentPassed,
  failed: styles.segmentFailed,
  blocked: styles.segmentBlocked,
  skipped: styles.segmentSkipped,
  pending: styles.segmentPending,
}

export function TestOrderPage() {
  const navigate = useNavigate()
  const activeProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const queryClient = useQueryClient()
  const { activeSprintId, sprints, sprintsQuery, sprintSelectorOptions } =
    useActiveSprint()

  const [searchKeyword, setSearchKeyword] = useState('')
  const [searchResetKey, setSearchResetKey] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingOrder, setEditingOrder] = useState<TestOrder | null>(null)
  const keywordInputRef = useRef<InputRef>(null)

  const sprintNameMap = useMemo(() => {
    const map = new Map<string, string>()
    sprints.forEach((sprint) => {
      const id = normalizeSprintId(sprint)
      if (id) map.set(id, sprint.name)
    })
    return map
  }, [sprints])

  const ordersQuery = useQuery({
    queryKey: ['testOrders', activeProjectId, activeSprintId, searchKeyword, page, pageSize],
    queryFn: () =>
      api.getProjectTestOrders(activeProjectId!, { sprintId: activeSprintId ?? '', keyword: searchKeyword, page, pageSize }),
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })

  const pageOrders = listItems(ordersQuery.data)
  const total = ordersQuery.data?.total ?? 0
  const currentPage = ordersQuery.data?.page ?? page
  useEffect(() => {
    if (ordersQuery.isSuccess && currentPage !== page) setPage(currentPage)
  }, [ordersQuery.isSuccess, currentPage, page])
  useEffect(() => { setPage(1) }, [activeProjectId, activeSprintId])
  const commitSearch = useCallback((value: string) => {
    setSearchKeyword(value)
    setPage(1)
  }, [])

  // 保留搜索框快捷键：Mac 用 ⌘K，其他平台用 Ctrl+K。
  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey)) return
      // 标签页常驻挂载后，隐藏面板里的搜索框不能抢占快捷键。
      if (keywordInputRef.current?.nativeElement?.closest('[hidden]')) return
      event.preventDefault()
      keywordInputRef.current?.focus()
    }

    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

  const deleteMutation = useMutation({
    mutationFn: (orderId: string) => api.deleteTestOrder(orderId),
    onSuccess: () => {
      message.success('测试单已删除')
      queryClient.invalidateQueries({ queryKey: ['testOrders'] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  function renderOrderCard(order: TestOrder) {
    const progress = buildTestOrderProgress(order)
    const statusMeta = getTestOrderStatusMeta(order.status)
    const orderId = order.orderId

    const title = orderId ? (
      <Link
        to={`/test-orders/${orderId}`}
        title={order.name}
        onClick={() => queryClient.setQueryData(['testOrder', orderId], order)}
      >
        {order.name}
      </Link>
    ) : order.name

    return (
      <EntityCard
        key={orderId ?? order.name}
        title={title}
        status={
          <span className={`${styles.statusPill} tone-${getTestOrderStatusTone(order.status)}`}>
            <span className={styles.statusDot} />
            {statusMeta.label}
          </span>
        }
        meta={[
          {
            label: '所属迭代',
            value: (order.sprintId && sprintNameMap.get(order.sprintId)) || '-',
          },
          { label: '被测版本', value: order.testedVersion || '-' },
        ]}
        footerNote={<>最近更新 {formatTime(pickUpdatedAt(order))}</>}
        actions={
          <>
            <Tooltip title="编辑测试单">
              <ProjectActionButton
                action="write"
                type="text"
                shape="circle"
                className="action-btn-update"
                operation="edit"
                iconOnly
                aria-label="编辑测试单"
                onClick={() => {
                  setEditingOrder(order)
                  setDrawerOpen(true)
                }}
              />
            </Tooltip>
            <Popconfirm
              title="确认删除该测试单？"
              description="删除后不可恢复，其中的执行条目一并删除，用例本身不受影响。"
              okText="确认删除"
              okButtonProps={{ danger: true }}
              onConfirm={() => order.orderId && deleteMutation.mutate(order.orderId)}
            >
              <Tooltip title="删除测试单">
                <ProjectActionButton
                  action="write"
                  type="text"
                  shape="circle"
                  danger
                  className="action-btn-delete"
                  operation="delete"
                  iconOnly
                  aria-label="删除测试单"
                  loading={deleteMutation.isPending && deleteMutation.variables === order.orderId}
                />
              </Tooltip>
            </Popconfirm>
          </>
        }
        onOpen={() => {
          if (!orderId) return
          // 列表行本身就是完整测试单，先写缓存，工作台不必再取一次详情。
          queryClient.setQueryData(['testOrder', orderId], order)
          navigate(`/test-orders/${orderId}`)
        }}
      >
        <div className={styles.progressCell}>
          <div className={styles.progressLine}>
            <span className={styles.progressExecuted}>
              已执行{' '}
              <strong>
                {progress.executed}/{progress.total}
              </strong>
              {progress.metrics.map((metric) => (
                <span
                  key={metric.key}
                  className={`${styles.progressMetric} tone-${METRIC_TONES[metric.key]}`}
                >
                  {metric.label} {metric.count}
                </span>
              ))}
            </span>
            <span className={`${styles.progressPercent} tone-${getTestOrderStatusTone(order.status)}`}>
              {progress.percent}%
            </span>
          </div>
          {/* 分段进度条是图形，无障碍名用完整的进度文案，和抽屉 / 工作台里的说法一致。 */}
          <div
            className={styles.progressTrack}
            role="img"
            aria-label={formatEntryProgress(order)}
          >
            {progress.segments.map((segment) => (
              <span
                key={segment.key}
                className={`${styles.progressSegment} ${SEGMENT_STYLES[segment.key]}`}
                style={{ width: `${segment.percent}%` }}
                title={`${segment.label}: ${segment.count}`}
              />
            ))}
          </div>
        </div>
      </EntityCard>
    )
  }

  function openCreateDrawer() {
    setEditingOrder(null)
    setDrawerOpen(true)
  }

  const hasLocalFilters = Boolean(searchKeyword.trim())

  return (
    <div className={`workbench-page api-automation-page functional-test-page tp-list-surface test-orders-page tp-surface ${styles.root}`}>
      <div className="api-automation-content">
        <ListSurface
          className="test-orders-list-panel"
          bodyClassName="test-orders-card-body"
          scrollClassName="sprint-card-scroll test-orders-card-scroll"
          toolbar={
            <div className="panel-header api-panel-header tp-list-toolbar">
              <div className="api-filter-group flex flex-wrap items-center gap-2">
                <h1 className="tp-list-title">测试单</h1>
                <div className={`api-filter-field ${styles.searchField}`}>
                  <DebouncedSearchInput
                    inputRef={keywordInputRef}
                    className="api-filter-input test-orders-search-input"
                    prefix={<SearchOutlined />}
                    suffix={<button type="button" className={styles.searchSubmit} onClick={() => { setPage(1); keywordInputRef.current?.focus() }}>搜索</button>}
                    placeholder="搜索测试单名称 / 被测版本"
                    ariaLabel="搜索测试单名称 / 被测版本"
                    resetKey={searchResetKey}
                    onCommit={commitSearch}
                  />
                </div>
              </div>

              <Space size={8} className="flex-none items-center tp-refresh-actions">
                <Tooltip title="刷新测试单列表">
                  <ProjectActionButton
                    action="read"
                    type="text"
                    shape="circle"
                    className="action-btn-read"
                    operation="refresh"
                    icon={<ReloadOutlined />}
                    iconOnly
                    aria-label="刷新测试单列表"
                    loading={ordersQuery.isFetching}
                    onClick={() => ordersQuery.refetch()}
                  />
                </Tooltip>
                <ProjectActionButton
                  action="write"
                  type="primary"
                  operation="create"
                  iconOnly
                  disabled={!activeProjectId || sprints.length === 0}
                  onClick={openCreateDrawer}
                >
                  新建测试单
                </ProjectActionButton>
              </Space>
            </div>
          }
          notices={
            <>
              {sprintsQuery.error ? (
                <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} />
              ) : null}
              {ordersQuery.error ? (
                <Alert showIcon type="error" title={getErrorMessage(ordersQuery.error)} />
              ) : null}
            </>
          }
          footer={activeProjectId && (sprintsQuery.isLoading || sprints.length > 0) && ordersQuery.data ? (
            <ListPagination current={currentPage} pageSize={pageSize} total={total}
              loading={ordersQuery.isFetching} onChange={(next, size) => { setPage(next); setPageSize(size) }} />
          ) : undefined}
        >
          {!activeProjectId ? (
            <div className="sprint-card-loading">
              <Empty description="请先选择项目" />
            </div>
          ) : !sprintsQuery.isLoading && sprints.length === 0 ? (
            <div className="sprint-card-loading">
              <Empty description="当前项目下暂无迭代" />
            </div>
          ) : ordersQuery.isLoading ? (
            <div className="sprint-card-loading">
              <Empty description="测试单加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </div>
          ) : total === 0 ? (
            <div className="sprint-card-loading">
              <Empty
                image={<AppstoreOutlined />}
                description={
                  <Space orientation="vertical" size={4}>
                    <Text strong>
                      {hasLocalFilters ? '没有符合筛选条件的测试单' : '当前迭代下还没有测试单'}
                    </Text>
                    <Text type="secondary">
                      {hasLocalFilters
                        ? '调整或清空筛选条件后再看。'
                        : '新建测试单后，从用例库挑选用例加入即可开始执行。'}
                    </Text>
                  </Space>
                }
              >
                {hasLocalFilters ? (
                  <Button
                    onClick={() => {
                      setSearchResetKey((current) => current + 1)
                      setSearchKeyword('')
                      setPage(1)
                    }}
                  >
                    清空筛选
                  </Button>
                ) : (
                  <ProjectActionButton
                    action="write"
                    type="primary"
                    className="action-btn-create"
                    operation="create"
                    disabled={!activeProjectId || sprints.length === 0}
                    onClick={openCreateDrawer}
                  >
                    新建测试单
                  </ProjectActionButton>
                )}
              </Empty>
            </div>
          ) : (
            <div className="entity-card-grid">
              {pageOrders.map(renderOrderCard)}
            </div>
          )}
        </ListSurface>
      </div>

      <TestOrderDrawer
        open={drawerOpen}
        order={editingOrder}
        projectId={activeProjectId}
        sprintOptions={sprintSelectorOptions.filter((option) => option.value !== 'all')}
        defaultSprintId={activeSprintId}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  )
}
