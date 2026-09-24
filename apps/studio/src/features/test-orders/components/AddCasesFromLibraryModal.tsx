import '@/shared/styles/list-table.css'
import '@/shared/styles/surface-tokens.css'
import { SearchOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useProjectRequirements } from '@/features/projects/hooks/useProjectRequirements'
import { priorityColor } from '@/features/test-cases/utils/casePriority'
import { readFunctionCaseContent } from '@/features/test-cases/utils/caseForm'
import { api, listItems, listTotal, type FunctionCaseLibraryItem } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import {
  getErrorMessage,
  normalizeFunctionTestCaseId,
  normalizeFunctionTestSuiteId,
  normalizeRequirementId,
  normalizeSprintId,
} from '@/utils/format'

const { Text } = Typography

const DEFAULT_PAGE_SIZE = 20
/** 每页条数的可选项，上限对齐后端 pageSize 的 le=200。 */
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

/** 下拉里的「全部」选项值，与真实 ID 区分开。 */
const ALL = 'all'

type Props = {
  open: boolean
  orderId?: string
  projectId?: string
  /** 测试单所属迭代：打开时迭代筛选默认落在它上面，仍可切换或选全部。 */
  sprintId?: string
  /** 已在单里的用例，勾选框置灰，避免重复加入。 */
  existingCaseIds?: string[]
  onClose: () => void
  onAdded?: () => void
}

/**
 * 从用例库往当前测试单里挑用例。
 * 选例入口在测试单这一侧：加入后每条会生成执行条目并保存当时的内容快照。
 * 支持按迭代 / 需求 / 测试集 / 关键字筛选，点用例标题可查看用例内容。
 */
export function AddCasesFromLibraryModal({
  open,
  orderId,
  projectId,
  sprintId,
  existingCaseIds = [],
  onClose,
  onAdded,
}: Props) {
  const queryClient = useQueryClient()
  const [sprintFilter, setSprintFilter] = useState(ALL)
  const [requirementFilter, setRequirementFilter] = useState(ALL)
  const [suiteFilter, setSuiteFilter] = useState(ALL)
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  // 每页条数是查看偏好，关掉弹窗再打开仍沿用上次的选择。
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([])
  const [detailItem, setDetailItem] = useState<FunctionCaseLibraryItem | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => {
      setKeyword(keywordInput.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [keywordInput])

  // 每次打开都回到测试单所属迭代、清掉上次的选择，避免跨测试单串筛选。
  useEffect(() => {
    if (!open) return
    setSprintFilter(sprintId ?? ALL)
    setRequirementFilter(ALL)
    setSuiteFilter(ALL)
    setKeywordInput('')
    setKeyword('')
    setPage(1)
    setSelectedCaseIds([])
    setDetailItem(null)
  }, [open, sprintId])

  const sprintsQuery = useQuery({
    queryKey: ['sprints', projectId],
    queryFn: () => api.getSprints(projectId!),
    enabled: open && Boolean(projectId),
  })
  const sprints = useMemo(() => sprintsQuery.data ?? [], [sprintsQuery.data])

  // 需求池按迭代聚合：选中迭代只列该迭代的需求，「全部迭代」时列项目全部需求。
  const { allRequirements, allRequirementsQuery, requirementSprintMap } = useProjectRequirements({
    activeProjectId: projectId,
    enabled: open,
    sprints,
  })

  const suitesQuery = useQuery({
    queryKey: ['testOrderCasePickerSuites', projectId, sprintFilter, requirementFilter],
    queryFn: () =>
      api.getProjectFunctionTestSuites(projectId!, {
        sprintId: sprintFilter === ALL ? '' : sprintFilter,
        requirementId: requirementFilter === ALL ? '' : requirementFilter,
      }),
    enabled: open && Boolean(projectId),
  })
  const suites = listItems(suitesQuery.data)

  const casesQuery = useQuery({
    queryKey: [
      'testOrderCasePicker',
      projectId,
      sprintFilter,
      requirementFilter,
      suiteFilter,
      keyword,
      page,
      pageSize,
    ],
    queryFn: () =>
      api.getProjectFunctionTestCases(projectId!, {
        sprintId: sprintFilter === ALL ? '' : sprintFilter,
        requirementId: requirementFilter === ALL ? '' : requirementFilter,
        suiteId: suiteFilter === ALL ? '' : suiteFilter,
        keyword,
        page,
        pageSize,
      }),
    enabled: open && Boolean(projectId),
  })
  const cases = listItems(casesQuery.data)
  const total = listTotal(casesQuery.data)
  const existingIds = new Set(existingCaseIds.filter(Boolean))

  const addMutation = useMutation({
    mutationFn: () => api.addTestOrderCases(orderId!, selectedCaseIds),
    onSuccess: (result) => {
      const added = result?.addedCount ?? 0
      const skipped = result?.skippedCount ?? 0
      message.success(
        skipped > 0 ? `已加入 ${added} 条用例，${skipped} 条已在测试单中` : `已加入 ${added} 条用例`,
      )
      queryClient.invalidateQueries({ queryKey: ['testOrder', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrderEntries', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrders'] })
      onAdded?.()
      // 保持弹窗与当前筛选、页码，连续挑用例时不必重新筛一遍；加入过的用例会随执行条目刷新变为不可再选。
      setSelectedCaseIds([])
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const sprintOptions = useMemo(
    () => [
      { label: '全部迭代', value: ALL },
      ...sprints.map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) })),
    ],
    [sprints],
  )

  const requirementOptions = useMemo(() => {
    const scoped =
      sprintFilter === ALL
        ? allRequirements
        : allRequirements.filter(
            (requirement) =>
              requirementSprintMap.get(normalizeRequirementId(requirement)) === sprintFilter,
          )
    return [
      { label: '全部需求', value: ALL },
      ...scoped.map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    ]
  }, [allRequirements, requirementSprintMap, sprintFilter])

  const suiteOptions = useMemo(
    () => [
      { label: '全部测试集', value: ALL },
      ...suites.map((suite) => ({ label: suite.name, value: normalizeFunctionTestSuiteId(suite) })),
    ],
    [suites],
  )

  /** 上级筛选变化时清掉下级的选择，避免出现「迭代与需求 / 测试集对不上」的组合。 */
  function handleSprintFilterChange(value: string) {
    setSprintFilter(value)
    setRequirementFilter(ALL)
    setSuiteFilter(ALL)
    setPage(1)
  }

  function handleRequirementFilterChange(value: string) {
    setRequirementFilter(value)
    setSuiteFilter(ALL)
    setPage(1)
  }

  function handleSuiteFilterChange(value: string) {
    setSuiteFilter(value)
    setPage(1)
  }

  const columns: TableProps<FunctionCaseLibraryItem>['columns'] = [
    {
      title: '用例标题',
      key: 'title',
      render: (_, item) => (
        <Tooltip title={`查看用例详情：${item.title}`}>
          <Typography.Link
            className="add-cases-title-link"
            onClick={(event) => {
              event.preventDefault()
              setDetailItem(item)
            }}
          >
            {item.title}
          </Typography.Link>
        </Tooltip>
      ),
    },
    {
      title: '所属测试集',
      key: 'suiteName',
      width: 200,
      ellipsis: true,
      render: (_, item) => <Text type="secondary">{item.suiteName || '-'}</Text>,
    },
    {
      title: '优先级',
      key: 'priority',
      width: 90,
      render: (_, item) =>
        item.priority ? <Tag color={priorityColor(item.priority)}>{item.priority}</Tag> : '-',
    },
  ]

  const detailContent = readFunctionCaseContent(detailItem)
  const detailScopeText = [
    detailItem?.sprintName,
    detailItem?.requirementName,
    detailItem?.suiteName,
  ]
    .filter(Boolean)
    .join(' / ')

  return (
    <Modal
      title="加入用例"
      open={open}
      width={1100}
      centered
      styles={{ body: { maxHeight: 'calc(100vh - 220px)', overflowY: 'auto' } }}
      cancelText="取消"
      okText="加入"
      okButtonProps={{
        className: 'action-btn-save',
        disabled: selectedCaseIds.length === 0,
      }}
      confirmLoading={addMutation.isPending}
      onCancel={onClose}
      onOk={() => addMutation.mutate()}
      destroyOnHidden
    >
      <Space orientation="vertical" size={10} style={{ width: '100%' }}>
        <Text type="secondary">
          已选择 {selectedCaseIds.length} 条用例，加入后会在测试单里生成执行条目并保存当前内容快照。
        </Text>
        <div className="test-order-add-cases-filters">
          <div className="api-filter-field">
            <span className="api-filter-field-label">迭代</span>
            <Select
              className="api-filter-select business-filter-select"
              value={sprintFilter}
              options={sprintOptions}
              loading={sprintsQuery.isLoading}
              placeholder="请选择迭代"
              onChange={handleSprintFilterChange}
            />
          </div>
          <div className="api-filter-field">
            <span className="api-filter-field-label">需求</span>
            <Select
              className="api-filter-select business-filter-select"
              value={requirementFilter}
              options={requirementOptions}
              loading={allRequirementsQuery.isLoading}
              placeholder="请选择需求"
              onChange={handleRequirementFilterChange}
            />
          </div>
          <div className="api-filter-field">
            <span className="api-filter-field-label">测试集</span>
            <Select
              className="api-filter-select business-filter-select"
              value={suiteFilter}
              options={suiteOptions}
              loading={suitesQuery.isLoading}
              placeholder="请选择测试集"
              onChange={handleSuiteFilterChange}
            />
          </div>
          <Input
            className="api-filter-input"
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索用例名称 / 模块"
            value={keywordInput}
            onChange={(event) => setKeywordInput(event.target.value)}
          />
        </div>
        {casesQuery.error ? (
          <Alert showIcon type="error" title={getErrorMessage(casesQuery.error)} />
        ) : null}
        <Table<FunctionCaseLibraryItem>
          className="functional-suite-list-table tp-list-table"
          size="small"
          columns={columns}
          dataSource={cases}
          loading={casesQuery.isLoading}
          rowKey={(item) => normalizeFunctionTestCaseId(item) ?? item.title}
          locale={{
            emptyText: (
              <Empty
                description={keyword ? '没有符合条件的用例' : '这里还没有功能用例'}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ),
          }}
          rowSelection={{
            preserveSelectedRowKeys: true,
            selectedRowKeys: selectedCaseIds,
            onChange: (keys) => setSelectedCaseIds(keys.map(String)),
            getCheckboxProps: (item) => {
              const caseId = normalizeFunctionTestCaseId(item)
              return {
                disabled: !caseId || existingIds.has(caseId),
                'aria-label': `选择用例：${item.title}`,
              }
            },
          }}
          pagination={{
            current: page,
            pageSize,
            total,
            size: 'small',
            showSizeChanger: true,
            pageSizeOptions: PAGE_SIZE_OPTIONS,
            // 全站没有引 antd 的 zh_CN，这里单独把每页条数的文案本地化。
            locale: { items_per_page: '条/页' },
            onChange: (nextPage, nextPageSize) => {
              // 改每页条数时回到第一页，否则页码可能落到新范围之外。
              if (nextPageSize !== pageSize) {
                setPageSize(nextPageSize)
                setPage(1)
                return
              }
              setPage(nextPage)
            },
          }}
        />
      </Space>

      <Modal
        open={Boolean(detailItem)}
        title="用例详情"
        width={720}
        centered
        footer={<Button onClick={() => setDetailItem(null)}>关闭</Button>}
        onCancel={() => setDetailItem(null)}
        destroyOnHidden
      >
        <div className="add-cases-detail">
          <div className="add-cases-detail-meta">
            {detailItem?.priority ? (
              <Tag color={priorityColor(detailItem.priority)}>{detailItem.priority}</Tag>
            ) : null}
            {detailItem?.caseType ? <Tag>{detailItem.caseType}</Tag> : null}
            <Text type="secondary">{detailScopeText || '-'}</Text>
          </div>
          <div className="test-order-block">
            <Text type="secondary">前置条件</Text>
            <div className="test-order-preconditions">
              {detailContent.preconditions.length === 0
                ? '暂无前置条件'
                : detailContent.preconditions.map((item, index) => (
                    <div key={index}>{item}</div>
                  ))}
            </div>
          </div>
          {detailContent.steps.length === 0 ? (
            <Text type="secondary">暂无操作步骤</Text>
          ) : (
            detailContent.steps.map((step, index) => (
              <div key={index} className="api-case-run-result-row test-order-step">
                <div className="api-case-run-result-row-title">
                  <span className="test-order-step-no">{index + 1}</span>
                  <span className="test-order-step-action">{step.action}</span>
                </div>
                <div className="test-order-step-expect">预期：{step.expected}</div>
              </div>
            ))
          )}
        </div>
      </Modal>
    </Modal>
  )
}
