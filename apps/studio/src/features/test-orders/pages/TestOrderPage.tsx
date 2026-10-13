import '@/shared/styles/list-table.css'
import { AppstoreOutlined, FileTextOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Empty,
  Input,
  Popconfirm,
  Space,
  Table,
  Tooltip,
  Typography,
} from 'antd'
import type { InputRef, TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
import { buildTestOrderProgress, type TestOrderProgressKey } from '../utils/testOrderProgress'
import '@/shared/styles/surface-tokens.css'
import '@/features/test-orders/styles/index.css'
import '@/features/test-orders/styles/test-orders-v2.css'

const { Text } = Typography

/** 进度条与指标文字用的色调，与条目结论一一对应。 */
const METRIC_TONES: Record<TestOrderProgressKey, string> = {
  passed: 'green',
  failed: 'red',
  blocked: 'amber',
  skipped: 'slate',
}

export function TestOrderPage() {
  const navigate = useNavigate()
  const activeProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const queryClient = useQueryClient()
  const { activeSprintId, sprints, sprintsQuery, sprintSelectorOptions } =
    useActiveSprint()

  const [keyword, setKeyword] = useState('')
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
    queryKey: ['testOrders', activeProjectId, activeSprintId],
    queryFn: () =>
      api.getProjectTestOrders(activeProjectId!, { sprintId: activeSprintId ?? '' }),
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })

  const orders = listItems(ordersQuery.data)
  const visibleOrders = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    return orders.filter((order) => {
      if (!text) return true
      const haystack = `${order.name} ${order.testedVersion ?? ''}`.toLowerCase()
      return haystack.includes(text)
    })
  }, [keyword, orders])

  const currentPage = Math.max(1, Math.min(page, Math.ceil(visibleOrders.length / pageSize) || 1))
  const pageOrders = visibleOrders.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  useEffect(() => { setPage(1) }, [activeProjectId, activeSprintId, keyword])

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

  const columns: TableProps<TestOrder>['columns'] = [
    {
      title: '测试单名称',
      key: 'name',
      width: 145,
      render: (_, order) => (
        <Space size={8} className="tp-list-name functional-suite-list-name test-order-name-cell">
          <span className="test-order-name-icon" aria-hidden="true"><FileTextOutlined /></span>
          <Tooltip title={order.name}>
            <Text ellipsis>{order.name}</Text>
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '所属迭代',
      key: 'sprint',
      width: 125,
      ellipsis: true,
      render: (_, order) => (
        <Text type="secondary" className="test-order-muted-cell">
          {(order.sprintId && sprintNameMap.get(order.sprintId)) || '-'}
        </Text>
      ),
    },
    {
      title: '被测版本',
      key: 'testedVersion',
      width: 125,
      ellipsis: true,
      render: (_, order) => (
        <Text className="test-order-version-cell" type="secondary">
          {order.testedVersion || '-'}
        </Text>
      ),
    },
    {
      title: '进度与指标',
      key: 'progress',
      width: 460,
      render: (_, order) => {
        const progress = buildTestOrderProgress(order)
        return (
          <div className="test-order-progress-cell">
            <div className="test-order-progress-line">
              <span className="test-order-progress-executed">
                已执行{' '}
                <strong>
                  {progress.executed}/{progress.total}
                </strong>
                {progress.metrics.map((metric) => (
                  <span
                    key={metric.key}
                    className={`test-order-progress-metric tone-${METRIC_TONES[metric.key]}`}
                  >
                    {metric.label} {metric.count}
                  </span>
                ))}
              </span>
              <span className={`test-order-progress-percent tone-${getTestOrderStatusTone(order.status)}`}>
                {progress.percent}%
              </span>
            </div>
            {/* 分段进度条是图形，无障碍名用完整的进度文案，和抽屉 / 工作台里的说法一致。 */}
            <div
              className="test-order-progress-track"
              role="img"
              aria-label={formatEntryProgress(order)}
            >
              {progress.segments.map((segment) => (
                <span
                  key={segment.key}
                  className={`test-order-progress-segment segment-${segment.key}`}
                  style={{ width: `${segment.percent}%` }}
                  title={`${segment.label}: ${segment.count}`}
                />
              ))}
            </div>
          </div>
        )
      },
    },
    {
      title: '状态',
      key: 'status',
      width: 150,
      render: (_, order) => {
        const meta = getTestOrderStatusMeta(order.status)
        return (
          <span className={`test-order-status-pill tone-${getTestOrderStatusTone(order.status)}`}>
            <span className="test-order-status-dot" />
            {meta.label}
          </span>
        )
      },
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: 250,
      render: (_, order) => (
        <Text className="functional-suite-list-time test-order-time-cell" type="secondary">
          {formatTime(pickUpdatedAt(order))}
        </Text>
      ),
    },
    {
      title: <span className="tp-actions-col-title" style={{ width: 64 }}>操作</span>,
      key: 'actions',
      width: 102,
      align: 'right',
      render: (_, order) => (
        <Space
          size={8}
          className="functional-suite-list-actions test-order-row-actions"
          onClick={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
        >
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
        </Space>
      ),
    },
  ]

  function openCreateDrawer() {
    setEditingOrder(null)
    setDrawerOpen(true)
  }

  const hasLocalFilters = Boolean(keyword.trim())

  return (
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface test-orders-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board tp-list-panel">
          <div className="panel-header api-panel-header test-orders-toolbar tp-list-toolbar">
            <div className="api-filter-group test-orders-filters">
              <h1 className="tp-list-title">测试单</h1>
              <div className="api-filter-field test-orders-search-field">
                <Input
                  ref={keywordInputRef}
                  className="api-filter-input test-orders-search-input"
                  allowClear
                  prefix={<SearchOutlined />}
                  suffix={<button type="button" className="test-orders-search-submit" onClick={() => { setPage(1); keywordInputRef.current?.focus() }}>搜索</button>}
                  placeholder="搜索测试单名称 / 被测版本"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
              </div>
            </div>

            <Space size={8} className="test-orders-toolbar-actions tp-refresh-actions">
              <Tooltip title="刷新测试单列表">
                <ProjectActionButton
                  action="read"
                  type="text"
                  shape="circle"
                  className="action-btn-read test-orders-refresh"
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

          {sprintsQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} />
          ) : null}
          {ordersQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(ordersQuery.error)} />
          ) : null}

          {!activeProjectId ? (
            <div className="sprint-card-loading">
              <Empty description="请先选择项目" />
            </div>
          ) : !sprintsQuery.isLoading && sprints.length === 0 ? (
            <div className="sprint-card-loading">
              <Empty description="当前项目下暂无迭代" />
            </div>
          ) : (
            <>
              <div className="test-orders-table-card tp-list-body">
                <div className="table-body-scroll sprint-card-scroll functional-suite-scroll test-orders-table-scroll tp-list-scroll">
                  {ordersQuery.isLoading ? (
                    <div className="sprint-card-loading">
                      <Empty description="测试单加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    </div>
                  ) : visibleOrders.length === 0 ? (
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
                              setKeyword('')
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
                    <Table<TestOrder>
                      className="functional-suite-list-table tp-list-table"
                      columns={columns}
                      dataSource={pageOrders}
                      rowKey={(order) => order.orderId ?? order.name}
                      pagination={false}
                      scroll={{ x: 1200 }}
                      onRow={(order) => ({
                        onClick: (event) => {
                          if (
                            (event.target as HTMLElement).closest(
                              '.ant-table-selection-column, .functional-suite-list-actions',
                            )
                          ) {
                            return
                          }
                          if (order.orderId) navigate(`/test-orders/${order.orderId}`)
                        },
                      })}
                    />
                  )}
                </div>
                <div className="table-footer test-orders-footer">
                  <ListPagination current={currentPage} pageSize={pageSize} total={visibleOrders.length}
                    loading={ordersQuery.isFetching} onChange={(next, size) => { setPage(next); setPageSize(size) }} />
                </div>
              </div>
            </>
          )}
        </section>
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
