import { useTestOrderWindow } from '../hooks/useTestOrderWindow'
import { TestOrderGraphViewer } from '../components/TestOrderGraphViewer'
import { TestOrderEntryList } from '../components/TestOrderEntryList'
import { TestOrderWorkspaceToolbar } from '../components/TestOrderWorkspaceToolbar'
import { TestOrderDetailHeader } from '../components/TestOrderDetailHeader'
import { useViewMotion } from '@/shared/ui/useViewMotion'
import {
  LeftOutlined,
  QuestionCircleOutlined,
  RightOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Checkbox,
  Input,
  Modal,
  Select,
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
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { AddCasesFromLibraryModal } from '../components/AddCasesFromLibraryModal'
import { CaseVisualizationPanel } from '../components/visualization/CaseVisualizationPanel'
import type { VisualizationMode } from '../visualizationTypes'
import { TestOrderCaseSummary } from '../components/TestOrderCaseSummary'
import { TestOrderVerdictButtons } from '../components/TestOrderVerdictButtons'
import { useTestOrderEntrySave } from '../hooks/useTestOrderEntrySave'
import { TEST_ORDER_VERDICTS, isTestOrderEntryLocked } from '../utils/testOrderExecution'
import { useProjectAccess } from '@/domain/projects/hooks/useProjectAccess'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import type { TestOrderStatusFilter } from '../utils/testOrderStatus'
import '@/shared/styles/surface-tokens.css'
import workspaceStyles from '../styles/test-order-workspace.module.css'

const { Text } = Typography

/** 详情宽屏把切换放到两侧；窄屏收进面包屑右侧，避免箭头压住正文。 */
function useDetailNarrowNav() {
  const query = '(max-width: 1320px)'
  const read = () => typeof window !== 'undefined'
    && Boolean(window.matchMedia?.(query).matches ?? window.innerWidth <= 1320)
  const [narrow, setNarrow] = useState(read)
  useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia?.(query)
    if (!media) return
    const update = () => setNarrow(media.matches)
    update()
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [])
  return narrow
}

/**
 * 原因输入框自己保存输入态，失焦时才提交。
 * 这样逐字输入不会重渲染详情区域和当前条目的步骤表。
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
  const detailNarrowNav = useDetailNarrowNav()
  // 图谱首次打开后保持挂载：布局、选中节点和缩放都留在原地，来回切视图不再重新请求和全量布局。
  const [graphVisited, setGraphVisited] = useState(false)
  const graphMounted = graphVisited || workspaceView === 'graph'
  useEffect(() => {
    if (workspaceView === 'graph' && !graphVisited) setGraphVisited(true)
  }, [graphVisited, workspaceView])
  const workspaceViewRef = useViewMotion(workspaceView === 'execution' ? 0 : 1)
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<TestOrderStatusFilter>('all')
  const [onlyMine, setOnlyMine] = useState(false)
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
  function clearFilters() {
    clearCheckedOnFilter()
    setKeyword('')
    setStatusFilter('all')
    setOnlyMine(false)
  }
  function toggleAllEntries(checked: boolean) {
    const pageIds = entries.flatMap((entry) => entry.entryId ? [entry.entryId] : [])
    setCheckedEntryIds((previous) => checked
      ? [...new Set([...previous, ...pageIds])]
      : previous.filter((id) => !pageIds.includes(id)))
  }
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
    total: entryTotal, selectEntry, clearDeletedSelection, changePage,
    moveToPageEntry, advance } = useTestOrderWindow(
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

  const selectedIndex = entryView?.entryId
    ? entries.findIndex((entry) => entry.entryId === entryView.entryId)
    : -1
  const hasPrev = selectedIndex > 0 || (selectedIndex === 0 && currentPage > 1)
  const hasNext = selectedIndex >= 0
    && (selectedIndex < entries.length - 1 || currentPage * pageSize < entryTotal)

  async function moveDetail(offset: 1 | -1) {
    if (!selectedEntryId) return
    const index = entries.findIndex((entry) => entry.entryId === selectedEntryId)
    if (index < 0) return
    const adjacent = entries[index + offset]
    if (adjacent?.entryId) {
      selectEntry(adjacent.entryId)
      return
    }
    try {
      const moved = await moveToPageEntry(offset)
      if (!moved) message.info(offset > 0 ? '已经是最后一条' : '已经是第一条')
    } catch (error) {
      message.warning(getErrorMessage(error))
    }
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

  // 键盘：1/2/3/4 判定整条用例，上下切换条目。只在详情打开时接管方向键，
  // 列表页仍可用方向键滚动。
  // 监听器只注册一次，处理函数通过 ref 取最新状态，避免每次渲染重挂监听。
  const keyDownHandlerRef = useRef<(event: KeyboardEvent) => void>(() => {})
  useEffect(() => {
    keyDownHandlerRef.current = (event: KeyboardEvent) => {
      if (workspaceView !== 'execution' || saveMutation.isPending || !selectedEntryId) return
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        void moveDetail(1)
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        void moveDetail(-1)
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

  const isSaving = saveMutation.isPending
  const saveStateText = isSaving ? '保存中…' : savedAt ? `已保存 ${savedAt}` : ''
  const hasFilters = Boolean(keyword.trim()) || statusFilter !== 'all' || onlyMine
  const detailPosition = entryView?.orderNo
    ? `全单第 ${entryView.orderNo} 条 · 筛选共 ${entryTotal} 条`
    : '当前条目不在筛选结果中'

  function returnToEntryList() {
    selectEntry(null)
  }

  const workspaceToolbar = <TestOrderWorkspaceToolbar
    order={order}
    statusCounts={entriesQuery.data?.statusCounts}
    statusFilter={statusFilter}
    onStatusFilterChange={changeStatusFilter}
    keyword={keyword}
    onKeywordChange={changeKeyword}
    onlyMine={onlyMine}
    onOnlyMineChange={changeOnlyMine}
    hasFilters={hasFilters}
    onClearFilters={clearFilters}
    onRefresh={() => void entriesQuery.refetch()}
    refreshing={entriesQuery.isFetching}
    graphActive={workspaceView === 'graph'}
    onToggleGraph={() => setWorkspaceView((view) => view === 'graph' ? 'execution' : 'graph')}
    onBack={() => navigate('/testing?tab=orders')}
    onAddCases={() => setAddCasesOpen(true)}
  />

  return (
    <div className={`workbench-page api-automation-page functional-suite-detail-page test-order-workspace-page tp-list-surface tp-surface ${workspaceStyles.root}`}>
      <div className="api-automation-content gap-3">
        <div className="w-full test-order-workspace tp-board">
          {orderQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(orderQuery.error)} />
          ) : null}
          {entriesQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(entriesQuery.error)} />
          ) : null}

          {graphMounted && orderId && <div ref={workspaceView === 'graph' ? workspaceViewRef : undefined} className="test-order-inline-graph flex min-h-0 min-w-0 flex-1 overflow-hidden [&>.test-order-graph-viewer]:min-h-0 [&>.test-order-graph-viewer]:min-w-0 [&>.test-order-graph-viewer]:flex-1" style={workspaceView === 'graph' ? undefined : { display: 'none' }}><TestOrderGraphViewer orderId={orderId} projectId={order?.projectId} canExecute={can('execute')} currentUserId={currentUserId} isProjectOwner={isOwner} toolbar={workspaceView === 'graph' ? workspaceToolbar : undefined} /></div>}
          <div ref={workspaceView === 'execution' ? workspaceViewRef : undefined} className="test-order-execution-view flex min-h-0 min-w-0 flex-auto flex-col" style={workspaceView === 'graph' ? { display: 'none' } : undefined}>
            <div className="test-order-list-view flex min-h-0 min-w-0 flex-auto flex-col [&[hidden]]:hidden" hidden={Boolean(selectedEntryId)}>
              <TestOrderEntryList
                toolbar={workspaceView === 'execution' && !selectedEntryId ? workspaceToolbar : null}
                orderId={orderId}
                projectId={order?.projectId}
                entries={entries}
                entryTotal={entryTotal}
                currentPage={currentPage}
                pageSize={pageSize}
                checkedEntryIds={checkedEntryIds}
                loading={entriesQuery.isLoading}
                fetching={entriesQuery.isFetching}
                placeholder={Boolean(entriesQuery.isPlaceholderData)}
                canExecute={can('execute')}
                canWrite={can('write')}
                batchPending={batchMutation.isPending}
                hasFilters={hasFilters}
                assigneeName={personName}
                onSelectEntry={(id) => selectEntry(id)}
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
                onAddCases={() => setAddCasesOpen(true)}
                onClearFilters={clearFilters}
              />
            </div>

            {selectedEntryId ? <section className="test-order-detail-panel flex min-h-0 min-w-0 flex-auto flex-col overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)]">
              <TestOrderDetailHeader
                order={order}
                caseTitle={entryView?.caseTitle}
                narrowNav={detailNarrowNav}
                hasPrev={hasPrev}
                hasNext={hasNext}
                onBackToOrders={() => navigate('/testing?tab=orders')}
                onBackToCases={returnToEntryList}
                onPrev={() => void moveDetail(-1)}
                onNext={() => void moveDetail(1)}
              />

              <div className="test-order-detail-stage relative flex min-h-0 min-w-0 flex-auto flex-col">
                {!detailNarrowNav ? <>
                  <Tooltip title="上一条（↑）" placement="right">
                    <Button
                      className="test-order-detail-side-nav is-prev absolute left-5 top-1/2 z-[4] h-11 w-11 -translate-y-1/2 rounded-full border border-[var(--srf-card-border)] bg-[var(--srf-card)] text-[var(--srf-text-secondary)] shadow-[0_2px_8px_var(--srf-shadow-color)] hover:border-[var(--srf-accent)] hover:text-[var(--srf-accent)] disabled:opacity-35"
                      shape="circle"
                      aria-label="上一条"
                      icon={<LeftOutlined />}
                      disabled={!hasPrev}
                      onClick={() => void moveDetail(-1)}
                    />
                  </Tooltip>
                  <Tooltip title="下一条（↓）" placement="left">
                    <Button
                      className="test-order-detail-side-nav is-next absolute right-5 top-1/2 z-[4] h-11 w-11 -translate-y-1/2 rounded-full border border-[var(--srf-card-border)] bg-[var(--srf-card)] text-[var(--srf-text-secondary)] shadow-[0_2px_8px_var(--srf-shadow-color)] hover:border-[var(--srf-accent)] hover:text-[var(--srf-accent)] disabled:opacity-35"
                      shape="circle"
                      aria-label="下一条"
                      icon={<RightOutlined />}
                      disabled={!hasNext}
                      onClick={() => void moveDetail(1)}
                    />
                  </Tooltip>
                </> : null}
                <div className="test-order-editor-body test-order-detail-body flex min-h-0 flex-auto flex-col overflow-auto gap-0 p-0">
                  <div className="test-order-detail-inner mx-auto w-full max-w-[1200px] pb-6 max-narrow:max-w-none">
                    {entryView ? <TestOrderCaseSummary
                      entry={entryView}
                      assigneeName={personName(entryView.assigneeUserId)}
                      executorName={personName(entryView.executorUserId)}
                      lockedByAssignee={lockedByAssignee}
                    /> : null}
                    {detailReady && selected ? <CaseVisualizationPanel key={`${orderId}:${selected.entryId}`} orderId={orderId!} entryId={selected.entryId!} projectId={order?.projectId} snapshot={selected.snapshot} caseTitle={selected.caseTitle} canGenerate={can('execute')} preferredMode={visualizationMode} onMode={setVisualizationMode} />
                      : detailQuery.error ? <div className="test-order-case-content-status flex items-center gap-2.5 p-6 text-[12px] text-[var(--srf-text-muted)]">
                        <Alert showIcon type="error" title={getErrorMessage(detailQuery.error)} action={<Button onClick={() => void detailQuery.refetch()}>重试</Button>} />
                      </div>
                      : <div className="test-order-case-content-status flex items-center gap-2.5 p-6 text-[12px] text-[var(--srf-text-muted)]" role="status" aria-live="polite">
                        <Spin size="small" /><span>加载执行详情…</span>
                      </div>}
                  </div>
                </div>
              </div>

              <section className="test-order-execution-bar grid flex-none grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-5 gap-y-3 border-t border-[var(--srf-card-border)] bg-[var(--srf-card)] px-5 py-3.5 [grid-template-areas:'footer_actions_position'] max-[1600px]:grid-cols-[minmax(0,1fr)_auto] max-[1600px]:gap-x-4 max-[1600px]:gap-y-2.5 max-[1600px]:px-4 max-[1600px]:py-3 max-[1600px]:[grid-template-areas:'actions_actions'_'footer_position'] max-[1100px]:grid-cols-1 max-[1100px]:[grid-template-areas:'actions'_'position'_'footer']" aria-label="执行判定与缺陷关联">
                <div className="test-order-execution-actions flex flex-wrap items-center justify-end gap-3 [grid-area:actions] max-[1100px]:gap-2">
                  <span className="test-order-verdict-title flex items-baseline justify-between gap-2 text-[12px] font-bold leading-[18px] text-[var(--srf-text)]">执行判定结果</span>
                  <TestOrderVerdictButtons
                    status={entryView?.status}
                    disabled={!canJudge || saveMutation.isPending}
                    showShortcuts
                    reverseOrder
                    layout="flex"
                    onJudge={(status) => save({ status })}
                  />
                  {detailReady && selected?.status === 'failed' ? (
                    <div className="test-order-defect-controls flex min-w-0 flex-none items-center [&_.ant-btn]:flex-none">
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
                  <div className="test-order-defect-section col-span-full flex flex-col gap-2 max-h-[min(20vh,180px)] overflow-auto">
                    {linkedBugsQuery.data && listItems(linkedBugsQuery.data).length > 0 ? (
                      <div className="test-order-linked-bugs flex flex-wrap gap-2">
                        {listItems(linkedBugsQuery.data).map((bug) => (
                          <a
                            key={bug.bugId}
                            className="test-order-linked-bug-chip text-[var(--srf-accent)] [overflow-wrap:anywhere]"
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
                <footer className="test-order-execution-footer flex flex-wrap items-center gap-2 text-[11px] [grid-area:footer]" aria-label="用例执行操作">
                  <Tooltip
                    title={`快捷键：${TEST_ORDER_VERDICTS.map(({ key, label }) => `${key} ${label}`).join(' · ')}；↑ 上一条，↓ 下一条`}
                    trigger={['hover', 'focus']}
                  >
                    <Button type="text" size="small" shape="circle"
                      className="test-order-shortcut-help text-[var(--srf-text-muted)]" aria-label="快捷键说明"
                      icon={<QuestionCircleOutlined />} />
                  </Tooltip>
                  <Checkbox
                    className="test-order-autoadvance w-auto text-[11px] text-[var(--srf-text-secondary)]"
                    checked={autoAdvance}
                    onChange={(event) => setAutoAdvance(event.target.checked)}
                  >
                    判定后自动前进
                  </Checkbox>
                  {saveStateText ? (
                    <Text
                      className="test-order-save-state text-[11px] text-[var(--srf-text-muted)]"
                      type={saveMutation.isError ? 'danger' : 'secondary'}
                    >
                      {saveStateText}
                    </Text>
                  ) : null}
                </footer>
                <Text className="test-order-entry-position border-s border-[var(--srf-card-border)] ps-5 text-right tabular-nums text-[11px] text-[var(--srf-text-secondary)] [grid-area:position] max-[1100px]:border-0 max-[1100px]:ps-0" type="secondary">
                  {detailPosition}
                </Text>
              </section>
            </section> : null}
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
