import {
  ArrowLeftOutlined,
  OrderedListOutlined,
  ApartmentOutlined,
  ProfileOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
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
  Tooltip,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { AddCasesFromLibraryModal } from '../components/AddCasesFromLibraryModal'
import { TestOrderVerdictButtons } from '../components/TestOrderVerdictButtons'
import { useTestOrderEntrySave } from '../hooks/useTestOrderEntrySave'
import { TEST_ORDER_VERDICTS, isTestOrderEntryLocked } from '../utils/testOrderExecution'
import { TestOrderGraphViewer } from '../components/TestOrderGraphViewer'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { priorityTone } from '@/shared/utils/priorityTone'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage } from '@/utils/format'
import {
  getTestOrderEntryStatusMeta,
  getTestOrderEntryStatusTone,
  getTestOrderStatusMeta,
  getTestOrderStatusTone,
} from '../utils/testOrderStatus'
import '@/shared/styles/surface-tokens.css'
import '@/features/test-orders/styles/index.css'
import '@/features/test-orders/styles/workspace-v2.css'
import '@/features/test-orders/styles/workspace-verdict-v2.css'

const { Text } = Typography

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
  const [graphOpen, setGraphOpen] = useState(false)

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

  const matchingEntries = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    return entries.filter((entry) => {
      if (onlyMine && entry.assigneeUserId !== currentUserId) return false
      if (!text) return true
      return `${entry.caseId ?? ''} ${entry.caseTitle ?? ''} ${entry.caseModule ?? ''}`.toLowerCase().includes(text)
    })
  }, [currentUserId, entries, keyword, onlyMine])
  const visibleEntries = useMemo(() => matchingEntries.filter((entry) =>
    statusFilter === 'all' || entry.status === statusFilter,
  ), [matchingEntries, statusFilter])

  const mineCount = entries.filter((entry) => entry.assigneeUserId === currentUserId).length

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

  const saveMutation = useTestOrderEntrySave(orderId ?? '')

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
    saveMutation.mutate({ entryId: selected.entryId, payload }, {
      onSuccess: () => setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5)),
    })
  }

  const isOwner = project?.role === 'owner'
  const lockedByAssignee =
    isTestOrderEntryLocked(selected?.assigneeUserId, currentUserId, isOwner)
  const canJudge = can('execute') && !lockedByAssignee

  function moveSelection(offset: number) {
    const index = visibleEntries.findIndex((entry) => entry.entryId === selected?.entryId)
    if (index < 0) return
    const next = visibleEntries[index + offset]
    if (next) setSelectedEntryId(next.entryId ?? null)
  }

  // 判定后自动前进到下一条未执行（可在底部判定栏关闭）。
  const advanceAfterJudge = !graphOpen && autoAdvance && selected?.status !== 'pending'
  useEffect(() => {
    if (!advanceAfterJudge) return
    const index = visibleEntries.findIndex((entry) => entry.entryId === selected?.entryId)
    const next = visibleEntries.slice(index + 1).find((entry) => entry.status === 'pending')
    if (next) setSelectedEntryId(next.entryId ?? null)
  }, [advanceAfterJudge, selected?.entryId, visibleEntries])

  // 键盘：1/2/3/4 判定整条用例，上下切换条目。
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (graphOpen || saveMutation.isPending) return
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
      const status = TEST_ORDER_VERDICTS.find((option) => option.key === event.key)?.value
      if (!status || !canJudge) return
      event.preventDefault()
      save({ status })
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  const preconditionCount = (selected?.snapshot?.preconditions ?? []).length
  const stepCount = (selected?.snapshot?.steps ?? []).length
  const orderTotal = order?.entriesTotal ?? 0
  const orderExecuted = order?.entriesExecuted ?? 0
  const orderProgressPercent = orderTotal > 0 ? Math.round((orderExecuted / orderTotal) * 100) : 0
  const selectedVisibleIndex = visibleEntries.findIndex((entry) => entry.entryId === selected?.entryId)
  const isSaving = saveMutation.isPending
  const saveStateText = isSaving ? '保存中…' : savedAt ? `已保存 ${savedAt}` : ''
  const entryStatusMeta = getTestOrderEntryStatusMeta(selected?.status)
  const orderStatusMeta = order ? getTestOrderStatusMeta(order.status) : null

  return (
    <div className="workbench-page api-automation-page functional-suite-detail-page test-order-workspace-page tp-surface">
      <div className="api-automation-content">
        <div className="page-frame test-order-workspace tp-board">
          <section className="workbench-panel test-order-orderbar">
            <Button
              type="text"
              className="api-case-back-button"
              aria-label="返回测试单列表"
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate('/testing?tab=orders')}
            />
            <span className="test-order-orderbar-id">
              <Text strong className="test-order-orderbar-name">
                {order?.name ?? '测试单'}
              </Text>
              {order?.testedVersion ? (
                <span className="test-order-orderbar-chip">被测版本 {order.testedVersion}</span>
              ) : null}
              {orderStatusMeta ? (
                <span
                  className={`test-order-orderbar-chip tone-${getTestOrderStatusTone(order?.status)}`}
                >
                  {orderStatusMeta.label}
                </span>
              ) : null}
            </span>
            <span className="test-order-orderbar-progress">
              已执行 {order?.entriesExecuted ?? 0}/{order?.entriesTotal ?? 0}
            </span>
            <div className="test-order-orderbar-actions">
              <ProjectActionButton
                action="execute"
                projectId={order?.projectId}
                className="action-btn-graph"
                icon={<ApartmentOutlined aria-hidden="true" />}
                aria-label="用例图谱"
                disabled={!order?.orderId}
                onClick={() => setGraphOpen(true)}
              >
                用例图谱
              </ProjectActionButton>
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
            </div>
          </section>

          {orderQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(orderQuery.error)} />
          ) : null}
          {entriesQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(entriesQuery.error)} />
          ) : null}

          <div className="test-order-workspace-cols">
            <section className="workbench-panel test-order-side-panel">
              <div className="test-order-side-head">
                <span className="test-order-side-title">
                  执行用例清单
                  <span className="test-order-side-count">{entries.length}</span>
                </span>
                <Tooltip title="刷新执行条目">
                  <Button
                    type="text"
                    size="small"
                    className="test-order-side-refresh"
                    aria-label="刷新执行条目"
                    icon={<ReloadOutlined />}
                    loading={entriesQuery.isFetching}
                    onClick={() => entriesQuery.refetch()}
                  />
                </Tooltip>
              </div>

              <div className="test-order-side-progress">
                <div className="test-order-side-progress-row">
                  <span>执行进度</span>
                  <span>
                    {orderProgressPercent}%（{order?.entriesExecuted ?? 0}/{order?.entriesTotal ?? 0}）
                  </span>
                </div>
                <span className="test-order-side-progress-track">
                  <span
                    className="test-order-side-progress-fill"
                    style={{ width: `${orderProgressPercent}%` }}
                  />
                </span>
              </div>

              <div className="test-order-side-toolbar">
                <Input
                  allowClear
                  prefix={<SearchOutlined />}
                  placeholder="搜索用例 ID 或关键字"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
                <div className="test-order-status-filters">
                  {STATUS_FILTERS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`tp-chip${statusFilter === option.value ? ' active' : ''}`}
                      aria-pressed={statusFilter === option.value}
                      onClick={() => setStatusFilter(option.value)}
                    >
                      {option.label}{' '}
                      <span className="tp-chip-count">
                        {matchingEntries.filter((entry) => option.value === 'all' || entry.status === option.value).length}
                      </span>
                    </button>
                  ))}
                </div>
                <div className="test-order-owner-filter">
                  <Checkbox checked={onlyMine} onChange={(event) => setOnlyMine(event.target.checked)}>
                    只看我负责的
                  </Checkbox>
                  <span>
                    {mineCount}/{entries.length} 指派给我
                  </span>
                </div>
              </div>

              <div className="test-order-side-scroll">
                {entriesQuery.isLoading ? (
                  <Empty description="执行条目加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : visibleEntries.length === 0 ? (
                  <Empty description="没有符合筛选条件的条目" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <div className="api-case-nav-list">
                    {visibleEntries.map((entry) => {
                      const meta = getTestOrderEntryStatusMeta(entry.status)
                      const active = entry.entryId === selected?.entryId
                      const entryStepCount = (entry.snapshot?.steps ?? []).length
                      return (
                        <div
                          key={entry.entryId ?? entry.orderNo}
                          className={`test-order-nav-row${active ? ' active' : ''}`}
                        >
                          <Checkbox
                            aria-label={`选择第 ${entry.orderNo ?? ''} 条执行条目`}
                            checked={checkedEntryIds.includes(entry.entryId ?? '')}
                            onChange={(event) =>
                              setCheckedEntryIds((prev) =>
                                event.target.checked
                                  ? [...prev, entry.entryId ?? '']
                                  : prev.filter((id) => id !== entry.entryId),
                              )
                            }
                          />
                          <button
                            type="button"
                            className="test-order-nav-item"
                            aria-current={active}
                            onClick={() => setSelectedEntryId(entry.entryId ?? null)}
                          >
                            <span className="test-order-nav-head">
                              {entry.casePriority ? (
                                <span
                                  className={`test-order-nav-prio tone-${priorityTone(entry.casePriority)}`}
                                >
                                  {entry.casePriority}
                                </span>
                              ) : null}
                              <span
                                className={`test-order-nav-status tone-${getTestOrderEntryStatusTone(entry.status)}`}
                              >
                                {meta.label}
                              </span>
                            </span>
                            <span className="test-order-nav-title">
                              {entry.caseTitle || entry.caseId}
                            </span>
                            <span className="test-order-nav-meta">
                              {entry.caseModule ? <span>{entry.caseModule}</span> : null}
                              <span>{entryStepCount} 步</span>
                              <span>{personName(entry.assigneeUserId) || '未分配'}</span>
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
              {checkedEntryIds.length > 0 ? <div className="test-order-sidebar-foot">
                <Text type="secondary" className="test-order-selection-count">已选 {checkedEntryIds.length} 条</Text>
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
              </div> : null}
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
                    <span className="test-order-case-no">
                      {selected.caseId}
                    </span>
                    <Text strong className="test-order-case-title">
                      {selected.caseTitle || selected.caseId}
                    </Text>
                    <span className="spacer" />
                    {lockedByAssignee ? (
                      <Text type="secondary">该条已分配给其他执行人</Text>
                    ) : null}
                  </div>
                  <div className="test-order-execution-meta">
                    <span
                      className={`test-order-meta-pill tone-${getTestOrderEntryStatusTone(selected.status)}`}
                    >
                      状态 <strong>{entryStatusMeta.label}</strong>
                    </span>
                    {selected.casePriority ? (
                      <span className={`test-order-meta-pill tone-${priorityTone(selected.casePriority)}`}>
                        优先级 <strong>{selected.casePriority}</strong>
                      </span>
                    ) : null}
                    <span className="test-order-meta-pill">
                      分配给 <strong>{personName(selected.assigneeUserId) || '未分配'}</strong>
                    </span>
                    {selected.caseModule ? (
                      <span className="test-order-meta-pill">
                        所属模块 <strong>{selected.caseModule}</strong>
                      </span>
                    ) : null}
                    <span className="test-order-meta-pill">
                      实际执行 <strong>{personName(selected.executorUserId) || '-'}</strong>
                    </span>
                    <span className="test-order-meta-pill">
                      执行时间 <strong>{formatTime(selected.executedAt) || '-'}</strong>
                    </span>
                  </div>
                  <div className="test-order-editor-body">
                    <section className="test-order-section tone-blue">
                      <div className="test-order-section-head">
                        <span className="test-order-section-title">
                          <ProfileOutlined />
                          前置条件
                        </span>
                        <span className="test-order-section-badge">
                          {preconditionCount} 项环境与数据依赖
                        </span>
                      </div>
                      <div className="test-order-section-body">
                        {preconditionCount === 0 ? (
                          <span className="test-order-precondition-empty">暂无前置条件</span>
                        ) : (
                          <ol className="test-order-precondition-list">
                            {(selected.snapshot?.preconditions ?? []).map((item, index) => (
                              <li key={index} className="test-order-precondition-item">
                                <span className="test-order-precondition-no">
                                  {String(index + 1).padStart(2, '0')}
                                </span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ol>
                        )}
                      </div>
                    </section>

                    <section className="test-order-section tone-teal">
                      <div className="test-order-section-head">
                        <span className="test-order-section-title">
                          <OrderedListOutlined />
                          测试执行步骤与预期结果
                        </span>
                        <span className="test-order-section-badge">{stepCount} 步</span>
                      </div>
                      <div className="test-order-section-body">
                        <table className="test-order-steps-table">
                          <caption>测试执行步骤与预期结果</caption>
                          <thead><tr><th scope="col">步骤</th><th scope="col">操作说明</th><th scope="col">预期结果</th></tr></thead>
                          <tbody>
                            {stepCount === 0 ? (
                              <tr><td colSpan={3} className="test-order-steps-empty">暂无测试步骤</td></tr>
                            ) : (selected.snapshot?.steps ?? []).map((step, index) => (
                              <tr key={index}>
                                <td><span className="test-order-step-index">{String(index + 1).padStart(2, '0')}</span></td>
                                <td>{step.action || '—'}</td>
                                <td>{step.expected || '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </section>
                  </div>
                </>
              )}
            </section>

            <aside className="workbench-panel test-order-verdict-panel">
              {selected ? (
                <>
                  <div className="test-order-verdict-title">
                    执行判定结果
                    <span className="test-order-verdict-hint">快捷键 1/2/3/4</span>
                  </div>
                  <TestOrderVerdictButtons
                    status={selected.status}
                    disabled={!canJudge || saveMutation.isPending}
                    showShortcuts
                    onJudge={(status) => save({ status })}
                  />

                  {/* 缺陷信息：只存了一个禅道缺陷号，没有缺陷详情接口，所以不做设计稿里那张 BUG 卡片。 */}
                  <div className="test-order-defect-section">
                    <div className="test-order-defect-head">关联缺陷与 BUG 追踪</div>
                    {selected.status === 'failed' || selected.status === 'blocked' ? (
                      <>
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
                      </>
                    ) : null}
                    {selected.zentaoBugId ? (
                      <div className="test-order-defect-card">
                        <span className="test-order-defect-id">禅道缺陷 #{selected.zentaoBugId}</span>
                        <Button
                          type="text"
                          className="test-order-defect-untie"
                          disabled={!canJudge}
                          onClick={() => save({ zentaoBugId: '' })}
                        >
                          解绑
                        </Button>
                      </div>
                    ) : null}
                    <Input
                      value={drafts.zentaoBugId ?? ''}
                      disabled={!canJudge}
                      placeholder="禅道缺陷号（可选）"
                      onChange={(event) =>
                        setDrafts((prev) => ({ ...prev, zentaoBugId: event.target.value }))
                      }
                      onBlur={() => save({ zentaoBugId: drafts.zentaoBugId ?? '' })}
                    />
                    <span className="test-order-defect-hint">
                      目前只能关联禅道缺陷号，Jira / 内部缺陷平台还没接入。
                    </span>
                  </div>

                  <footer className="test-order-execution-footer" aria-label="用例执行操作">
                    <div className="test-order-entry-navigation">
                      <Button size="small" disabled={selectedVisibleIndex <= 0} onClick={() => moveSelection(-1)}>上一条</Button>
                      <Text type="secondary">{selectedVisibleIndex >= 0 ? `第 ${selectedVisibleIndex + 1} / ${visibleEntries.length} 条` : '当前条目不在筛选结果中'}</Text>
                      <Button size="small" disabled={selectedVisibleIndex < 0 || selectedVisibleIndex >= visibleEntries.length - 1} onClick={() => moveSelection(1)}>下一条</Button>
                    </div>
                    <Checkbox
                      className="test-order-autoadvance"
                      checked={autoAdvance}
                      onChange={(event) => setAutoAdvance(event.target.checked)}
                    >
                      判定后自动前进
                    </Checkbox>
                    {saveStateText ? (
                      <Text
                        className="test-order-save-state"
                        type={saveMutation.isError ? 'danger' : 'secondary'}
                      >
                        {saveStateText}
                      </Text>
                    ) : null}
                  </footer>
                </>
              ) : null}
            </aside>
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

      <TestOrderGraphViewer
        open={graphOpen}
        orderId={order?.orderId ?? orderId ?? ''}
        projectId={order?.projectId}
        canExecute={can('execute')}
        currentUserId={currentUserId}
        isProjectOwner={isOwner}
        onClose={() => setGraphOpen(false)}
      />
    </div>
  )
}
