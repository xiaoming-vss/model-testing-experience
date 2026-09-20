import { ArrowLeftOutlined, SearchOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { AddCasesFromLibraryModal } from '../components/AddCasesFromLibraryModal'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { priorityColor } from '@/features/test-cases/utils/casePriority'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import {
  getTestOrderEntryDotColor,
  getTestOrderEntryStatusMeta,
  getTestOrderStatusMeta,
} from '../utils/testOrderStatus'
import '@/features/test-orders/styles/index.css'

const { Text } = Typography

// 执行针对整条用例：一次判定给出这条用例的结论。
const VERDICT_OPTIONS: Array<{ value: string; label: string; className: string }> = [
  { value: 'passed', label: '通过', className: 'on-ok' },
  { value: 'failed', label: '失败', className: 'on-bad' },
  { value: 'blocked', label: '阻塞', className: 'on-block' },
  { value: 'skipped', label: '跳过', className: 'on-skip' },
]

const STATUS_FILTERS: Array<{ value: string; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'pending', label: '未执行' },
  { value: 'failed', label: '失败' },
  { value: 'blocked', label: '阻塞' },
]

export function TestOrderWorkspacePage() {
  const { orderId } = useParams<{ orderId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const currentUserId = useAuthStore((state) => state.user?.userId)

  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null)
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [onlyMine, setOnlyMine] = useState(false)
  const [autoAdvance, setAutoAdvance] = useState(true)
  const [checkedEntryIds, setCheckedEntryIds] = useState<string[]>([])
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [savedAt, setSavedAt] = useState<string>('')
  const [assignOpen, setAssignOpen] = useState(false)
  const [assignee, setAssignee] = useState('')
  const [addCasesOpen, setAddCasesOpen] = useState(false)

  const orderQuery = useQuery({
    queryKey: ['testOrder', orderId],
    queryFn: () => api.getTestOrder(orderId!),
    enabled: Boolean(orderId),
  })
  const order = orderQuery.data
  const { project, can } = useProjectAccess(order?.projectId)

  const entriesQuery = useQuery({
    queryKey: ['testOrderEntries', orderId],
    queryFn: () => api.getTestOrderEntries(orderId!),
    enabled: Boolean(orderId),
  })

  const membersQuery = useQuery({
    queryKey: ['projectMembers', order?.projectId],
    queryFn: () => api.getProjectMembers(order!.projectId!),
    enabled: Boolean(order?.projectId),
  })
  const memberNameMap = useMemo(() => {
    const map = new Map<string, string>()
    listItems(membersQuery.data).forEach((member) => map.set(member.userId, member.name))
    return map
  }, [membersQuery.data])
  const personName = (userId?: string) =>
    userId ? memberNameMap.get(userId) ?? userId : ''
  const entries = listItems(entriesQuery.data)

  const entriesReloaded = entriesQuery.dataUpdatedAt

  const visibleEntries = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    return entries.filter((entry) => {
      if (onlyMine && entry.assigneeUserId !== currentUserId) return false
      if (statusFilter !== 'all' && (entry.status ?? '') !== statusFilter) return false
      if (!text) return true
      return `${entry.caseTitle ?? ''} ${entry.caseModule ?? ''}`.toLowerCase().includes(text)
    })
  }, [currentUserId, entries, keyword, onlyMine, statusFilter])

  const mineCount = entries.filter((entry) => entry.assigneeUserId === currentUserId).length
  const unassignedCount = entries.filter((entry) => !entry.assigneeUserId).length

  const selected = useMemo(
    () => entries.find((entry) => entry.entryId === selectedEntryId) ?? visibleEntries[0],
    [entries, selectedEntryId, visibleEntries],
  )

  // 进入工作台或列表刷新后，默认停在第一条未执行条目（中断后继续）。
  useEffect(() => {
    if (!entriesQuery.isSuccess) return
    setSelectedEntryId((current) => {
      if (current && entries.some((entry) => entry.entryId === current)) return current
      const firstPending = entries.find((entry) => entry.status === 'pending') ?? entries[0]
      return firstPending?.entryId ?? null
    })
  }, [entries, entriesQuery.isSuccess, entriesReloaded])

  useEffect(() => {
    if (!selected) return
    setDrafts({
      reason: (selected.status === 'blocked' ? selected.blockReason : selected.failureReason) ?? '',
      zentaoBugId: selected.zentaoBugId ?? '',
    })
  }, [selected, selected?.entryId])

  const saveMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.updateTestOrderEntry(orderId!, selected!.entryId!, payload),
    onSuccess: () => {
      setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5))
      queryClient.invalidateQueries({ queryKey: ['testOrderEntries', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrder', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrders'] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const batchMutation = useMutation({
    mutationFn: () => api.batchMarkPassedEntries(orderId!, checkedEntryIds),
    onSuccess: (result) => {
      message.success(
        `已标记通过 ${result?.markedCount ?? 0} 条${
          result?.skippedCount ? `，${result.skippedCount} 条已有结论被跳过` : ''
        }`,
      )
      setCheckedEntryIds([])
      queryClient.invalidateQueries({ queryKey: ['testOrderEntries', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrder', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrders'] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const removeMutation = useMutation({
    mutationFn: (entryId: string) => api.deleteTestOrderEntry(orderId!, entryId),
    onSuccess: () => {
      message.success('执行条目已移除')
      setCheckedEntryIds([])
      queryClient.invalidateQueries({ queryKey: ['testOrderEntries', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrder', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrders'] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const assignMutation = useMutation({
    mutationFn: () => api.assignTestOrderEntries(orderId!, checkedEntryIds, assignee),
    onSuccess: () => {
      message.success(assignee ? '已分配执行人' : '已取消分配')
      setAssignOpen(false)
      setCheckedEntryIds([])
      queryClient.invalidateQueries({ queryKey: ['testOrderEntries', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrder', orderId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  function save(payload: Record<string, unknown>) {
    if (!selected?.entryId) return
    saveMutation.mutate(payload)
  }

  const isOwner = project?.role === 'owner'
  const lockedByAssignee =
    Boolean(selected?.assigneeUserId) && selected?.assigneeUserId !== currentUserId && !isOwner
  const canJudge = can('execute') && !lockedByAssignee

  function moveSelection(offset: number) {
    const index = visibleEntries.findIndex((entry) => entry.entryId === selected?.entryId)
    if (index < 0) return
    const next = visibleEntries[index + offset]
    if (next) setSelectedEntryId(next.entryId ?? null)
  }

  // 判定后自动前进到下一条未执行（可在头部关闭）。
  const advanceAfterJudge = autoAdvance && selected?.status !== 'pending'
  useEffect(() => {
    if (!advanceAfterJudge) return
    const index = visibleEntries.findIndex((entry) => entry.entryId === selected?.entryId)
    const next = visibleEntries.slice(index + 1).find((entry) => entry.status === 'pending')
    if (next) setSelectedEntryId(next.entryId ?? null)
  }, [advanceAfterJudge, selected?.entryId, visibleEntries])

  // 键盘：1/2/3/4 判定整条用例，上下切换条目。
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        moveSelection(1)
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        moveSelection(-1)
        return
      }
      const byKey: Record<string, string> = {
        '1': 'passed',
        '2': 'failed',
        '3': 'blocked',
        '4': 'skipped',
      }
      const status = byKey[event.key]
      if (!status || !canJudge) return
      event.preventDefault()
      save({ status })
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  const isSaving = saveMutation.isPending
  const saveStateText = isSaving ? '保存中…' : savedAt ? `已保存 ${savedAt}` : ''
  const entryStatusMeta = getTestOrderEntryStatusMeta(selected?.status)
  const orderStatusMeta = order ? getTestOrderStatusMeta(order.status) : null

  return (
    <div className="workbench-page api-automation-page functional-suite-detail-page">
      <div className="api-automation-content">
        <div className="page-frame test-order-workspace">
          <section className="workbench-panel test-order-orderbar">
            <Button
              type="text"
              className="api-case-back-button"
              aria-label="返回测试单列表"
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate('/testing?tab=orders')}
            />
            <Text strong className="test-order-orderbar-name">
              {order?.name ?? '测试单'}
            </Text>
            {order?.testedVersion ? <Tag>被测版本 {order.testedVersion}</Tag> : null}
            {orderStatusMeta ? <Tag color={orderStatusMeta.color}>{orderStatusMeta.label}</Tag> : null}
            <Text type="secondary">
              已执行 {order?.entriesExecuted ?? 0}/{order?.entriesTotal ?? 0}
            </Text>
            <span className="spacer" />
            <ProjectActionButton
              action="write"
              projectId={order?.projectId}
              type="primary"
              className="action-btn-create"
              operation="create"
              disabled={!order?.orderId}
              onClick={() => setAddCasesOpen(true)}
            >
              加入用例
            </ProjectActionButton>
            <Checkbox checked={autoAdvance} onChange={(event) => setAutoAdvance(event.target.checked)}>
              判定后自动前进
            </Checkbox>
            {saveStateText ? (
              <Text type={saveMutation.isError ? 'danger' : 'secondary'}>{saveStateText}</Text>
            ) : null}
          </section>

          {orderQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(orderQuery.error)} />
          ) : null}
          {entriesQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(entriesQuery.error)} />
          ) : null}

          <div className="test-order-workspace-cols">
            <section className="workbench-panel api-case-sidebar">
              <div className="panel-header api-case-sidebar-header">
                <Text strong>执行条目</Text>
                <Text type="secondary">{entries.length}</Text>
              </div>
              <div className="api-case-sidebar-toolbar test-order-sidebar-toolbar">
                <Input
                  allowClear
                  prefix={<SearchOutlined />}
                  placeholder="搜索用例名称 / 模块"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
                <div className="test-order-status-filters">
                  {STATUS_FILTERS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`test-order-filter-chip${
                        statusFilter === option.value ? ' active' : ''
                      }`}
                      onClick={() => setStatusFilter(option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <Space size={12} wrap>
                  <Checkbox checked={onlyMine} onChange={(event) => setOnlyMine(event.target.checked)}>
                    只看我负责的
                  </Checkbox>
                  <Text type="secondary">
                    我负责 {mineCount} · 未分配 {unassignedCount}
                  </Text>
                </Space>
              </div>
              <div className="api-case-sidebar-scroll">
                {entriesQuery.isLoading ? (
                  <Empty description="执行条目加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : visibleEntries.length === 0 ? (
                  <Empty description="没有符合筛选条件的条目" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <div className="api-case-nav-list">
                    {visibleEntries.map((entry) => {
                      const meta = getTestOrderEntryStatusMeta(entry.status)
                      const active = entry.entryId === selected?.entryId
                      return (
                        <div
                          key={entry.entryId ?? entry.orderNo}
                          className={`test-order-nav-row${active ? ' active' : ''}`}
                        >
                          <Checkbox
                            checked={checkedEntryIds.includes(entry.entryId ?? '')}
                            onChange={(event) =>
                              setCheckedEntryIds((prev) =>
                                event.target.checked
                                  ? [...prev, entry.entryId ?? '']
                                  : prev.filter((id) => id !== entry.entryId),
                              )
                            }
                          />
                          <span
                            className="test-order-nav-dot"
                            style={{ background: getTestOrderEntryDotColor(entry.status) }}
                          />
                          <button
                            type="button"
                            className="test-order-nav-item"
                            aria-current={active}
                            onClick={() => setSelectedEntryId(entry.entryId ?? null)}
                          >
                            <span className="test-order-nav-index">{entry.orderNo ?? '-'}</span>
                            <span className="test-order-nav-body">
                              <span className="test-order-nav-title">
                                {entry.caseTitle || entry.caseId}
                              </span>
                              <span className="test-order-nav-meta">
                                <Tag color={meta.color}>{meta.label}</Tag>
                                <span>{personName(entry.assigneeUserId) || '未分配'}</span>
                              </span>
                            </span>
                          </button>
                          <Popconfirm
                            title="确认移除该执行条目？"
                            description="移除后条目及其结果不再保留，用例本身不受影响。"
                            okText="确认移除"
                            okButtonProps={{ danger: true }}
                            onConfirm={() => entry.entryId && removeMutation.mutate(entry.entryId)}
                          >
                            <button
                              type="button"
                              className="test-order-nav-remove"
                              aria-label={`移除第 ${entry.orderNo ?? ''} 条执行条目`}
                            >
                              ✕
                            </button>
                          </Popconfirm>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
              <div className="test-order-sidebar-foot">
      <Popconfirm
        title={`确认将选中的 ${checkedEntryIds.length} 条标记为通过？`}
        okText="确认标记"
        onConfirm={() => batchMutation.mutate()}
        disabled={checkedEntryIds.length === 0}
      >
        <Button
          className="action-btn-save"
          disabled={checkedEntryIds.length === 0}
          loading={batchMutation.isPending}
        >
          批量标记通过{checkedEntryIds.length > 0 ? `（${checkedEntryIds.length}）` : ''}
        </Button>
      </Popconfirm>
      <ProjectActionButton
        action="manage"
        className="action-btn-update"
        operation="edit"
        disabled={checkedEntryIds.length === 0}
        onClick={() => {
          setAssignee('')
          setAssignOpen(true)
        }}
      >
        分配执行人{checkedEntryIds.length > 0 ? `（${checkedEntryIds.length}）` : ''}
      </ProjectActionButton>
              </div>
            </section>

            <section className="workbench-panel test-order-panel">
              {!selected ? (
                <div className="sprint-card-loading">
                  <Empty description="请先加入执行条目">
                    <ProjectActionButton
                      action="write"
                      projectId={order?.projectId}
                      type="primary"
                      className="action-btn-create"
                      operation="create"
                      disabled={!order?.orderId}
                      onClick={() => setAddCasesOpen(true)}
                    >
                      加入用例
                    </ProjectActionButton>
                  </Empty>
                </div>
              ) : (
                <>
                  <div className="test-order-editor-head">
                    <Text strong className="test-order-case-title">
                      {selected.caseTitle || selected.caseId}
                    </Text>
                    <Tag color={entryStatusMeta.color}>{entryStatusMeta.label}</Tag>
                    {selected.casePriority ? (
                      <Tag color={priorityColor(selected.casePriority)}>{selected.casePriority}</Tag>
                    ) : null}
                    <span className="spacer" />
                    {lockedByAssignee ? (
                      <Text type="secondary">该条已分配给其他执行人</Text>
                    ) : null}
                  </div>
                  <div className="test-order-editor-body">
                    <div className="test-order-content">
                    <div className="test-order-block">
                      <Text type="secondary">前置条件</Text>
                      <div className="test-order-preconditions">
                        {(selected.snapshot?.preconditions ?? []).length === 0
                          ? '暂无前置条件'
                          : (selected.snapshot?.preconditions ?? []).map((item, index) => (
                              <div key={index}>{item}</div>
                            ))}
                      </div>
                    </div>

                    {(selected.snapshot?.steps ?? []).map((step, index) => (
                      <div key={index} className="api-case-run-result-row test-order-step">
                        <div className="api-case-run-result-row-title">
                          <span className="test-order-step-no">{index + 1}</span>
                          <span className="test-order-step-action">{step.action}</span>
                        </div>
                        <div className="test-order-step-expect">预期：{step.expected}</div>
                      </div>
                    ))}
                    </div>
                  </div>
                </>
              )}
            </section>

            <section className="workbench-panel test-order-side">
              {!selected ? null : (
                <>
                  <div className="test-order-side-section">
                    <Text type="secondary">用例结论</Text>
                    <span className="test-order-judge">
                      {VERDICT_OPTIONS.map((option) => (
                        <Tooltip
                          key={option.value}
                          title={canJudge ? undefined : '当前不可判定：条目已分配给其他执行人'}
                        >
                          <button
                            type="button"
                            className={`test-order-judge-btn${
                              selected.status === option.value ? ` ${option.className}` : ''
                            }`}
                            disabled={!canJudge}
                            aria-label={`判定该用例为${option.label}`}
                            onClick={() => save({ status: option.value })}
                          >
                            {option.label}
                          </button>
                        </Tooltip>
                      ))}
                    </span>
                  </div>
                  {selected.status === 'failed' || selected.status === 'blocked' ? (
                    <div className="test-order-side-section">
                      <Text type="secondary">
                        {selected.status === 'failed' ? '失败原因' : '阻塞原因'}
                      </Text>
                      <Input.TextArea
                        rows={3}
                        value={drafts.reason ?? ''}
                        disabled={!canJudge}
                        placeholder="填写原因"
                        onChange={(event) =>
                          setDrafts((prev) => ({ ...prev, reason: event.target.value }))
                        }
                        onBlur={() =>
                          save(
                            selected.status === 'failed'
                              ? { failureReason: drafts.reason ?? '' }
                              : { blockReason: drafts.reason ?? '' },
                          )
                        }
                      />
                      {selected.status === 'failed' ? (
                        <>
                          <Text type="secondary">关联缺陷号</Text>
                          <Input
                            value={drafts.zentaoBugId ?? ''}
                            disabled={!canJudge}
                            placeholder="禅道缺陷号（可选）"
                            onChange={(event) =>
                              setDrafts((prev) => ({ ...prev, zentaoBugId: event.target.value }))
                            }
                            onBlur={() => save({ zentaoBugId: drafts.zentaoBugId ?? '' })}
                          />
                        </>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="test-order-side-section">
                    <Text type="secondary">执行信息</Text>
                    <div className="test-order-kv">
                      <span>分配执行人</span>
                      <span>{personName(selected.assigneeUserId) || '未分配'}</span>
                    </div>
                    <div className="test-order-kv">
                      <span>实际执行人</span>
                      <span>{personName(selected.executorUserId) || '-'}</span>
                    </div>
                    <div className="test-order-kv">
                      <span>执行时间</span>
                      <span>{formatTime(selected.executedAt) || '-'}</span>
                    </div>
                  </div>
                  <div className="test-order-side-foot">
                    <Text type="secondary">
                      1 通过 · 2 失败 · 3 阻塞 · 4 跳过 · ↑↓ 切换条目
                    </Text>
                  </div>
                </>
              )}
            </section>
          </div>
        </div>
      </div>

      <Modal
        title="分配执行人"
        open={assignOpen}
        onCancel={() => setAssignOpen(false)}
        onOk={() => assignMutation.mutate()}
        okText="保存"
        okButtonProps={{ className: 'action-btn-save' }}
        confirmLoading={assignMutation.isPending}
        destroyOnHidden
      >
        <Space orientation="vertical" size={10} style={{ width: '100%' }}>
          <Text type="secondary">已选择 {checkedEntryIds.length} 条执行条目。</Text>
          <Select
            style={{ width: '100%' }}
            value={assignee}
            loading={membersQuery.isLoading}
            options={[
              { label: '未分配（谁都可以执行）', value: '' },
              ...listItems(membersQuery.data).map((member) => ({
                label: `${member.name}（${member.role}）`,
                value: member.userId,
              })),
            ]}
            onChange={(value: string) => setAssignee(value)}
          />
        </Space>
      </Modal>

      <AddCasesFromLibraryModal
        open={addCasesOpen}
        orderId={order?.orderId ?? orderId}
        projectId={order?.projectId}
        sprintId={order?.sprintId}
        existingCaseIds={entries.map((entry) => entry.caseId ?? '').filter(Boolean)}
        onClose={() => setAddCasesOpen(false)}
      />
    </div>
  )
}
