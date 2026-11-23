import { ListEmptyState } from '@/shared/components/ListEmptyState'
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
import { SprintFilterSelect } from '@/domain/projects/components/SprintFilterSelect'
import { useSprintFilter } from '@/domain/projects/hooks/useSprintFilter'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { api, listItems, type TestOrder } from '@/services/api'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { ListPagination } from '@/shared/components/ListPagination'
import { message } from '@/shared/utils/feedback'
import { entityCardGridClass } from '@/shared/utils/surfaceClasses'
import { formatTime, getErrorMessage, normalizeSprintId, pickUpdatedAt } from '@/utils/format'
import { TestOrderDrawer } from '../components/TestOrderDrawer'
import {
  formatEntryProgress,
  getTestOrderStatusMeta,
  getTestOrderStatusTone,
} from '../utils/testOrderStatus'
import { buildTestOrderProgress, type TestOrderProgressKey, type TestOrderProgressSegmentKey } from '../utils/testOrderProgress'
import '@/shared/styles/surface-tokens.css'

const { Text } = Typography

/** 进度条与指标文字用的色调，与条目结论一一对应。 */
const METRIC_TONES: Record<TestOrderProgressKey, string> = {
  passed: 'green',
  failed: 'red',
  blocked: 'amber',
  skipped: 'slate',
}

const SEGMENT_STYLES: Record<TestOrderProgressSegmentKey, string> = {
  passed: 'bg-[var(--srf-result-passed)]',
  failed: 'bg-[var(--srf-result-failed)]',
  blocked: 'bg-[var(--srf-result-blocked)]',
  skipped: 'bg-[var(--srf-result-skipped)]',
  pending: 'bg-[var(--srf-track-pending)]',
}

export function TestOrderPage() {
  const navigate = useNavigate()
  const activeProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const queryClient = useQueryClient()
  const sprintFilter = useSprintFilter(activeProjectId, { allowAll: true })
  const { selectedSprintId: activeSprintId, sprints, sprintsQuery, filterOptions: sprintOptions } = sprintFilter

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
    const statusTone = getTestOrderStatusTone(order.status)
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
          <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-[var(--srf-tone-border,var(--srf-card-border))] bg-[var(--srf-tone-bg,var(--srf-chip))] px-2 py-0.5 text-[12px] font-medium leading-4 text-[var(--srf-tone-text,var(--srf-chip-text))] tone-${statusTone}`}>
            <span className={`h-[5px] w-1.5 flex-none rounded-full bg-current${statusTone === 'blue' ? ' animate-[pulse_1.6s_ease-in-out_infinite] motion-reduce:animate-none' : ''}`} />
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
        <div className="progressCell mt-0.5 mb-3 flex min-w-0 flex-col gap-1.5 tabular-nums">
          <div className="progressLine flex min-w-0 items-baseline justify-between gap-3">
            <span className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] leading-4 text-[var(--srf-text-secondary)]">
              已执行{' '}
              <strong className="font-semibold text-[var(--srf-text)]">
                {progress.executed}/{progress.total}
              </strong>
              {progress.metrics.map((metric) => (
                <span
                  key={metric.key}
                  className={`text-[var(--srf-tone-text)] before:text-[var(--srf-text-muted)] before:content-['_·_'] tone-${METRIC_TONES[metric.key]}`}
                >
                  {metric.label} {metric.count}
                </span>
              ))}
            </span>
            <span className={`flex-none text-[12px] font-medium text-[var(--srf-text-secondary)] tone-${statusTone}`}>
              {progress.percent}%
            </span>
          </div>
          {/* 分段进度条是图形，无障碍名用完整的进度文案，和抽屉 / 工作台里的说法一致。 */}
          <div
            className="flex h-[5px] w-full overflow-hidden rounded-full bg-[var(--srf-track)]"
            role="img"
            aria-label={formatEntryProgress(order)}
          >
            {progress.segments.map((segment) => (
              <span
                key={segment.key}
                className={`h-full ${SEGMENT_STYLES[segment.key]}`}
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
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface test-orders-page tp-surface min-w-0">
      <div className="api-automation-content">
        <ListSurface
          className="test-orders-list-panel"
          bodyClassName="test-orders-card-body"
          scrollClassName="flex min-h-0 flex-col p-4 test-orders-card-scroll"
          toolbar={
            <div className="panel-header api-panel-header tp-list-toolbar">
              <div className="api-filter-group flex flex-wrap items-center gap-2">
                <h1 className="tp-list-title">测试单</h1>
                <SprintFilterSelect value={sprintFilter.selectValue} options={sprintFilter.filterOptions}
                  loading={sprintFilter.loading} onChange={sprintFilter.selectSprint} />
                <div className="api-filter-field searchField min-w-0 w-[300px] max-narrow:w-full">
                  <DebouncedSearchInput
                    inputRef={keywordInputRef}
                    className="api-filter-input test-orders-search-input"
                    prefix={<SearchOutlined />}
                    suffix={<button type="button" className="cursor-pointer border-0 bg-transparent px-0.5 font-[inherit] text-[12px] text-[var(--app-shell-text-secondary)] focus-visible:outline-2 focus-visible:outline-[var(--app-accent)]" onClick={() => { setPage(1); keywordInputRef.current?.focus() }}>搜索</button>}
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
            <ListEmptyState description="请先选择项目" />
          ) : !sprintsQuery.isLoading && sprints.length === 0 ? (
            <ListEmptyState description="当前项目下暂无迭代" />
          ) : ordersQuery.isLoading ? (
            <ListEmptyState description="测试单加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : total === 0 ? (
            <ListEmptyState
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
              </ListEmptyState>
          ) : (
            <div className={`entity-card-grid ${entityCardGridClass}`}>
              {pageOrders.map(renderOrderCard)}
            </div>
          )}
        </ListSurface>
      </div>

      <TestOrderDrawer
        open={drawerOpen}
        order={editingOrder}
        projectId={activeProjectId}
        sprintOptions={sprintOptions.filter((option) => option.value !== 'all')}
        defaultSprintId={activeSprintId}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  )
}
