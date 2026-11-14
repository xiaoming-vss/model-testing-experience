import { useTestOrderWindow } from '../hooks/useTestOrderWindow'
import { TestOrderGraphViewer } from '../components/TestOrderGraphViewer'
import { TestOrderEntrySidebar, type TestOrderStatusFilter } from '../components/TestOrderEntrySidebar'
import { useViewMotion } from '@/shared/ui/useViewMotion'
import {
  ArrowLeftOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Input,
  Modal,
  Select,
  Segmented,
  Space,
  Spin,
  Tooltip,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { DELETED_ACCOUNT_LABEL } from '@/shared/components/UserReference/UserReference'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { AddCasesFromLibraryModal } from '../components/AddCasesFromLibraryModal'
import { CaseVisualizationPanel } from '../components/visualization/CaseVisualizationPanel'
import type { VisualizationMode } from '../visualizationTypes'
import { TestOrderCaseSummary } from '../components/TestOrderCaseSummary'
import { TestOrderVerdictButtons } from '../components/TestOrderVerdictButtons'
import { useTestOrderEntrySave } from '../hooks/useTestOrderEntrySave'
import { TEST_ORDER_VERDICTS, isTestOrderEntryLocked } from '../utils/testOrderExecution'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import {
  getTestOrderStatusMeta,
  getTestOrderStatusTone,
  groupTestOrderEntriesByStatus,
  type TestOrderResultStatus,
} from '../utils/testOrderStatus'
import '@/shared/styles/surface-tokens.css'
import '@/features/test-orders/styles/index.css'
import '@/features/test-orders/styles/workspace-v2.css'
import '@/features/test-orders/styles/workspace-sidebar-v3.css'
import '@/features/test-orders/styles/workspace-verdict-v2.css'

const { Text } = Typography

/**
 * 原因输入框自己保存输入态，失焦时才提交。
 * 这样逐字输入不会重渲染左侧清单和当前条目的步骤表。
 */
function TestOrderReasonInput({ label, value, disabled, onCommit }: {
  label: string
  value: string
  disabled: boolean
  onCommit: (reason: string) => void
}) {
  const [draft, setDraft] = useState(value)
  useEffect(() => { setDraft(value) }, [value])
  return <Input.TextArea
    aria-label={label}
    autoSize={{ minRows: 2, maxRows: 3 }}
    value={draft}
    disabled={disabled}
    placeholder="填写原因"
    onChange={(event) => setDraft(event.target.value)}
    onBlur={() => { if (draft !== value) onCommit(draft) }}
  />
}

export function TestOrderWorkspacePage() {
  const { orderId } = useParams<{ orderId: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const currentUserId = useAuthStore((state) => state.user?.userId)

  const [workspaceView, setWorkspaceView] = useState<'execution' | 'graph'>('execution')
  // 图谱首次打开后保持挂载：布局、选中节点和缩放都留在原地，来回切视图不再重新请求和全量布局。
  const [graphVisited, setGraphVisited] = useState(false)
  const graphMounted = graphVisited || workspaceView === 'graph'
  useEffect(() => {
    if (workspaceView === 'graph' && !graphVisited) setGraphVisited(true)
  }, [graphVisited, workspaceView])
  const workspaceViewRef = useViewMotion(workspaceView === 'execution' ? 0 : 1)
  const keyboardNavigation = useRef(false)
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<TestOrderStatusFilter>('all')
  const [onlyMine, setOnlyMine] = useState(false)
  const [collapsedGroups, setCollapsedGroups] = useState<TestOrderResultStatus[]>([])
  const [autoAdvance, setAutoAdvance] = useState(false)
  const [checkedEntryIds, setCheckedEntryIds] = useState<string[]>([])
  const [visualizationPreference, setVisualizationPreference] = useState<{ orderId?: string; mode: VisualizationMode }>({ mode: 'text' })
  const visualizationMode = visualizationPreference.orderId === orderId ? visualizationPreference.mode : 'text'
  const setVisualizationMode = (mode: VisualizationMode) => setVisualizationPreference({ orderId, mode })
  function clearCheckedOnFilter() {
    if (checkedEntryIds.length) message.info('筛选条件已变化，已清空勾选')
    setCheckedEntryIds([])
  }
  function changeKeyword(next: string) {
    clearCheckedOnFilter()
    setKeyword(next)
  }
  function changeStatusFilter(next: TestOrderStatusFilter) {
    if (next === statusFilter) return
    clearCheckedOnFilter()
    setStatusFilter(next)
  }
  function changeOnlyMine(next: boolean) {
    if (next === onlyMine) return
    clearCheckedOnFilter()
    setOnlyMine(next)
  }
  function toggleGroup(status: TestOrderResultStatus) {
    setCollapsedGroups((previous) => previous.includes(status)
      ? previous.filter((item) => item !== status)
      : [...previous, status])
  }
  function toggleAllEntries(checked: boolean) {
    const pageIds = entries.flatMap((entry) => entry.entryId ? [entry.entryId] : [])
    setCheckedEntryIds((previous) => checked
      ? [...new Set([...previous, ...pageIds])]
      : previous.filter((id) => !pageIds.includes(id)))
  }
  useEffect(() => { setCollapsedGroups([]) }, [orderId, statusFilter, onlyMine, keyword])
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [savedAt, setSavedAt] = useState<string>('')
  const [assignOpen, setAssignOpen] = useState(false)
  const [assignee, setAssignee] = useState('')
  const [addCasesOpen, setAddCasesOpen] = useState(false)

  const [searchKeyword, setSearchKeyword] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setSearchKeyword(keyword.trim()), 250)
    return () => clearTimeout(timer)
  }, [keyword])
  const { entriesQuery, detailQuery, entries, selectedEntryId, selected, currentPage, pageSize,
    total: entryTotal, selectEntry, clearDeletedSelection, changePage, moveSelection, advance } = useTestOrderWindow(
    orderId, searchParams.get('entryId'), { keyword: searchKeyword, status: statusFilter === 'all' ? '' : statusFilter, onlyMine, actor: currentUserId },
  )
  useEffect(() => { setCheckedEntryIds([]) }, [orderId])

  const orderQuery = useQuery({
    queryKey: ['testOrder', orderId],
    queryFn: () => api.getTestOrder(orderId!),
    enabled: Boolean(orderId),
    refetchOnWindowFocus: true,
    // 列表跳转前已写入同一份测试单；短时间内不重复请求。
    staleTime: 30_000,
  })
  const order = orderQuery.data
  // 列表行已经带回摘要（编号、标题、状态、执行人），切换条目时先用它撑住详情区，
  // 只有步骤快照需要等详情请求，避免整块面板卸载成 Spin 再重建。
  const selectedEntry = selectedEntryId
    ? entries.find((entry) => entry.entryId === selectedEntryId) ?? null
    : null
  const detailReady = Boolean(selected?.entryId && selected.entryId === selectedEntryId)
  const entryView = detailReady ? selected : selectedEntry

  // 只有判定过的条目才可能关联平台 Bug：pending 条目不会出现在这里，
  // 键盘逐条审查时不再为每个条目多发一次 Bug 查询。
  const linkedBugsQuery = useQuery({
    queryKey: ['bugs', order?.projectId, 'forEntry', selectedEntryId],
    queryFn: () =>
      api.getProjectBugs(order!.projectId!, {
        sourceEntryId: selectedEntryId!,
        page: 1,
        pageSize: 20,
      }),
    enabled: Boolean(order?.projectId && detailReady && selected?.status && selected.status !== 'pending'),
  })
  const { project, can } = useProjectAccess(order?.projectId)

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
    userId ? memberNameMap.get(userId) ?? (membersQuery.data ? DELETED_ACCOUNT_LABEL : userId) : ''
  const visibleEntries = entries
  const mineCount = entriesQuery.data?.mineCount ?? 0
  const allEntryCount = entriesQuery.data?.orderTotal ?? order?.entriesTotal ?? 0
  // 分组只作用于当前页；↑/↓ 按用户看到的顺序移动，折叠的分组不参与。
  const groupedEntries = useMemo(() => groupTestOrderEntriesByStatus(visibleEntries), [visibleEntries])
  const groupedFlatEntries = useMemo(() => groupedEntries.flatMap((group) => group.entries), [groupedEntries])
  const navigationEntries = useMemo(() => groupedEntries
    .filter((group) => !collapsedGroups.includes(group.status))
    .flatMap((group) => group.entries), [groupedEntries, collapsedGroups])

  function moveInDisplayOrder(offset: number) {
    if (!selectedEntryId) return
    const index = navigationEntries.findIndex((entry) => entry.entryId === selectedEntryId)
    if (index < 0) {
      const fallback = offset > 0 ? navigationEntries[0] : navigationEntries[navigationEntries.length - 1]
      if (fallback?.entryId) selectEntry(fallback.entryId)
      return
    }
    moveSelection(offset, navigationEntries)
  }

  const selectedReason = selected?.status === 'blocked' ? selected?.blockReason : selected?.failureReason
  useEffect(() => {
    if (selectedEntryId) setDrafts({ reason: selectedReason ?? '' })
  }, [selectedEntryId, selectedReason])

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
      queryClient.invalidateQueries({ queryKey: ['testOrderEntry', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrder', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrders'] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const removeMutation = useMutation({
    mutationFn: (entryId: string) => api.deleteTestOrderEntry(orderId!, entryId),
    onSuccess: async (_, removedId) => {
      message.success('执行条目已移除')
      setCheckedEntryIds([])
      await queryClient.invalidateQueries({ queryKey: ['testOrderEntries', orderId] })
      clearDeletedSelection(removedId)
      queryClient.removeQueries({ queryKey: ['testOrderEntry', orderId, removedId], exact: true })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['testOrder', orderId] }),
        queryClient.invalidateQueries({ queryKey: ['testOrders'] }),
      ])
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
      queryClient.invalidateQueries({ queryKey: ['testOrderEntry', orderId] })
      queryClient.invalidateQueries({ queryKey: ['testOrder', orderId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  function toggleEntry(id: string | undefined, checked: boolean) {
    if (!id) return
    if (checked && checkedEntryIds.length >= 500) { message.warning('单次最多选择 500 条执行条目'); return }
    setCheckedEntryIds((previous) => checked ? [...new Set([...previous, id])] : previous.filter((item) => item !== id))
  }

  function save(payload: Record<string, unknown>) {
    if (!selected?.entryId) return
    saveMutation.mutate({ entryId: selected.entryId, payload }, {
      onSuccess: () => {
        setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5))
        if (autoAdvance && payload.status) void advance(selected.entryId!).catch(() => message.warning('下一条加载失败，请手动翻页重试'))
      },
    })
  }

  const isOwner = project?.role === 'owner'
  const lockedByAssignee =
    isTestOrderEntryLocked(entryView?.assigneeUserId, currentUserId, isOwner)
  const canJudge = detailReady && can('execute') && !lockedByAssignee

  // 在清单内使用键盘切换时，焦点跟随选中项，避免旧条目残留焦点框和移除按钮。
  useEffect(() => {
    const focused = document.activeElement
    if (keyboardNavigation.current && focused !== document.body && !focused?.matches('.test-order-nav-item')) {
      keyboardNavigation.current = false
    }
    const focusedInList = focused instanceof Element
      && focused.matches('.test-order-nav-item')
      && Boolean(focused.closest('.test-order-side-panel'))
    if (keyboardNavigation.current || focusedInList) {
      const button = document.querySelector<HTMLButtonElement>(
        '.test-order-side-panel .test-order-nav-item[aria-current="true"]',
      )
      if (button && selectedEntryId) { button.focus(); keyboardNavigation.current = false }
    }
  }, [selectedEntryId, entriesQuery.data])

  // 键盘：1/2/3/4 判定整条用例，上下切换条目。
  // 监听器只注册一次，处理函数通过 ref 取最新状态，避免每次渲染重挂监听。
  const keyDownHandlerRef = useRef<(event: KeyboardEvent) => void>(() => {})
  useEffect(() => {
    keyDownHandlerRef.current = (event: KeyboardEvent) => {
      if (workspaceView !== 'execution' || saveMutation.isPending) return
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return
      if (event.key === 'ArrowDown') {
        keyboardNavigation.current = Boolean(target?.closest('.test-order-nav-item'))
        event.preventDefault()
        moveInDisplayOrder(1)
        return
      }
      if (event.key === 'ArrowUp') {
        keyboardNavigation.current = Boolean(target?.closest('.test-order-nav-item'))
        event.preventDefault()
        moveInDisplayOrder(-1)
        return
      }
      const status = TEST_ORDER_VERDICTS.find((option) => option.key === event.key)?.value
      if (!status || !canJudge) return
      event.preventDefault()
      save({ status })
    }
  })
  useEffect(() => {
    const listener = (event: KeyboardEvent) => keyDownHandlerRef.current(event)
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  }, [])

  const orderTotal = order?.entriesTotal ?? 0
  const orderExecuted = order?.entriesExecuted ?? 0
  const orderProgressPercent = orderTotal > 0 ? Math.round((orderExecuted / orderTotal) * 100) : 0
  const selectedGroupedIndex = groupedFlatEntries.findIndex((entry) => entry.entryId === selectedEntryId)
  const isSaving = saveMutation.isPending
  const saveStateText = isSaving ? '保存中…' : savedAt ? `已保存 ${savedAt}` : ''
  const orderStatusMeta = order ? getTestOrderStatusMeta(order.status) : null

  return (
    <div className="workbench-page api-automation-page functional-suite-detail-page test-order-workspace-page tp-surface">
      <div className="api-automation-content">
        <div className="page-frame test-order-workspace tp-board">
          <section className="workbench-panel test-order-orderbar tp-list-toolbar">
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
                <span className="test-order-orderbar-chip tp-tone-tag">被测版本 {order.testedVersion}</span>
              ) : null}
              {orderStatusMeta ? (
                <span
                  className={`test-order-orderbar-chip tp-tone-tag tone-${getTestOrderStatusTone(order?.status)}`}
                >
                  {orderStatusMeta.label}
                </span>
              ) : null}
            </span>
            <span className="test-order-orderbar-progress">
              已执行 {order?.entriesExecuted ?? 0}/{order?.entriesTotal ?? 0}
            </span>
            <div className="test-order-orderbar-actions">
              <Segmented className="tab-view-switch" aria-label="测试单视图" value={workspaceView} disabled={!order?.orderId}
                options={[{ label: '用例执行', value: 'execution' }, { label: '用例图谱', value: 'graph' }]}
                onChange={value => setWorkspaceView(value as 'execution' | 'graph')} />
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

          {graphMounted && orderId && <div ref={workspaceView === 'graph' ? workspaceViewRef : undefined} className="test-order-inline-graph" style={workspaceView === 'graph' ? undefined : { display: 'none' }}><TestOrderGraphViewer orderId={orderId} projectId={order?.projectId} canExecute={can('execute')} currentUserId={currentUserId} isProjectOwner={isOwner} /></div>}
          <div ref={workspaceView === 'execution' ? workspaceViewRef : undefined} className="test-order-workspace-cols" style={workspaceView === 'graph' ? { display: 'none' } : undefined}>
            <TestOrderEntrySidebar
              orderId={orderId}
              projectId={order?.projectId}
              entries={visibleEntries}
              statusCounts={entriesQuery.data?.statusCounts}
              matchedTotal={entriesQuery.data?.matchedTotal ?? 0}
              mineCount={mineCount}
              orderTotal={allEntryCount}
              progressPercent={orderProgressPercent}
              entryTotal={entryTotal}
              currentPage={currentPage}
              pageSize={pageSize}
              keyword={keyword}
              statusFilter={statusFilter}
              onlyMine={onlyMine}
              checkedEntryIds={checkedEntryIds}
              selectedEntryId={selectedEntryId}
              collapsedGroups={collapsedGroups}
              loading={entriesQuery.isLoading}
              fetching={entriesQuery.isFetching}
              placeholder={Boolean(entriesQuery.isPlaceholderData)}
              canExecute={can('execute')}
              canWrite={can('write')}
              batchPending={batchMutation.isPending}
              assigneeName={personName}
              onKeywordChange={changeKeyword}
              onStatusFilterChange={changeStatusFilter}
              onOnlyMineChange={changeOnlyMine}
              onToggleGroup={toggleGroup}
              onRefresh={() => void entriesQuery.refetch()}
              onSelectEntry={selectEntry}
              onToggleEntry={toggleEntry}
              onToggleAll={toggleAllEntries}
              onClearChecked={() => setCheckedEntryIds([])}
              onRemoveEntry={(entryId) => removeMutation.mutate(entryId)}
              onBatchPass={() => batchMutation.mutate()}
              onAssign={() => {
                setAssignee('')
                setAssignOpen(true)
              }}
              onPageChange={changePage}
            />

            <section className="test-order-panel">
              {entriesQuery.isLoading ? <Spin description="加载执行详情…" />
                : !selectedEntryId ? (
                <div className="sprint-card-loading">
                  <Empty description={order?.entriesTotal ? '当前筛选没有执行条目' : '请先加入执行条目'}>
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
                  <div className="test-order-editor-body">
                    {entryView ? <TestOrderCaseSummary
                      entry={entryView}
                      assigneeName={personName(entryView.assigneeUserId)}
                      executorName={personName(entryView.executorUserId)}
                      lockedByAssignee={lockedByAssignee}
                    /> : null}
                    {detailReady && selected ? <CaseVisualizationPanel key={`${orderId}:${selected.entryId}`} orderId={orderId!} entryId={selected.entryId!} projectId={order?.projectId} snapshot={selected.snapshot} caseTitle={selected.caseTitle} canGenerate={can('execute')} preferredMode={visualizationMode} onMode={setVisualizationMode} />
                      : detailQuery.error ? <div className="test-order-case-content-status">
                        <Alert showIcon type="error" title={getErrorMessage(detailQuery.error)} action={<Button onClick={() => void detailQuery.refetch()}>重试</Button>} />
                      </div>
                      : <div className="test-order-case-content-status" role="status" aria-live="polite">
                        <Spin size="small" /><span>加载执行详情…</span>
                      </div>}
                  </div>
                  <section className="test-order-execution-bar" aria-label="执行判定与缺陷关联">
                    <div className="test-order-execution-actions">
                      <span className="test-order-verdict-title">执行判定结果</span>
                      <TestOrderVerdictButtons
                        status={entryView?.status}
                        disabled={!canJudge || saveMutation.isPending}
                        showShortcuts
                        reverseOrder
                        onJudge={(status) => save({ status })}
                      />
                      {detailReady && selected?.status === 'failed' ? (
                        <div className="test-order-defect-controls">
                          <ProjectActionButton
                            action="write"
                            size="small"
                            className="action-btn-create"
                            operation="create"
                            aria-label="提交 Bug"
                            onClick={() => {
                              const reason = drafts.reason ?? selected.failureReason ?? ''
                              const params = new URLSearchParams({
                                projectId: order?.projectId ?? '',
                                orderId: order?.orderId ?? '',
                                entryId: selected.entryId ?? '',
                                caseId: selected.caseId ?? '',
                                requirementId: selected.requirementId ?? '',
                                sprintId: order?.sprintId ?? '',
                                title: `${selected.caseTitle ?? '执行失败'} 执行失败`,
                                description: reason ? `<p>${reason}</p>` : '',
                              })
                              navigate(`/bugs/new?${params.toString()}`)
                            }}
                          >
                            提交 Bug
                          </ProjectActionButton>
                        </div>
                      ) : null}
                    </div>
                    {detailReady && selected && (selected.status === 'failed' || selected.status === 'blocked' || listItems(linkedBugsQuery.data).length > 0) ? (
                      <div className="test-order-defect-section">
                        {linkedBugsQuery.data && listItems(linkedBugsQuery.data).length > 0 ? (
                          <div className="test-order-linked-bugs">
                            {listItems(linkedBugsQuery.data).map((bug) => (
                              <a
                                key={bug.bugId}
                                className="test-order-linked-bug-chip"
                                href={`/bugs/${bug.bugId}`}
                                onClick={(event) => {
                                  event.preventDefault()
                                  navigate(`/bugs/${bug.bugId}`)
                                }}
                              >
                                BUG-{bug.bugNo} {bug.title}
                              </a>
                            ))}
                          </div>
                        ) : null}
                        {selected.status === 'failed' || selected.status === 'blocked' ? (
                          <>
                            <Text type="secondary">
                              {selected.status === 'failed' ? '失败原因' : '阻塞原因'}
                            </Text>
                            <TestOrderReasonInput
                              label={selected.status === 'failed' ? '失败原因' : '阻塞原因'}
                              value={drafts.reason ?? ''}
                              disabled={!canJudge}
                              onCommit={(reason) => {
                                setDrafts((prev) => ({ ...prev, reason }))
                                save(selected.status === 'failed' ? { failureReason: reason } : { blockReason: reason })
                              }}
                            />
                          </>
                        ) : null}
                      </div>
                    ) : null}
                    <footer className="test-order-execution-footer" aria-label="用例执行操作">
                      <Tooltip
                        title={`快捷键：${TEST_ORDER_VERDICTS.map(({ key, label }) => `${key} ${label}`).join(' · ')}；↑ 上一条，↓ 下一条`}
                        trigger={['hover', 'focus']}
                      >
                        <Button type="text" size="small" shape="circle"
                          className="test-order-shortcut-help" aria-label="快捷键说明"
                          icon={<QuestionCircleOutlined />} />
                      </Tooltip>
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
                    <Text className="test-order-entry-position" type="secondary">
                      {selectedGroupedIndex >= 0
                        ? `本页第 ${selectedGroupedIndex + 1} / ${groupedFlatEntries.length} 条 · 筛选共 ${entryTotal} 条`
                        : '当前条目不在筛选结果中'}
                    </Text>
                  </section>
                </>
              )}
            </section>
          </div>
        </div>
      </div>

      <Modal
        mask={{ closable: false }}
        centered
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
