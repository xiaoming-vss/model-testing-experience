import { AppstoreOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Empty,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { api, listItems, type TestOrder } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage, normalizeSprintId, pickUpdatedAt } from '@/utils/format'
import { TestOrderDrawer } from '../components/TestOrderDrawer'
import { formatEntryProgress, getTestOrderStatusMeta } from '../utils/testOrderStatus'
import '@/features/test-orders/styles/index.css'

const { Text } = Typography

const STATUS_FILTER_OPTIONS = [
  { label: '全部状态', value: 'all' },
  { label: '未开始', value: 'pending' },
  { label: '执行中', value: 'in_progress' },
  { label: '已完成', value: 'completed' },
]

export function TestOrderPage() {
  const navigate = useNavigate()
  const activeProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const queryClient = useQueryClient()
  const { activeSprintId, sprints, sprintsQuery, selectSprint, sprintSelectorOptions } =
    useActiveSprint()

  const [status, setStatus] = useState<string | null>(null)
  const [keyword, setKeyword] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingOrder, setEditingOrder] = useState<TestOrder | null>(null)

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
      if (status && (order.status ?? '') !== status) return false
      if (!text) return true
      const haystack = `${order.name} ${order.testedVersion ?? ''}`.toLowerCase()
      return haystack.includes(text)
    })
  }, [keyword, orders, status])

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
      width: '26%',
      render: (_, order) => (
        <Space size={0} className="functional-suite-list-name">
          <Tooltip title={order.name}>
            <Text ellipsis>{order.name}</Text>
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '所属迭代',
      key: 'sprint',
      width: 150,
      ellipsis: true,
      render: (_, order) => (
        <Text type="secondary">
          {(order.sprintId && sprintNameMap.get(order.sprintId)) || '-'}
        </Text>
      ),
    },
    {
      title: '被测版本',
      key: 'testedVersion',
      width: 150,
      ellipsis: true,
      render: (_, order) => <Text type="secondary">{order.testedVersion || '-'}</Text>,
    },
    {
      title: '进度',
      key: 'progress',
      render: (_, order) => (
        <Text type="secondary" className="test-order-progress">
          {formatEntryProgress(order)}
        </Text>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_, order) => {
        const meta = getTestOrderStatusMeta(order.status)
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: 180,
      render: (_, order) => (
        <Text className="functional-suite-list-time" type="secondary">
          {formatTime(pickUpdatedAt(order))}
        </Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 138,
      align: 'right',
      render: (_, order) => (
        <Space
          size={8}
          className="functional-suite-list-actions"
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

  const hasLocalFilters = Boolean(status || keyword.trim())

  return (
    <div className="workbench-page api-automation-page functional-test-page">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel">
          <div className="panel-header api-panel-header">
            <div className="requirement-panel-head">
              <Text strong>测试单</Text>
              <div className="api-filter-group">
                <div className="api-filter-field">
                  <span className="api-filter-field-label">迭代</span>
                  <Select
                    className="api-filter-select business-filter-select"
                    value={activeSprintId ?? 'all'}
                    options={sprintSelectorOptions}
                    loading={sprintsQuery.isLoading}
                    placeholder="请选择迭代"
                    onChange={(value: string) => selectSprint(value === 'all' ? 'all' : value)}
                  />
                </div>
                <div className="api-filter-field">
                  <span className="api-filter-field-label">状态</span>
                  <Select
                    className="api-filter-select business-filter-select"
                    value={status ?? 'all'}
                    options={STATUS_FILTER_OPTIONS}
                    onChange={(value: string) => setStatus(value === 'all' ? null : value)}
                  />
                </div>
                <div className="api-filter-field">
                  <Input
                    className="api-filter-input"
                    allowClear
                    placeholder="搜索测试单名称 / 被测版本"
                    value={keyword}
                    onChange={(event) => setKeyword(event.target.value)}
                  />
                </div>
              </div>
            </div>
            <Space size={8}>
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
            <div className="table-body-scroll sprint-card-scroll functional-suite-scroll">
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
                          setStatus(null)
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
                  className="functional-suite-list-table"
                  columns={columns}
                  dataSource={visibleOrders}
                  rowKey={(order) => order.orderId ?? order.name}
                  pagination={false}
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
          )}

          <div className="table-footer">
            <Text type="secondary">显示第 1 条 - 第 {visibleOrders.length} 条，共 {visibleOrders.length} 条</Text>
          </div>
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
