import { ActionButton } from '@/shared/components/ActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ArrowLeftOutlined, DownOutlined, EditOutlined, RightOutlined, UploadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Empty, Input, Modal, Popconfirm, Select, Space, Spin, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { LlmConnectionSelectModal } from '../components/LlmConnectionSelectModal'
import { UiImportConflictModal } from '../components/UiImportConflictModal'
import { ImportMigrationWarning } from '../components/ImportMigrationWarning'
import { RunHistoryTable, RunRowActions, type RunMenuAction } from '../components/RunHistoryTable'
import { confirmDeleteRun, isRunDeletable } from '../utils/runDeletion'
import { RunPipelineStatus } from '../components/RunPipelineStatus'
import { validateUiSourceArchive } from '../utils/uiSourceArchive'
import type { UiCaseGenerateTaskRun, UiCaseGenerateTaskRunImportConflict } from '../types'
import { parseUiCaseCandidate } from '../utils/uiCaseCandidate'
import { isGenerateTaskRunImportable } from '../utils/taskStatus'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { api, ApiError, listItems, type ListResponse } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage, normalizeRequirementId, normalizeSprintId } from '@/utils/format'

const { Text } = Typography
const activeRunStatuses = new Set(['pending', 'claimed', 'running'])

function formatBytes(value?: number) {
  if (value === undefined || !Number.isFinite(value)) return '-'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${Number((value / 1024).toFixed(1))} KiB`
  return `${Number((value / 1024 / 1024).toFixed(1))} MiB`
}


function archiveErrorMessage(error: unknown) {
  const messageText = getErrorMessage(error)
  return error instanceof ApiError && error.status === 413
    ? `源码包超过上传大小限制：${messageText}`
    : messageText
}

function uiImportErrorMessage(error: unknown) {
  const messageText = getErrorMessage(error)
  if (error instanceof ApiError && error.status === 403) {
    return `无权限执行 UI 用例导入操作：${messageText}`
  }
  return error instanceof ApiError && error.status >= 500
    ? `服务端导入失败，未完成正式资产写入：${messageText}`
    : messageText
}

function CandidatePreview({ yaml }: { yaml: string }) {
  const parsed = useMemo(() => parseUiCaseCandidate(yaml), [yaml])
  const [expandedCases, setExpandedCases] = useState<Set<string>>(() => new Set())
  if (parsed.error) {
    return (
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Alert showIcon type="warning" title="YAML 暂时无法解析，已保留原文供修复" description={parsed.error} />
        <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{parsed.rawYaml}</pre>
      </Space>
    )
  }
  if (parsed.cases.length === 0) return <Empty description="候选结果中没有可预览的用例" />
  return (
    <Space orientation="vertical" size={12} style={{ width: '100%' }}>
      {parsed.cases.map((candidate, caseIndex) => {
        const caseName = candidate.name || `未命名用例 ${caseIndex + 1}`
        const caseKey = `${caseName}-${caseIndex}`
        const expanded = expandedCases.has(caseKey)

        return (
          <Card
            key={caseKey}
            className="ui-task-candidate-case-card"
            size="small"
            title={(
              <button
                type="button"
                className="ui-task-candidate-case-trigger"
                aria-expanded={expanded}
                aria-label={`${caseName}，${expanded ? '收起' : '展开'}`}
                onClick={() => {
                  setExpandedCases((current) => {
                    const next = new Set(current)
                    if (next.has(caseKey)) next.delete(caseKey)
                    else next.add(caseKey)
                    return next
                  })
                }}
              >
                {expanded ? <DownOutlined aria-hidden /> : <RightOutlined aria-hidden />}
                <span>{caseName}</span>
              </button>
            )}
            extra={<Space>{candidate.enabled === undefined ? null : <Tag>{candidate.enabled ? '启用' : '停用'}</Tag>}<Text type="secondary">顺序 {candidate.orderNo ?? '-'}</Text></Space>}
          >
            {expanded ? (
              <>
                {Object.keys(candidate.extraFields).length ? (
                  <Descriptions size="small" column={1} items={Object.entries(candidate.extraFields).map(([key, value]) => ({ key, label: key, children: JSON.stringify(value) }))} />
                ) : null}
                <Table
                  size="small"
                  pagination={false}
                  rowKey="__rowKey"
                  dataSource={candidate.steps.map((step, index) => ({ ...step, __rowKey: index }))}
                  columns={[
                    { title: '顺序', dataIndex: 'orderNo', width: 70 },
                    { title: '步骤名称', dataIndex: 'stepName' },
                    { title: '关键字', dataIndex: 'keyword', width: 110 },
                    { title: '定位类型', dataIndex: 'locatorType', width: 110 },
                    { title: '定位值', dataIndex: 'locatorValue' },
                    { title: '操作值', dataIndex: 'operationValue' },
                    { title: '失败继续', dataIndex: 'continueOnFailure', render: (value) => value === undefined ? '-' : value ? '是' : '否' },
                    { title: '启用', dataIndex: 'enabled', render: (value) => value === undefined ? '-' : value ? '是' : '否' },
                    { title: '其他字段', dataIndex: 'extraFields', render: (value) => Object.keys(value ?? {}).length ? JSON.stringify(value) : '-' },
                  ]}
                />
              </>
            ) : null}
          </Card>
        )
      })}
    </Space>
  )
}

type DetailLocationState = { pendingSourceArchive?: File; pendingSourceArchiveError?: string } | null

export function UiCaseGenerateTaskDetailPage() {
  const { taskId = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const pendingNavigationFile = (location.state as DetailLocationState)?.pendingSourceArchive
  const pendingNavigationError = (location.state as DetailLocationState)?.pendingSourceArchiveError
  const [selectedRunId, setSelectedRunId] = useState<string>()
  const [draftYaml, setDraftYaml] = useState('')
  const [savedYaml, setSavedYaml] = useState('')
  const [reviewComment, setReviewComment] = useState('')
  const [llmModalOpen, setLlmModalOpen] = useState(false)
  const [archiveModalOpen, setArchiveModalOpen] = useState(Boolean(pendingNavigationFile))
  const [archiveFile, setArchiveFile] = useState<File | undefined>(pendingNavigationFile)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editName, setEditName] = useState('')
  const [editInstruction, setEditInstruction] = useState('')
  const [editSprintId, setEditSprintId] = useState<string>()
  const [editRequirementId, setEditRequirementId] = useState<string>()
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [selectedSuiteIds, setSelectedSuiteIds] = useState<Record<string, string | undefined>>({})
  const [importConflict, setImportConflict] = useState<{
    suiteId: string
    conflicts: UiCaseGenerateTaskRunImportConflict[]
  } | null>(null)
  const [importConflictsChanged, setImportConflictsChanged] = useState(false)
  const [expandedSection, setExpandedSection] = useState<'sourceArchive' | 'instruction' | 'runHistory'>('runHistory')
  const [candidateModalOpen, setCandidateModalOpen] = useState(false)
  const [candidateCloseConfirmOpen, setCandidateCloseConfirmOpen] = useState(false)
  const [candidateEditorVersion, setCandidateEditorVersion] = useState(0)

  const taskQuery = useQuery({
    queryKey: ['uiCaseGenerateTask', taskId],
    queryFn: () => api.getUiCaseGenerateTask(taskId),
    enabled: Boolean(taskId),
    retry: false,
  })
  const runsQuery = useQuery({
    queryKey: ['uiCaseGenerateTaskRuns', taskId],
    queryFn: () => api.getUiCaseGenerateTaskRuns(taskId),
    enabled: Boolean(taskId) && !taskQuery.error,
    refetchInterval: (query) => listItems(query.state.data).some((run) => activeRunStatuses.has(run.status ?? '')) ? 2000 : false,
    retry: false,
  })
  const runs = useMemo(
    () => [...listItems(runsQuery.data)].sort((left, right) => new Date(right.createdAt ?? '').getTime() - new Date(left.createdAt ?? '').getTime()),
    [runsQuery.data],
  )

  useEffect(() => {
    if (!selectedRunId && runs[0]?.runId) setSelectedRunId(runs[0].runId)
  }, [runs, selectedRunId])

  const selectedRunQuery = useQuery({
    queryKey: ['uiCaseGenerateTaskRun', selectedRunId],
    queryFn: () => api.getUiCaseGenerateTaskRun(selectedRunId!),
    enabled: Boolean(selectedRunId),
    refetchInterval: (query) => activeRunStatuses.has((query.state.data as UiCaseGenerateTaskRun | undefined)?.status ?? '') ? 2000 : false,
    retry: false,
  })
  const selectedRun = selectedRunQuery.error
    ? undefined
    : selectedRunQuery.data ?? runs.find((run) => run.runId === selectedRunId)

  const editSprintsQuery = useQuery({
    queryKey: ['sprints', 'uiTaskEdit', taskQuery.data?.projectId],
    queryFn: () => api.getSprints(taskQuery.data!.projectId!),
    enabled: editModalOpen && Boolean(taskQuery.data?.projectId),
  })
  const editRequirementsQuery = useQuery({
    queryKey: ['requirements', 'uiTaskEdit', editSprintId],
    queryFn: () => api.getRequirements(editSprintId!),
    enabled: editModalOpen && Boolean(editSprintId),
  })
  const importRequirementId = selectedRun?.requirementId ?? taskQuery.data?.requirementId
  const suitesQuery = useQuery({
    queryKey: ['uiTestSuites', importRequirementId],
    queryFn: () => api.getUiTestSuites(importRequirementId!),
    enabled: importModalOpen && Boolean(importRequirementId),
    retry: false,
  })

  useEffect(() => {
    const nextYaml = selectedRun?.resultYaml ?? ''
    setDraftYaml(nextYaml)
    setSavedYaml(nextYaml)
    setReviewComment('')
  }, [selectedRun?.resultYaml, selectedRun?.runId])

  const hasActiveRun = runs.some((run) => activeRunStatuses.has(run.status ?? ''))
  const resolveRunRecord = (record: UiCaseGenerateTaskRun) =>
    record.runId === selectedRunId && selectedRun ? selectedRun : record
  const { can } = useProjectAccess(taskQuery.data?.projectId ?? '')
  const candidateEditable = selectedRun?.status === 'success' && selectedRun.reviewStatus === 'pending'
  const canEditCandidate = can('write') && candidateEditable
  const hasUnsavedChanges = draftYaml !== savedYaml
  const canReview = canEditCandidate && Boolean(savedYaml.trim()) && !hasUnsavedChanges
  const canImport = isGenerateTaskRunImportable(selectedRun)
  const candidateStats = useMemo(() => {
    const parsed = parseUiCaseCandidate(draftYaml)
    return {
      cases: parsed.cases.length,
      steps: parsed.cases.reduce((total, candidate) => total + candidate.steps.length, 0),
    }
  }, [draftYaml])
  const selectedSuiteId = selectedRunId ? selectedSuiteIds[selectedRunId] : undefined
  const importedSuiteId = selectedRun?.importedTargets.find((target) => target.targetType === 'ui_suite')?.targetId
  const conflictSuiteAvailable = !importConflict
    || listItems(suitesQuery.data).some((suite) => suite.suiteId === importConflict.suiteId)

  const applyImportedRun = useCallback((updatedRun: UiCaseGenerateTaskRun) => {
    queryClient.setQueryData(['uiCaseGenerateTaskRun', updatedRun.runId], updatedRun)
    queryClient.setQueryData<ListResponse<UiCaseGenerateTaskRun>>(['uiCaseGenerateTaskRuns', taskId], (current) => {
      if (!current) return current
      const items = listItems(current).map((item) => (
        item.runId === updatedRun.runId ? updatedRun : item
      )) as ListResponse<UiCaseGenerateTaskRun>
      items.items = items.slice()
      items.total = current.total
      return items
    })
  }, [queryClient, taskId])

  const closeImportInteractions = useCallback(() => {
    setImportModalOpen(false)
    setImportConflict(null)
    setImportConflictsChanged(false)
  }, [])

    function navigateBack() {
      if (!hasUnsavedChanges) {
        navigate('/ai-testing?tab=tasks')
        return
      }
    Modal.confirm({
      mask: { closable: false },
      title: '放弃未保存的候选改动？',
      content: '离开页面后，本次未保存的 YAML 修改将丢失。',
      okText: '放弃并离开',
      okButtonProps: { danger: true },
        onOk: () => navigate('/ai-testing?tab=tasks'),
    })
  }

  function selectRun(runId?: string) {
    if (!runId || runId === selectedRunId) return
    if (!hasUnsavedChanges) {
      setSelectedRunId(runId)
      return
    }
    Modal.confirm({
      mask: { closable: false },
      title: '放弃未保存的候选改动？',
      content: '切换运行记录会丢失当前未保存的 YAML 修改。',
      okText: '放弃并切换',
      okButtonProps: { danger: true },
      onOk: () => setSelectedRunId(runId),
    })
  }

  function closeCandidateModal() {
    if (!hasUnsavedChanges) {
      setCandidateModalOpen(false)
      return
    }
    setCandidateCloseConfirmOpen(true)
  }

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.uploadUiCaseGenerateTaskSourceArchive(taskId, file),
    onSuccess: (updatedTask) => {
      queryClient.setQueryData(['uiCaseGenerateTask', taskId], updatedTask)
      queryClient.invalidateQueries({ queryKey: ['uiCaseGenerateTasks', updatedTask.projectId] })
      message.success(taskQuery.data?.sourceArchive ? '源码包已替换' : '源码包已上传')
      setArchiveModalOpen(false)
      setArchiveFile(undefined)
      navigate(location.pathname, { replace: true, state: null })
    },
  })
  const updateTaskMutation = useMutation({
    mutationFn: () => api.updateUiCaseGenerateTask(taskId, {
      name: editName.trim(),
      sprintId: editSprintId!,
      requirementId: editRequirementId!,
      instruction: editInstruction.trim(),
    }),
    onSuccess: (updatedTask) => {
      queryClient.setQueryData(['uiCaseGenerateTask', taskId], updatedTask)
      queryClient.invalidateQueries({ queryKey: ['uiCaseGenerateTasks', updatedTask.projectId] })
      setEditModalOpen(false)
      message.success('任务已更新')
    },
  })
  const runMutation = useMutation({
    mutationFn: (connectionId: string) => api.runUiCaseGenerateTask(taskId, { connectionId }),
    onSuccess: (createdRun) => {
      setLlmModalOpen(false)
      setSelectedRunId(createdRun.runId)
      queryClient.invalidateQueries({ queryKey: ['uiCaseGenerateTaskRuns', taskId] })
      message.success('任务已加入执行队列')
    },
  })
  const deleteTaskMutation = useMutation({
    mutationFn: () => api.deleteUiCaseGenerateTask(taskId),
      onSuccess: () => {
        message.success('任务已删除')
        navigate('/ai-testing?tab=tasks')
      },
  })
  const deleteRunMutation = useMutation({
    mutationFn: (runId: string) => api.deleteUiCaseGenerateTaskRun(runId),
    onSuccess: (_data, runId) => {
      message.success('运行记录已删除')
      if (selectedRunId === runId) {
        // 被删的运行记录同时是候选编辑器的来源，未保存的改动随之作废。
        setSelectedRunId(undefined)
        setDraftYaml('')
        setSavedYaml('')
      }
      queryClient.removeQueries({ queryKey: ['uiCaseGenerateTaskRun', runId], exact: true })
      queryClient.invalidateQueries({ queryKey: ['uiCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })
  const saveMutation = useMutation({
    mutationFn: () => api.updateUiCaseGenerateTaskRunResult(selectedRunId!, { resultYaml: draftYaml }),
    onSuccess: (updatedRun) => {
      queryClient.setQueryData(['uiCaseGenerateTaskRun', selectedRunId], updatedRun)
      setSavedYaml(updatedRun.resultYaml ?? draftYaml)
      setDraftYaml(updatedRun.resultYaml ?? draftYaml)
      message.success('候选结果已保存')
    },
  })
  const reviewMutation = useMutation({
    mutationFn: (action: 'approve' | 'reject') => api.reviewUiCaseGenerateTaskRun(selectedRunId!, {
      action,
      ...(reviewComment.trim() ? { reviewComment: reviewComment.trim() } : {}),
    }),
    onSuccess: (updatedRun) => {
      queryClient.setQueryData(['uiCaseGenerateTaskRun', selectedRunId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['uiCaseGenerateTaskRuns', taskId] })
      message.success(updatedRun.reviewStatus === 'approved' ? '候选结果已批准' : '候选结果已拒绝')
    },
  })
  const importMutation = useMutation({
    mutationFn: (payload: { suiteId: string; confirmOverwrite: boolean }) => (
      api.importUiCaseGenerateTaskRun(selectedRunId!, payload)
    ),
    onSuccess: (result, payload) => {
      if (result.requiresConfirmation) {
        setImportModalOpen(false)
        setImportConflict({ suiteId: payload.suiteId, conflicts: result.conflicts })
        setImportConflictsChanged(payload.confirmOverwrite)
        return
      }
      applyImportedRun(result.run)
      closeImportInteractions()
      message.success('正式 UI 用例导入成功')
    },
    onError: async (error) => {
      if (error instanceof ApiError && (error.status === 400 || error.status === 404)) {
        const refreshed = await selectedRunQuery.refetch()
        if (error.status === 404) suitesQuery.refetch()
        if (refreshed.data?.importStatus === 'imported') {
          applyImportedRun(refreshed.data)
          closeImportInteractions()
          message.info('该运行已由其他操作完成导入')
        }
      }
    },
  })

  async function openImportModal() {
    importMutation.reset()
    const refreshed = await selectedRunQuery.refetch()
    const latestRun = refreshed.data
    if (latestRun?.importStatus === 'imported') {
      applyImportedRun(latestRun)
      closeImportInteractions()
      message.info('该运行已由其他操作完成导入')
      return
    }
    if (isGenerateTaskRunImportable(latestRun)) {
      setImportModalOpen(true)
    }
  }

  useEffect(() => {
    const refreshOnFocus = () => {
      if (selectedRunId) selectedRunQuery.refetch()
    }
    window.addEventListener('focus', refreshOnFocus)
    return () => window.removeEventListener('focus', refreshOnFocus)
  }, [selectedRunId, selectedRunQuery])

  useEffect(() => {
    if (selectedRun?.importStatus !== 'imported' || (!importModalOpen && !importConflict)) return
    applyImportedRun(selectedRun)
    closeImportInteractions()
    message.info('该运行已由其他操作完成导入')
  }, [applyImportedRun, closeImportInteractions, importConflict, importModalOpen, selectedRun])

  useEffect(() => {
    if (!selectedRunId || !selectedSuiteId || !suitesQuery.isSuccess) return
    if (listItems(suitesQuery.data).some((suite) => suite.suiteId === selectedSuiteId)) return
    setSelectedSuiteIds((current) => ({ ...current, [selectedRunId]: undefined }))
    message.warning('上次选择的 UI 套件已不可用，请重新选择')
  }, [selectedRunId, selectedSuiteId, suitesQuery.data, suitesQuery.isSuccess])

  if (taskQuery.isLoading) return <div className="workbench-page"><Spin /></div>
  if (taskQuery.error) {
    return <div className="workbench-page"><Alert showIcon type="error" title={getErrorMessage(taskQuery.error)} description="无法访问该 UI 生成任务。" /></div>
  }
  const task = taskQuery.data
  if (!task) return <div className="workbench-page"><Empty description="任务不存在" /></div>

  const archiveValidationError = validateUiSourceArchive(archiveFile)
  const replacementBlocked = hasActiveRun
  return (<ProjectAccessScope resourceError={taskQuery.error} projectId={task?.projectId ?? ''}>{(
    <div className="workbench-page ai-testing-page">
      <div className="workbench-tabs">
        {runMutation.error ? <Alert showIcon type="error" title={getErrorMessage(runMutation.error)} /> : null}
        {selectedRunQuery.error ? (
          <Alert
            showIcon
            type="error"
            title={getErrorMessage(selectedRunQuery.error)}
            description="无权访问该运行，候选内容已隐藏。"
          />
        ) : null}
        <div className="ai-task-detail-layout ui-case-task-detail-layout">
          <Card className="ai-task-detail-summary-card">
            <div className="ai-task-detail-inline-meta">
              <Button aria-label="返回生成任务" icon={<ArrowLeftOutlined aria-hidden />} onClick={navigateBack}>返回生成任务</Button>
              {[
                ['任务名称', task.name], ['迭代', task.sprintId || '-'], ['需求', 'UI 用例生成'],
                ['来源类型', '源码包'], ['创建人', task.creatorUserId || '-'], ['更新时间', formatTime(task.updatedAt)],
              ].map(([label, value]) => <div key={label} className="ai-task-detail-inline-item"><span className="ai-task-detail-inline-label">{label}</span><span className="ai-task-detail-inline-value">{value}</span></div>)}
              <div className="ai-task-detail-inline-actions">
                <Tooltip title={!task.sourceArchive ? '请先上传源码 ZIP' : hasActiveRun ? '任务执行中，暂时不能重复运行' : '运行任务'}><span><ProjectActionButton action="execute" aria-label="运行任务" className="action-btn-run" operation="run" disabled={!task.sourceArchive || hasActiveRun} onClick={() => setLlmModalOpen(true)}>运行</ProjectActionButton></span></Tooltip>
                <ProjectActionButton action="write" aria-label="编辑任务" className="action-btn-update" operation="edit" onClick={() => { setEditName(task.name); setEditInstruction(task.instruction); setEditSprintId(task.sprintId); setEditRequirementId(task.requirementId); setEditModalOpen(true) }}>编辑</ProjectActionButton>
                <Popconfirm title="确认删除该任务？" onConfirm={() => deleteTaskMutation.mutate()}><ProjectActionButton operation="delete" action="write" danger className="action-btn-delete" loading={deleteTaskMutation.isPending}>删除</ProjectActionButton></Popconfirm>
              </div>
            </div>
          </Card>

          <div className="ai-task-detail-split">
            <aside className="ai-task-detail-nav-panel">
              <div className="ai-task-detail-nav-head">
                <span className="ai-task-detail-nav-head-title">任务信息</span>
                <span className="ai-task-detail-nav-head-sub">导航</span>
              </div>
              <div className="ai-task-detail-nav-body">
                <div className="ai-task-detail-nav-label">输入</div>
                <button type="button" className={`ai-task-detail-nav-item${expandedSection === 'sourceArchive' ? ' active' : ''}`} onClick={() => setExpandedSection('sourceArchive')}>
                  <span className="ai-task-detail-nav-item-title">源码包</span>
                  <span className="ai-task-detail-nav-item-sub">{task.sourceArchive?.filename || '尚未上传源码包'}</span>
                </button>
                <button type="button" className={`ai-task-detail-nav-item${expandedSection === 'instruction' ? ' active' : ''}`} onClick={() => setExpandedSection('instruction')}>
                  <span className="ai-task-detail-nav-item-title">生成指令</span>
                  <span className="ai-task-detail-nav-item-sub">{task.instruction?.trim() || '暂无补充指令'}</span>
                </button>
                <div className="ai-task-detail-nav-label">输出</div>
                <button type="button" className={`ai-task-detail-nav-item${expandedSection === 'runHistory' ? ' active' : ''}`} onClick={() => setExpandedSection('runHistory')}>
                  <span className="ai-task-detail-nav-item-title">运行记录</span>
                  <span className="ai-task-detail-nav-item-sub">共 {runs.length} 条运行记录</span>
                </button>
                <div className="ai-task-detail-nav-tip">点击左侧条目在右侧查看内容，运行时记录自动刷新。</div>
              </div>
            </aside>

            <section className="ai-task-detail-main-panel">
              {expandedSection === 'sourceArchive' ? (
                <>
                  <div className="ai-task-detail-main-head">
                    <span className="ai-task-detail-main-head-title">源码包</span>
                    <div className="ai-task-detail-main-head-extra">
                      <Tooltip title={replacementBlocked ? '存在执行中的运行，完成后才能替换源码包' : undefined}>
                        <span><ProjectActionButton action="write" size="small" icon={task.sourceArchive ? <EditOutlined /> : <UploadOutlined />} disabled={replacementBlocked} onClick={() => setArchiveModalOpen(true)}>{task.sourceArchive ? '替换源码包' : '上传源码包'}</ProjectActionButton></span>
                      </Tooltip>
                    </div>
                  </div>
                  <div className="ai-task-detail-main-body">
                    {task.sourceArchive ? <Descriptions column={2} items={[{ key: 'filename', label: '文件名', children: task.sourceArchive.filename }, { key: 'size', label: '大小', children: formatBytes(task.sourceArchive.sizeBytes) }, { key: 'uploadedAt', label: '上传时间', children: formatTime(task.sourceArchive.uploadedAt) }, { key: 'sha256', label: 'SHA256', children: <Text code copyable>{task.sourceArchive.sha256}</Text> }]} /> : <Alert showIcon type="info" title="请先上传源码 ZIP" description="没有有效源码包时不能运行任务。" />}
                  </div>
                </>
              ) : expandedSection === 'instruction' ? (
                <>
                  <div className="ai-task-detail-main-head"><span className="ai-task-detail-main-head-title">生成指令</span></div>
                  <div className="ai-task-detail-main-body"><pre className="ai-task-code-block">{task.instruction || '-'}</pre></div>
                </>
              ) : (
                <>
                  <div className="ai-task-detail-main-head">
                    <span className="ai-task-detail-main-head-title">运行记录</span>
                    <div className="ai-task-detail-main-head-extra"><div className="ai-task-run-history-toolbar"><span className="ai-task-run-history-auto-refresh">每 5 秒自动刷新</span><ActionButton size="small" operation="refresh" onClick={() => { runsQuery.refetch(); selectedRunQuery.refetch() }}>刷新</ActionButton></div></div>
                  </div>
                  <div className="ai-task-detail-main-body">
                    {runsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(runsQuery.error)} /> : null}
                    {runsQuery.isLoading ? (
                      <Spin />
                    ) : runs.length ? (
                      <>
                        <RunHistoryTable<UiCaseGenerateTaskRun>
                          rows={runs}
                          getRunId={(record) => record.runId}
                          selectedRunId={selectedRunId}
                          resolveRow={resolveRunRecord}
                          onSelect={(runId) => selectRun(runId)}
                          renderStatus={(row) => <RunPipelineStatus run={resolveRunRecord(row)} />}
                          getReviewedAt={(row) => resolveRunRecord(row).reviewedAt}
                          getReviewComment={(row) => resolveRunRecord(row).reviewComment}
                          getImportedAt={(row) => resolveRunRecord(row).importedAt}
                          renderActions={(row) => {
                            const data = resolveRunRecord(row)
                            const importedSuiteId = (data.importedTargets ?? []).find((target) => target.targetType === 'ui_suite')?.targetId
                            const label = canEditCandidate && data.runId === selectedRunId ? '审核结果' : '查看候选结果'
                            const menuItems: RunMenuAction[] = [
                              ...(can('execute') && isGenerateTaskRunImportable(data)
                                ? [{ key: 'importSuite', label: '导入正式 UI 套件', disabled: importMutation.isPending }]
                                : []),
                              ...(data.importStatus === 'imported' && importedSuiteId
                                ? [{ key: 'openSuite', label: '查看正式套件' }]
                                : []),
                              ...(row.runId && can('write')
                                ? [{
                                    key: 'deleteRun',
                                    label: '删除运行记录',
                                    danger: true,
                                    disabled: !isRunDeletable(data.status) || deleteRunMutation.isPending,
                                  }]
                                : []),
                            ]
                            return (
                              <RunRowActions
                                inline={
                                  /* 候选结果入口（含审核）直接放在操作列，「更多」只留导入等状态变更操作。 */
                                  can('read') ? (
                                    <Button
                                      size="small"
                                      type="primary"
                                      onClick={(event) => {
                                        event.stopPropagation()
                                        selectRun(row.runId)
                                        setCandidateModalOpen(true)
                                      }}
                                    >
                                      {label}
                                    </Button>
                                  ) : null
                                }
                                menuItems={menuItems}
                                onMenuAction={(key) => {
                                  if (key === 'importSuite') {
                                    selectRun(row.runId)
                                    openImportModal()
                                    return
                                  }
                                  if (key === 'openSuite' && importedSuiteId) {
                                    navigate(`/ui-automation/suites/${importedSuiteId}`)
                                    return
                                  }
                                  if (key === 'deleteRun' && row.runId) {
                                    const runId = row.runId
                                    confirmDeleteRun(() => deleteRunMutation.mutate(runId))
                                  }
                                }}
                              />
                            )
                          }}
                        />
                      </>
                    ) : (
                      <div className="ai-task-run-history-placeholder"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有运行记录" /></div>
                    )}
                  </div>
                </>
              )}
            </section>
          </div>
        </div>
      </div>

      <Modal
        mask={{ closable: false }}
        className="ai-task-import-result-modal ui-task-candidate-result-modal"
        title={canEditCandidate ? '审核结果' : 'UI 用例候选结果'}
        open={candidateModalOpen}
        onCancel={closeCandidateModal}
        footer={[
          <Button
            key="close"
            aria-label={canEditCandidate ? '取消' : '关闭'}
            onClick={closeCandidateModal}
          >
            {canEditCandidate ? '取消' : '关闭'}
          </Button>,
          ...(candidateEditable ? [
            <ProjectActionButton action="write"
              key="save"
              disabled={!hasUnsavedChanges}
              loading={saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              保存候选结果
            </ProjectActionButton>,
            <ProjectActionButton action="review"
              key="reject"
              danger
              ghost
              disabled={!canReview}
              loading={reviewMutation.isPending}
              onClick={() => reviewMutation.mutate('reject')}
            >
              拒绝候选
            </ProjectActionButton>,
            <ProjectActionButton action="review"
              key="approve"
              type="primary"
              disabled={!canReview}
              loading={reviewMutation.isPending}
              onClick={() => reviewMutation.mutate('approve')}
            >
              批准候选
            </ProjectActionButton>,
          ] : []),
          ...(canImport ? [
            <ProjectActionButton action="execute" key="import" type="primary" aria-label="导入正式 UI 套件" onClick={openImportModal}>
              导入正式 UI 套件
            </ProjectActionButton>,
          ] : []),
          ...(selectedRun?.importStatus === 'imported' && importedSuiteId ? [
            <Button key="view-suite" type="primary" onClick={() => navigate(`/ui-automation/suites/${importedSuiteId}`)}>
              查看正式套件
            </Button>,
          ] : []),
        ]}
        destroyOnHidden
        width="min(1620px, calc(100vw - 72px))"
        centered
      >
        {selectedRunQuery.error ? (
          <Alert showIcon type="error" title={getErrorMessage(selectedRunQuery.error)} />
        ) : selectedRun ? (
          <div className="ai-task-import-result-form">
            <ImportMigrationWarning importMigrationComplete={selectedRun.importMigrationComplete} />
            <div className="ai-task-import-target-summary">
              <div className="ai-task-import-target-copy">
                <strong>候选结果</strong>
                <span title={taskQuery.data?.requirementId ?? undefined}>
                  关联需求：{taskQuery.data?.requirementId || '-'}
                </span>
              </div>
              <div className="ai-task-import-target-stats">
                <Tag color="blue">用例 {candidateStats.cases}</Tag>
                <Tag color="purple">步骤 {candidateStats.steps}</Tag>
              </div>
            </div>
            <Tabs
              items={[
                {
                  key: 'preview',
                  label: '结构化预览',
                  children: (
                    <div className="ai-task-review-modal-content ai-task-result-preview-modal-content ai-task-import-result-preview-content single-column">
                      <div className="ai-task-review-modal-section">
                        <div className="ai-task-review-modal-preview ai-task-import-result-preview ui-task-candidate-preview">
                          <CandidatePreview yaml={draftYaml} />
                        </div>
                      </div>
                    </div>
                  ),
                },
                {
                  key: 'yaml',
                  label: '编辑 YAML',
                  children: (
                    <div className="ai-task-review-modal-content single-column ui-task-candidate-yaml-pane">
                      <TextCodeEditor
                        key={candidateEditorVersion}
                        value={draftYaml}
                        onChange={setDraftYaml}
                        readOnly={!canEditCandidate}
                        ariaLabel="候选结果 YAML"
                        language="yaml"
                        foldable
                        height="100%"
                        minHeight={0}
                      />
                      {saveMutation.error ? (
                        <Alert showIcon type="error" title={getErrorMessage(saveMutation.error)} />
                      ) : null}
                    </div>
                  ),
                },
              ]}
            />
            {reviewMutation.error ? (
              <Alert showIcon type="error" title={getErrorMessage(reviewMutation.error)} />
            ) : null}
            <div className="ui-task-candidate-review-note">
              <label htmlFor="ui-review-comment">审核备注</label>
              <Input.TextArea
                id="ui-review-comment"
                aria-label="审核备注"
                rows={3}
                placeholder="请输入审核备注或拒绝原因"
                value={reviewComment}
                disabled={!canEditCandidate}
                onChange={(event) => setReviewComment(event.target.value)}
              />
            </div>
          </div>
        ) : (
          <Empty description="请选择一条运行记录查看候选结果" />
        )}
      </Modal>

      <ProjectActionModal action="write"
        mask={{ closable: false }}
        title="放弃未保存的候选改动？"
        open={candidateCloseConfirmOpen}
        okText="放弃修改"
        cancelText="继续编辑"
        okButtonProps={{ danger: true }}
        onCancel={() => setCandidateCloseConfirmOpen(false)}
        onOk={() => {
          setDraftYaml(savedYaml)
          setCandidateEditorVersion((current) => current + 1)
          setCandidateCloseConfirmOpen(false)
          setCandidateModalOpen(false)
        }}
      >
        关闭弹窗后，本次未保存的 YAML 修改将丢失。
      </ProjectActionModal>

      <ProjectActionModal action="execute"
        mask={{ closable: false }}
        title="导入正式 UI 套件"
        open={importModalOpen}
        okText="开始导入"
        cancelText="取消"
        okButtonProps={{
          disabled: !selectedSuiteId || suitesQuery.isLoading || Boolean(suitesQuery.error) || importMutation.isPending,
          loading: importMutation.isPending,
        }}
        cancelButtonProps={{ disabled: importMutation.isPending }}
        onCancel={() => { if (!importMutation.isPending) setImportModalOpen(false) }}
        onOk={() => selectedSuiteId && importMutation.mutate({ suiteId: selectedSuiteId, confirmOverwrite: false })}
      >
        {suitesQuery.error ? <Alert showIcon type="error" title={uiImportErrorMessage(suitesQuery.error)} style={{ marginBottom: 12 }} /> : null}
        {importMutation.error ? <Alert showIcon type="error" title={uiImportErrorMessage(importMutation.error)} style={{ marginBottom: 12 }} /> : null}
        <Select
          aria-label="目标 UI 套件"
          showSearch
          optionFilterProp="label"
          placeholder="请选择当前需求下的 UI 套件"
          loading={suitesQuery.isLoading}
          disabled={importMutation.isPending}
          value={selectedSuiteId}
          options={listItems(suitesQuery.data).map((suite) => ({ label: suite.name, value: suite.suiteId }))}
          notFoundContent={suitesQuery.isLoading ? '加载中' : '当前需求下暂无可用套件'}
          onChange={(suiteId) => {
            if (!selectedRunId) return
            setSelectedSuiteIds((current) => ({ ...current, [selectedRunId]: suiteId }))
          }}
          style={{ width: '100%' }}
        />
      </ProjectActionModal>

      <UiImportConflictModal
        open={Boolean(importConflict)}
        conflicts={importConflict?.conflicts ?? []}
        loading={importMutation.isPending}
        errorMessage={importConflict && importMutation.error ? uiImportErrorMessage(importMutation.error) : undefined}
        conflictsChanged={importConflictsChanged}
        confirmDisabled={!conflictSuiteAvailable}
        onCancel={() => {
          if (importMutation.isPending) return
          importMutation.reset()
          setImportConflict(null)
          setImportConflictsChanged(false)
        }}
        onConfirm={() => {
          if (!importConflict || importMutation.isPending || !conflictSuiteAvailable) return
          importMutation.reset()
          importMutation.mutate({ suiteId: importConflict.suiteId, confirmOverwrite: true })
        }}
      />

      <ProjectActionModal action="write"
        mask={{ closable: false }}
        title="编辑 UI 用例生成任务"
        open={editModalOpen}
        okText="保存"
        okButtonProps={{ disabled: !editName.trim() || !editSprintId || !editRequirementId, loading: updateTaskMutation.isPending }}
        cancelButtonProps={{ disabled: updateTaskMutation.isPending }}
        onCancel={() => setEditModalOpen(false)}
        onOk={() => updateTaskMutation.mutate()}
      >
        {updateTaskMutation.error ? <Alert showIcon type="error" title={getErrorMessage(updateTaskMutation.error)} style={{ marginBottom: 12 }} /> : null}
        <Space orientation="vertical" style={{ width: '100%' }}>
          <label>任务名称<Input aria-label="编辑任务名称" value={editName} maxLength={120} onChange={(event) => setEditName(event.target.value)} /></label>
          <label>所属迭代<Select aria-label="编辑所属迭代" value={editSprintId} loading={editSprintsQuery.isLoading} options={listItems(editSprintsQuery.data).map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) }))} onChange={(value) => { setEditSprintId(value); setEditRequirementId(undefined) }} style={{ width: '100%' }} /></label>
          <label>所属需求<Select aria-label="编辑所属需求" value={editRequirementId} loading={editRequirementsQuery.isLoading} options={listItems(editRequirementsQuery.data).map((requirement) => ({ label: requirement.name, value: normalizeRequirementId(requirement) }))} onChange={setEditRequirementId} style={{ width: '100%' }} /></label>
          <label>生成指令<Input.TextArea aria-label="编辑生成指令" value={editInstruction} maxLength={1000} onChange={(event) => setEditInstruction(event.target.value)} /></label>
        </Space>
      </ProjectActionModal>

      <ProjectActionModal action="write"
        mask={{ closable: false }}
        title={task.sourceArchive ? '确认替换源码包' : '上传源码包'}
        open={archiveModalOpen}
        onCancel={() => { if (!uploadMutation.isPending) { setArchiveModalOpen(false); setArchiveFile(undefined) } }}
        okText={task.sourceArchive ? '确认替换' : '确认上传'}
        okButtonProps={{ disabled: Boolean(archiveValidationError), loading: uploadMutation.isPending }}
        cancelButtonProps={{ disabled: uploadMutation.isPending }}
        onOk={() => archiveFile && uploadMutation.mutate(archiveFile)}
      >
        {pendingNavigationError && !uploadMutation.error ? <Alert showIcon type="error" title={pendingNavigationError} style={{ marginBottom: 12 }} /> : null}
        {uploadMutation.error ? <Alert showIcon type="error" title={archiveErrorMessage(uploadMutation.error)} style={{ marginBottom: 12 }} /> : null}
        {task.sourceArchive ? <Alert showIcon type="warning" title={`当前：${task.sourceArchive.filename}`} description="替换只影响后续运行；替换失败时当前源码包仍然有效。" style={{ marginBottom: 12 }} /> : null}
        <input aria-label="新的源码 ZIP" type="file" accept=".zip,application/zip" disabled={uploadMutation.isPending} onChange={(event) => setArchiveFile(event.target.files?.[0])} />
        {archiveFile ? <Text style={{ display: 'block', marginTop: 8 }}>新文件：{archiveFile.name}</Text> : null}
        {archiveFile && archiveValidationError ? <Alert showIcon type="error" title={archiveValidationError} style={{ marginTop: 12 }} /> : null}
      </ProjectActionModal>

      <LlmConnectionSelectModal
        open={llmModalOpen}
        projectId={task.projectId}
        loading={runMutation.isPending}
        onClose={() => setLlmModalOpen(false)}
        onConfirm={(connectionId) => runMutation.mutate(connectionId)}
      />
    </div>
  )}</ProjectAccessScope>)
}
