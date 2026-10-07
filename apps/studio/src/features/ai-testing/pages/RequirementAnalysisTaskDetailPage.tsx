import { RequirementMaterialComparison } from '../components/RequirementMaterialComparison'
import { RequirementUnderstandingComparison } from '../components/RequirementUnderstandingComparison'
import { listTotal } from '@/shared/api/request'
import { getRunPollingInterval, RUN_HISTORY_POLL_INTERVAL } from '@/domain/runs/polling'
import { useTaskRunHistorySync } from '@/features/ai-testing/hooks/useTaskRunHistorySync'
import { useDeleteTaskRun, useStartTaskRun } from '@/features/ai-testing/hooks/useTaskRunActions'
import { formatStructuredContent } from '@/shared/utils/value'
import { RevisionDivider, RevisionSidePanel } from '../components/RevisionSidePanel'
import { TaskDetailInstructionEditor, TaskDetailNavItem, TaskDetailNavPanel, TaskDetailToolbar } from '../components/TaskDetailShell'
import { RunArtifacts, RunPipelineStatus } from '../components/RunPipelineStatus'
import { RunHistoryTable, RunRowActions } from '../components/RunHistoryTable'
import { confirmDeleteRun, isRunDeletable } from '../utils/runDeletion'
import { buildRevisionTemplate, getRevisionQuestions } from '../utils/functionalRevision'
import { parseRequirementArtifact } from '@/domain/requirements/requirementArtifact'
import { ActionButton } from '@/shared/components/ActionButton'
import { usePersonalLlmChoice } from '../hooks/usePersonalLlmChoice'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ArrowLeftOutlined, CodeOutlined, FileTextOutlined, HistoryOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Form, Modal, Popconfirm, Spin, Tag, Tabs } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { goBackOrFallback } from '@/shared/utils/backNavigation'
import {
  RequirementAnalysisRunModal,
  type RequirementAnalysisRunFormValues,
} from '../components/RequirementAnalysisRunModal'
import {
  RequirementAnalysisTaskDrawer,
  type RequirementAnalysisTaskFormValues,
} from '../components/RequirementAnalysisTaskDrawer'
import type { RequirementAnalysisTaskRun } from '../types'
import {
  getApiCaseGenerateTaskRunStatusMeta,
  isRunnableApiCaseGenerateTaskRun,
  renderApiCaseGenerateTaskRunStatusTag,
} from '../utils/taskStatus'
import '@/shared/styles/surface-tokens.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-review.css'
import '@/features/ai-testing/styles/run-result.css'
import '@/features/ai-testing/styles/task-detail-v2.css'
import './RequirementAnalysisTaskDetailPage.css'
import { RequirementDocumentPreviewContent } from '@/features/requirements/components/RequirementDocumentPreviewModal'
import type { Requirement } from '@/features/requirements/types'
import { hasRequirementDocument } from '@/features/requirements/utils/requirementDocument'
import { api, listItems } from '@/services/api'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage, normalizeRequirementId, normalizeSprintId, pickUpdatedAt } from '@/utils/format'

type RequirementPoolItem = Requirement & {
  sprintName: string
  sprintIdForCreate: string
}

const runResultSectionDefinitions = [
  { key: 'firstStepOutput', label: '材料提取结果' },
  { key: 'resultYaml', label: '需求理解记录' },
  { key: 'errorMessage', label: '错误信息' },
] as const

type RunResultSectionKey = (typeof runResultSectionDefinitions)[number]['key']

type RunResultModalState = {
  key: RunResultSectionKey
  label: string
  mode: 'view' | 'review'
  runId?: string
} | null

const requirementAnalysisStageMetaMap: Record<string, { label: string; color: string }> = {
  extracting_text: { label: '材料提取与整理', color: 'cyan' },
  feature_understanding: { label: '需求理解与确认', color: 'purple' },
  completed: { label: '需求理解与确认', color: 'purple' },
}

const requirementAnalysisFinalStages = ['feature_understanding', 'completed']

const requirementAnalysisStageFieldMap: Record<string, { key: 'firstStepOutput'; label: string }> = {
  extracting_text: { key: 'firstStepOutput', label: '材料提取结果' },
}

function getRunSortTime(run: RequirementAnalysisTaskRun) {
  const time = new Date(run.createdAt || run.startedAt || run.updatedAt || '').getTime()
  return Number.isNaN(time) ? 0 : time
}

function parseConfigJsonRecord(configJson?: unknown): Record<string, unknown> {
  if (!configJson) return {}
  if (typeof configJson === 'object' && !Array.isArray(configJson)) {
    return configJson as Record<string, unknown>
  }
  if (typeof configJson !== 'string' || !configJson.trim()) return {}
  try {
    const parsed = JSON.parse(configJson)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    return {}
  }
  return {}
}

function getRequirementAnalysisStageMeta(stage?: string) {
  if (!stage) return { label: '-', color: 'default' }
  return requirementAnalysisStageMetaMap[stage] ?? { label: stage, color: 'default' }
}

function getRequirementAnalysisStageField(stage?: string) {
  if (!stage) return undefined
  return requirementAnalysisStageFieldMap[stage]
}

function normalizeInstruction(instruction?: string) {
  return instruction?.trim() ?? ''
}

export function RequirementAnalysisTaskDetailPage() {
  const { taskId = '' } = useParams()
  const [runPage, setRunPage] = useState(1)
  const [runPageSize, setRunPageSize] = useState(20)
  useEffect(() => { setRunPage(1) }, [taskId])
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerSprintId, setDrawerSprintId] = useState<string | undefined>(undefined)
  const [runModalOpen, setRunModalOpen] = useState(false)
  const [activeSection, setActiveSection] = useState<'instruction' | 'sourceContent' | 'runHistory'>('runHistory')
  const [selectedRunRecordId, setSelectedRunRecordId] = useState<string | null>(null)
  const [runResultModal, setRunResultModal] = useState<RunResultModalState>(null)
  const [stageOutputDraft, setStageOutputDraft] = useState('')
  const [stageOutputDirty, setStageOutputDirty] = useState(false)
  const [stageOutputSourceKey, setStageOutputSourceKey] = useState('')
  const [stageReviewAction, setStageReviewAction] = useState<'approve' | 'reject' | 'revise' | null>(null)
  const [reviseModalOpen, setReviseModalOpen] = useState(false)
  const [revisionFooter, setRevisionFooter] = useState<HTMLDivElement | null>(null)
  const [revisionInstruction, setRevisionInstruction] = useState('')
  const [revisionTemplate, setRevisionTemplate] = useState('')
  const [revisionDraftKey, setRevisionDraftKey] = useState('')
  const [instructionDraft, setInstructionDraft] = useState('')
  const [instructionDirty, setInstructionDirty] = useState(false)
  const [form] = Form.useForm<RequirementAnalysisTaskFormValues>()

  const taskQuery = useQuery({
    queryKey: ['requirementAnalysisTask', taskId],
    queryFn: () => api.getRequirementAnalysisTask(taskId),
    enabled: Boolean(taskId),
  })

  const task = taskQuery.data
  const { can } = useProjectAccess(task?.projectId ?? '')
  const personalLlm = usePersonalLlmChoice(task?.projectId)

  const boundRequirementQuery = useQuery({
    queryKey: ['requirement', 'requirementAnalysisTaskDetail', task?.requirementId],
    queryFn: () => api.getRequirement(task!.requirementId!),
    enabled: Boolean(task?.requirementId),
  })

  const runsQuery = useQuery({
    queryKey: ['requirementAnalysisTaskRuns', taskId, runPage, runPageSize],
    queryFn: () => api.getRequirementAnalysisTaskRuns(taskId, { page: runPage, pageSize: runPageSize }),
    enabled: Boolean(taskId),
    refetchInterval: activeSection === 'runHistory' ? RUN_HISTORY_POLL_INTERVAL : false,
  })
  const runTotal = listTotal(runsQuery.data)
  useEffect(() => {
    if (runsQuery.data && !runsQuery.isFetching && !runsQuery.error) {
      const lastPage = Math.max(1, Math.ceil(runTotal / runPageSize))
      if (runPage > lastPage) setRunPage(lastPage)
    }
  }, [runPage, runPageSize, runTotal, runsQuery.data, runsQuery.isFetching, runsQuery.error])
  const runPagination = {
    current: runPage, pageSize: runPageSize, total: runTotal,
    loading: runsQuery.isFetching || Boolean(runsQuery.error),
    onChange: (page: number, size: number) => { setRunPage(size === runPageSize ? page : 1); setRunPageSize(size) },
  }
  const refetchRunHistory = runsQuery.refetch
  useEffect(() => {
    if (activeSection === 'runHistory') void refetchRunHistory({ cancelRefetch: false })
  }, [activeSection, refetchRunHistory])


  const sprintsQuery = useQuery({
    queryKey: ['sprints', 'requirementAnalysisTaskDetail', task?.projectId],
    queryFn: async () => {
      if (!task?.projectId) return []
      return api.getSprints(task.projectId)
    },
    enabled: Boolean(task?.projectId),
  })

  const requirementsQuery = useQuery({
    queryKey: ['requirementsPool', 'requirementAnalysisTaskDetail', task?.projectId],
    queryFn: async () => {
      if (!sprintsQuery.data || sprintsQuery.data.length === 0) return [] as RequirementPoolItem[]
      const groups = await Promise.all(
        sprintsQuery.data.map(async (sprint) => {
          const sprintId = normalizeSprintId(sprint)
          const requirements = await api.getRequirements(sprintId)
          return requirements.map((requirement) => ({
            ...requirement,
            sprintName: sprint.name,
            sprintIdForCreate: sprintId,
          }))
        }),
      )
      return groups.flat()
    },
    enabled: Boolean(task?.projectId) && !sprintsQuery.isLoading,
  })

  const sprintOptions = useMemo(
    () => listItems(sprintsQuery.data).map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) })),
    [sprintsQuery.data],
  )
  const requirementOptions = useMemo(
    () =>
      listItems(requirementsQuery.data)
        .filter((requirement) => !drawerSprintId || requirement.sprintIdForCreate === drawerSprintId)
        .map((requirement) => ({
          label: `${requirement.name}${drawerSprintId ? '' : `（${requirement.sprintName}）`}`,
          value: normalizeRequirementId(requirement),
        })),
    [drawerSprintId, requirementsQuery.data],
  )
  const sprintNameMap = useMemo(
    () => new Map(listItems(sprintsQuery.data).map((sprint) => [normalizeSprintId(sprint), sprint.name])),
    [sprintsQuery.data],
  )
  const requirementMap = useMemo(
    () => new Map(listItems(requirementsQuery.data).map((requirement) => [normalizeRequirementId(requirement), requirement])),
    [requirementsQuery.data],
  )
  const boundRequirement = boundRequirementQuery.data ?? (task?.requirementId ? requirementMap.get(task.requirementId) : undefined)

  const runRecords = useMemo(
    () => [...listItems(runsQuery.data)].sort((left, right) => getRunSortTime(right) - getRunSortTime(left)),
    [runsQuery.data],
  )
  const latestRunRecord = runsQuery.data?.latestRun ?? runRecords[0]
  const selectedRunId = selectedRunRecordId ?? runRecords[0]?.runId ?? ''
  const selectedRunQuery = useQuery({
    queryKey: ['requirementAnalysisRun', selectedRunId],
    queryFn: () => api.getRequirementAnalysisRun(selectedRunId),
    enabled: Boolean(selectedRunId),
    refetchInterval: (query) => activeSection === 'runHistory' ? getRunPollingInterval(query.state.data?.status) : false,
  })
  useTaskRunHistorySync({
    historyKey: 'requirementAnalysisTaskRuns', detailKey: 'requirementAnalysisRun', taskId, selectedRunId,
    history: runsQuery.data, detail: selectedRunQuery.data,
  })
  const selectedRun = selectedRunQuery.data
  const resolveRunRecord = (record: RequirementAnalysisTaskRun) =>
    record.runId === selectedRunId && selectedRun ? selectedRun : record
  const selectedRunRecord = useMemo(
    () => runRecords.find((record) => record.runId === selectedRunId),
    [runRecords, selectedRunId],
  )
  const activeSelectedRun = selectedRun?.runId === selectedRunId ? selectedRun : selectedRunRecord
  const selectedRunConfigJson = useMemo(() => parseConfigJsonRecord(selectedRun?.configJson), [selectedRun?.configJson])
  const selectedStage = selectedRun?.currentStage
  const selectedStageField = getRequirementAnalysisStageField(selectedStage)
  const selectedStageMeta = getRequirementAnalysisStageMeta(selectedStage)
  const selectedStageStatusMeta = selectedRun?.stageStatus === 'completed'
    ? { label: selectedRun.reviewStatus === 'approved' ? '已审核' : '待审核', color: selectedRun.reviewStatus === 'approved' ? 'success' : 'warning' }
    : getApiCaseGenerateTaskRunStatusMeta(selectedRun?.stageStatus)
  const selectedRunStatus = String(selectedRun?.status ?? '').toLowerCase()
  const selectedRunReviewStatus = String(selectedRun?.reviewStatus ?? '').toLowerCase()
  useEffect(() => { if (selectedRunReviewStatus === 'rejected') setReviseModalOpen(false) }, [selectedRunReviewStatus])
  const selectedStageOutputContent = selectedStageField
    ? formatStructuredContent(selectedRunConfigJson[selectedStageField.key] ?? selectedRun?.[selectedStageField.key])
    : ''
  const checkpointStageWaitingReview = Boolean(
    selectedRun?.checkpointEnabled &&
      String(selectedRun?.status ?? '').toLowerCase() === 'waiting_review' &&
      selectedRun?.stageStatus === 'waiting_review' &&
      selectedRunReviewStatus === 'pending' &&
      selectedRun?.importStatus !== 'imported' &&
      selectedStageField,
  )
  const showStageReviewInRunResultModal = Boolean(
    runResultModal?.mode === 'review' &&
      runResultModal.key === selectedStageField?.key && checkpointStageWaitingReview,
  )
  const finalResultEditable = Boolean(
    selectedRun?.runId &&
      runResultModal?.key === 'resultYaml' &&
      ['success', 'waiting_review'].includes(selectedRunStatus) &&
      requirementAnalysisFinalStages.includes(selectedStage ?? '') &&
      selectedRunReviewStatus === 'pending' &&
      selectedRun?.importStatus !== 'imported',
  )
  const finalResultApproved = Boolean(
    selectedRun?.runId &&
      runResultModal?.key === 'resultYaml' &&
      selectedRunStatus === 'success' &&
      requirementAnalysisFinalStages.includes(selectedStage ?? '') &&
      selectedRunReviewStatus === 'approved',
  )
  const editableRunResultModal = showStageReviewInRunResultModal || finalResultEditable || finalResultApproved
  const editableRunResultStage = finalResultEditable || finalResultApproved ? 'feature_understanding' : selectedStage
  const editableRunResultContent = finalResultEditable || finalResultApproved
    ? formatStructuredContent(selectedRun?.resultYaml)
    : selectedStageOutputContent

  const selectedRunResultSections = useMemo(() => {
    if (!selectedRun) return []

    return runResultSectionDefinitions
      .map((section) => {
        const directValue = selectedRun[section.key]
        const configValue =
          section.key === 'firstStepOutput'
            ? selectedRunConfigJson[section.key]
            : undefined
        return { ...section, value: formatStructuredContent(directValue || configValue) }
      })
      .filter((item) => item.value)
  }, [selectedRun, selectedRunConfigJson])
  const selectedRunResultSectionMap = useMemo(
    () => new Map(selectedRunResultSections.map((section) => [section.key, section.value])),
    [selectedRunResultSections],
  )
  const runResultModalContent = runResultModal ? selectedRunResultSectionMap.get(runResultModal.key) : undefined
  const runHistoryRefreshing = runsQuery.isFetching || selectedRunQuery.isFetching
  const runnableTask = isRunnableApiCaseGenerateTaskRun(latestRunRecord?.status)
  const selectedRunTaskType = activeSelectedRun?.snapshotJson?.taskType ?? task?.taskType
  const canImportSelectedRun =
    Boolean(activeSelectedRun?.runId) &&
    selectedRunTaskType === 'requirement_analysis' &&
    String(activeSelectedRun?.status ?? '').toLowerCase() === 'success' &&
    String(activeSelectedRun?.reviewStatus ?? '').toLowerCase() === 'approved' &&
    activeSelectedRun?.importStatus !== 'imported'
  const canImportRunResultModal = canImportSelectedRun && runResultModal?.key === 'resultYaml'

  const sprintName = task
    ? sprintNameMap.get(task.sprintId ?? '') ?? task.sprintId ?? '-'
    : '-'
  const requirementName = boundRequirement?.name ?? task?.requirementId ?? '-'
  const taskSourceContent = task?.sourceContent?.trim() ?? ''
  const displaySourceContent = taskSourceContent
  const canPreviewBoundRequirement = Boolean(boundRequirement && hasRequirementDocument(boundRequirement))
  /** 来源内容视图是否由绑定的需求文档兜底渲染；是的话由预览组件自己出标题栏，页面不再叠一条。 */
  const showSourceDocument = !displaySourceContent && canPreviewBoundRequirement && Boolean(boundRequirement)

  const sourceSummary = useMemo(() => {
    if (!task) return '暂无来源内容'
    const sizeLabel = taskSourceContent ? `${taskSourceContent.length} 字符` : '0 字符'
    const sourceTypeLabel = task.sourceType || 'text'
    const sourceState = canPreviewBoundRequirement ? ' · 已绑定需求文档' : boundRequirement ? ' · 原文件未上传，请重新上传' : ''
    return `${sourceTypeLabel} · ${sizeLabel}${sourceState}`
  }, [boundRequirement, canPreviewBoundRequirement, task, taskSourceContent])

  const instructionSummary = useMemo(() => {
    const instruction = normalizeInstruction(task?.instruction)
    if (!instruction) return '未填写 · 仅作用于下一次运行'
    return instruction.length > 36 ? `${instruction.slice(0, 36)}…` : instruction
  }, [task])

  const runStats = useMemo(() => {
    const counts = runsQuery.data?.statusCounts
    const countOf = (statuses: string[]) => counts
      ? statuses.reduce((total, status) => total + (counts[status] ?? 0), 0)
      : runRecords.filter((record) => statuses.includes(String(record.status ?? '').toLowerCase())).length
    const waitingCount = runsQuery.data?.reviewPendingCount ?? runRecords.filter(record =>
      record.reviewStatus === 'pending' && record.importStatus !== 'imported' && ['waiting_review', 'success'].includes(record.status ?? ''),
    ).length
    return { successCount: countOf(['success']), failedCount: countOf(['failed', 'error']), waitingCount }
  }, [runRecords, runsQuery.data?.reviewPendingCount, runsQuery.data?.statusCounts])

  const runHistorySummary = useMemo(() => {
    if (!runTotal) return '暂无运行记录'
    const statusMeta = getApiCaseGenerateTaskRunStatusMeta(latestRunRecord?.status)
    const suffix = runStats.waitingCount > 0 ? ` · ${runStats.waitingCount} 条待审核` : ''
    return `${runTotal} 条运行 · 最近：${statusMeta.label}${suffix}`
  }, [latestRunRecord?.status, runTotal, runStats.waitingCount])

  useEffect(() => {
    if (!task) return
    const requirement = task.requirementId ? requirementMap.get(task.requirementId) : undefined
    const sprintId = task.sprintId || requirement?.sprintIdForCreate
    setDrawerSprintId(sprintId)
    form.setFieldsValue({
      name: task.name,
      sprintId,
      requirementId: task.requirementId,
      instruction: task.instruction,
    })
  }, [form, requirementMap, task])

  useEffect(() => {
    setActiveSection('runHistory')
    setSelectedRunRecordId(null)
    setRunResultModal(null)
  }, [taskId])

  // 补充指令的内联编辑草稿跟着任务数据走；保存成功后任务数据更新，草稿与脏标记一起复位。
  useEffect(() => {
    setInstructionDraft(task?.instruction ?? '')
    setInstructionDirty(false)
  }, [task?.instruction, task?.taskId])

  useEffect(() => {
    if (!runsQuery.data || runsQuery.isFetching) return
    if (runRecords.length === 0) {
      setSelectedRunRecordId(null)
      return
    }
    setSelectedRunRecordId((current) =>
      current && runRecords.some((record) => record.runId === current) ? current : (runRecords[0].runId ?? null),
    )
  }, [runRecords, runsQuery.data, runsQuery.isFetching])

  useEffect(() => {
    // Opening a row's artifact also selects that run in the same render.
    setRunResultModal(current => current?.runId === selectedRunId ? current : null)
    setReviseModalOpen(false)
    setRevisionInstruction('')
    setRevisionTemplate('')
    setRevisionDraftKey('')
  }, [selectedRunId])

  useEffect(() => {
    const nextSourceKey = `${selectedRun?.runId ?? ''}:${editableRunResultStage ?? ''}:${runResultModal?.key ?? ''}`

    if (stageOutputSourceKey !== nextSourceKey) {
      setStageOutputSourceKey(nextSourceKey)
      setStageOutputDraft(editableRunResultContent)
      setStageOutputDirty(false)
      setStageReviewAction(null)
      return
    }

    if (!stageOutputDirty) {
      setStageOutputDraft(editableRunResultContent)
    }
  }, [
    editableRunResultContent,
    editableRunResultStage,
    runResultModal?.key,
    selectedRun?.runId,
    stageOutputDirty,
    stageOutputSourceKey,
  ])

  const updateTaskMutation = useMutation({
    mutationFn: (values: RequirementAnalysisTaskFormValues) =>
      api.updateRequirementAnalysisTask(taskId, {
        name: values.name,
        requirementId: values.requirementId,
        instruction: normalizeInstruction(values.instruction),
      }),
    onSuccess: (updatedTask) => {
      message.success('需求分析任务已更新')
      setDrawerOpen(false)
      queryClient.setQueryData(['requirementAnalysisTask', taskId], updatedTask)
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTasks', updatedTask.projectId] })
    },
  })

  const runTaskMutation = useStartTaskRun({
    kind: 'analysis',
    taskId,
    projectId: task?.projectId,
    startRun: (values: RequirementAnalysisRunFormValues) =>
      api.runRequirementAnalysisTask(taskId, {
        connectionId: values.connectionId,
        instruction: normalizeInstruction(values.instruction),
        triggerType: 'manual',
        checkpointEnabled: Boolean(values.checkpointEnabled),
        configJson: '{}',
      }),
    onStarted: (run) => {
      setRunPage(1)
      setRunModalOpen(false)
      setActiveSection('runHistory')
      setSelectedRunRecordId(run.runId ?? null)
    },
  })

  const importRunMutation = useMutation({
    mutationFn: (runId: string) => api.importRequirementAnalysisRunToRequirement(runId),
    onSuccess: (updatedRequirement, runId) => {
      const updatedRequirementId = normalizeRequirementId(updatedRequirement)
      message.success('已导入到需求')
      setRunResultModal(null)
      queryClient.setQueryData(
        ['requirement', 'requirementAnalysisTaskDetail', updatedRequirementId],
        updatedRequirement,
      )
      queryClient.setQueryData(['requirement', updatedRequirementId], updatedRequirement)
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisRun', runId] })
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTaskRuns', taskId] })
      queryClient.invalidateQueries({ queryKey: ['requirementsPool', 'requirementAnalysisTaskDetail', task?.projectId] })
      queryClient.invalidateQueries({ queryKey: ['requirementsPool', task?.projectId] })
    },
  })

  const saveStageOutputMutation = useMutation({
    mutationFn: (payload: { runId: string; stage: string; configJson: Record<string, unknown>; resultYaml?: string; silent?: boolean }) =>
      api.updateRequirementAnalysisRunStageOutput(payload.runId, {
        stage: payload.stage,
        configJson: payload.configJson,
        resultYaml: payload.resultYaml,
      }),
    onSuccess: (updatedRun, payload) => {
      if (!payload.silent) {
        message.success('阶段产物已保存')
      }
      setStageOutputDirty(false)
      queryClient.setQueryData(['requirementAnalysisRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const reviewStageMutation = useMutation({
    mutationFn: async (payload: {
      runId: string
      body: { stage: string; action: 'approve' | 'reject'; configJson: Record<string, unknown> }
    }) => api.reviewRequirementAnalysisRunStage(payload.runId, {
      ...payload.body,
      // 最终结果只是确认审核，不会继续派发下一阶段，因此不需要选择模型。
      llmConnectionId: requirementAnalysisFinalStages.includes(payload.body.stage) || payload.body.action === 'reject'
        ? undefined
        : payload.body.action === 'approve' ? await personalLlm.choose() : undefined,
    }),
    onSuccess: (updatedRun, payload) => {
      message.success(payload.body.action === 'reject' ? '最终结果审核不通过' : requirementAnalysisFinalStages.includes(payload.body.stage) ? '最终结果审核已通过' : '阶段审核已通过，继续执行')
      setStageReviewAction(null)
      setSelectedRunRecordId(updatedRun.runId ?? payload.runId)
      queryClient.setQueryData(['requirementAnalysisRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
      setStageReviewAction(null)
    },
  })

  const retryStageMutation = useMutation({
    mutationFn: async (payload: { runId: string; stage: string }) =>
      api.retryRequirementAnalysisRunStage(payload.runId, { stage: payload.stage, llmConnectionId: await personalLlm.choose() }),
    onSuccess: (updatedRun, payload) => {
      message.success('已提交阶段重试，等待重新执行')
      setSelectedRunRecordId(updatedRun.runId ?? payload.runId)
      queryClient.setQueryData(['requirementAnalysisRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const reviseStageMutation = useMutation({
    mutationFn: async (payload: {
      runId: string
      body: { llmConnectionId: string; stage: string; revisionInstruction: string; configJson: Record<string, unknown>; resultYaml?: string }
    }) => api.reviseRequirementAnalysisRunStage(payload.runId, payload.body),
    onSuccess: (updatedRun, payload) => {
      message.success('已提交 AI 修改，等待当前阶段重新执行')
      setReviseModalOpen(false)
      setRevisionInstruction('')
      setRevisionTemplate('')
      setRevisionDraftKey('')
      setRunResultModal(null)
      setStageOutputDirty(false)
      setStageReviewAction(null)
      setSelectedRunRecordId(updatedRun.runId ?? payload.runId)
      queryClient.setQueryData(['requirementAnalysisRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
      setStageReviewAction(null)
    },
  })
  const stageActionPending =
    saveStageOutputMutation.isPending || reviewStageMutation.isPending || reviseStageMutation.isPending || retryStageMutation.isPending

  const deleteTaskMutation = useMutation({
    mutationFn: () => api.deleteRequirementAnalysisTask(taskId),
    onSuccess: () => {
      message.success('需求分析任务已删除')
      queryClient.removeQueries({ queryKey: ['requirementAnalysisTask', taskId], exact: true })
      if (task?.projectId) {
        queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTasks', task.projectId] })
      }
      navigate('/ai-testing?tab=analysis')
    },
  })

  const deleteRunMutation = useDeleteTaskRun({
    kind: 'analysis',
    taskId,
    selectedRunId: selectedRunRecordId,
    onSelectedRunDeleted: () => {
      setSelectedRunRecordId(null)
    },
  })

  function handleSaveInstruction() {
    if (!task) return
    updateTaskMutation.mutate({
      name: task.name,
      sprintId: task.sprintId,
      requirementId: task.requirementId ?? '',
      instruction: instructionDraft,
    })
  }

  function handleRunTask() {
    if (runsQuery.isLoading) {
      message.warning('运行记录加载中，请稍后再试')
      return
    }
    if (!runnableTask) {
      message.warning('任务执行中，暂时不能重复运行')
      return
    }
    setRunModalOpen(true)
  }

  function handleRefreshRuns() {
    void runsQuery.refetch()
    if (selectedRunId) {
      void selectedRunQuery.refetch()
    }
  }

  function buildStageConfigJson() {
    if (!selectedStageField) return selectedRunConfigJson
    let output: unknown = stageOutputDraft
    try { output = JSON.parse(stageOutputDraft) } catch { /* Backend rejects malformed drafts. */ }
    return {
      ...selectedRunConfigJson,
      [selectedStageField.key]: output,
    }
  }

  function buildStageOutputPayload() {
    const stage = editableRunResultStage
    if (!selectedRun?.runId || !stage) return null

    const configJson = buildStageConfigJson()
    if (stage === 'feature_understanding') {
      return {
        runId: selectedRun.runId,
        stage,
        configJson,
        resultYaml: stageOutputDraft,
      }
    }

    return {
      runId: selectedRun.runId,
      stage,
      configJson,
    }
  }

  function handleSaveStageOutput() {
    const payload = buildStageOutputPayload()
    if (!payload) return
    if (!stageOutputDraft.trim()) {
      message.warning('阶段产物不能为空')
      return
    }

    saveStageOutputMutation.mutate(payload)
  }

  async function handleApproveStageReview() {
    const finalReview = finalResultEditable && requirementAnalysisFinalStages.includes(selectedStage ?? '')
    if (!selectedRun?.runId || !selectedStage || (!checkpointStageWaitingReview && !finalReview)) return
    if (!stageOutputDraft.trim()) {
      message.warning('阶段产物不能为空')
      return
    }

    setStageReviewAction('approve')
    const configJson = buildStageConfigJson()
    try {
      await saveStageOutputMutation.mutateAsync({
        runId: selectedRun.runId,
        stage: selectedStage,
        configJson,
        ...(finalReview ? { resultYaml: stageOutputDraft } : {}),
        silent: true,
      })
      await reviewStageMutation.mutateAsync({
        runId: selectedRun.runId,
        body: {
          stage: selectedStage,
          action: 'approve',
          configJson,
        },
      })
    } catch {
      setStageReviewAction(null)
    }
  }

  async function handleRejectFinalReview() {
    if (!selectedRun?.runId || !finalResultEditable || !requirementAnalysisFinalStages.includes(selectedStage ?? '')) return
    setStageReviewAction('reject')
    try {
      await reviewStageMutation.mutateAsync({
        runId: selectedRun.runId,
        body: { stage: selectedStage!, action: 'reject', configJson: buildStageConfigJson() },
      })
    } catch {
      setStageReviewAction(null)
    }
  }

  function openReviseStageModal() {
    if (!selectedRun?.runId || !editableRunResultStage || !editableRunResultModal) return
    if (!stageOutputDraft.trim()) {
      message.warning('阶段产物不能为空')
      return
    }
    const key = `${selectedRun.runId}:${editableRunResultStage}`
    if (key !== revisionDraftKey) {
      try {
        const artifact = parseRequirementArtifact(stageOutputDraft) ?? stageOutputDraft
        const label = editableRunResultStage === 'extracting_text' ? '材料提取结果' : '需求理解记录'
        const template = buildRevisionTemplate(getRevisionQuestions(artifact), label, '答复')
        setRevisionTemplate(template)
        setRevisionInstruction(template)
        setRevisionDraftKey(key)
      } catch (error) {
        message.warning(getErrorMessage(error))
        return
      }
    }
    setReviseModalOpen(true)
  }

  function handleReviseStage(connectionId: string) {
    const payload = buildStageOutputPayload()
    if (!selectedRun?.runId || !payload) return
    const trimmedInstruction = revisionInstruction.trim()
    if (!trimmedInstruction) {
      message.warning('请输入 AI 修改要求')
      return
    }
    if (revisionTemplate && trimmedInstruction === revisionTemplate.trim()) {
      message.warning('请补充已确认的信息，或填写其他优化要求')
      return
    }
    if (!stageOutputDraft.trim()) {
      message.warning('阶段产物不能为空')
      return
    }

    setStageReviewAction('revise')
    reviseStageMutation.mutate({
      runId: selectedRun.runId,
      body: {
        stage: payload.stage,
        revisionInstruction: trimmedInstruction,
        llmConnectionId: connectionId,
        configJson: payload.configJson,
        resultYaml: payload.resultYaml,
      },
    })
  }

  function handleImportSelectedRun() {
    if (!activeSelectedRun?.runId || !canImportSelectedRun) return

    Modal.confirm({
      mask: { closable: false },
      title: '导入需求',
      content: '导入后会把本次分析结果写回需求，并覆盖当前需求理解结果。',
      okText: '导入需求',
      cancelText: '取消',
      onOk: () => importRunMutation.mutateAsync(activeSelectedRun.runId!),
    })
  }

  return (<ProjectAccessScope resourceError={taskQuery.error} projectId={task?.projectId ?? ''}>{personalLlm.dialog}{(
    <div className="workbench-page ai-testing-page tp-list-surface ai-task-detail-page tp-surface">
      <div className="workbench-tabs">
        {taskQuery.error ? <Alert showIcon type="error" title={getErrorMessage(taskQuery.error)} /> : null}
        {runsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(runsQuery.error)} /> : null}

        {!task && taskQuery.isLoading ? (
          <Spin />
        ) : task ? (
          <div className="ai-task-detail-layout">
            <TaskDetailToolbar
              back={(
                <Button icon={<ArrowLeftOutlined />} onClick={() => goBackOrFallback(navigate, '/ai-testing?tab=analysis')}>
                  返回需求分析
                </Button>
              )}
              fields={[
                { label: '任务名称', value: task.name || '未命名任务', kind: 'name', separator: 'line' },
                { label: '迭代', value: sprintName, kind: 'chip-accent' },
                { label: '需求', value: requirementName },
                { label: '来源类型', value: task.sourceType || 'text', kind: 'chip-muted' },
                { label: '更新时间', value: formatTime(pickUpdatedAt(task)), kind: 'time', separator: 'dot' },
              ]}
              actions={(
                <>
                  <ProjectActionButton action="execute"
                    className="action-btn-run"
                    operation="run"
                    disabled={runsQuery.isLoading || !runnableTask}
                    loading={runTaskMutation.isPending}
                    onClick={handleRunTask}
                  >
                    运行
                  </ProjectActionButton>
                  <ProjectActionButton action="write" className="action-btn-update" operation="edit" onClick={() => setDrawerOpen(true)}>
                    编辑
                  </ProjectActionButton>
                  <Popconfirm title="确认删除该任务？" onConfirm={() => deleteTaskMutation.mutate()}>
                    <ProjectActionButton action="write" danger className="action-btn-delete" operation="delete" loading={deleteTaskMutation.isPending}>
                      删除
                    </ProjectActionButton>
                  </Popconfirm>
                </>
              )}
            />

            <div className="ai-task-detail-split">
              <TaskDetailNavPanel tip="点击左侧条目在右侧查看内容，运行时记录自动刷新。">
                <div className="ai-task-detail-nav-label">输入</div>
                <TaskDetailNavItem
                  title="来源内容"
                  sub={sourceSummary}
                  icon={<FileTextOutlined />}
                  active={activeSection === 'sourceContent'}
                  onClick={() => setActiveSection('sourceContent')}
                />
                <TaskDetailNavItem
                  title="补充指令"
                  sub={instructionSummary}
                  icon={<CodeOutlined />}
                  active={activeSection === 'instruction'}
                  onClick={() => setActiveSection('instruction')}
                />
                <div className="ai-task-detail-nav-label">输出</div>
                <TaskDetailNavItem
                  title="运行记录"
                  sub={runHistorySummary}
                  icon={<HistoryOutlined />}
                  active={activeSection === 'runHistory'}
                  badge={runTotal}
                  onClick={() => setActiveSection('runHistory')}
                />
              </TaskDetailNavPanel>

              <section className="ai-task-detail-main-panel">
                {activeSection === 'runHistory' ? (
                  <>
                    <div className="ai-task-detail-main-head">
                      <span className="ai-task-detail-main-head-title">运行记录</span>
                      <span className="ai-task-detail-main-head-sub">Pipeline Executions</span>
                      <div className="ai-task-detail-main-head-extra">
                        <div className="ai-task-run-history-toolbar">
                          <span className="ai-task-run-history-auto-refresh">历史每 30 秒刷新</span>
                          <ActionButton
                            size="small"
                            operation="refresh"
                            loading={runHistoryRefreshing}
                            onClick={handleRefreshRuns}
                          >
                            刷新
                          </ActionButton>
                        </div>
                      </div>
                    </div>
                    <div className="ai-task-detail-main-body">
                      {runRecords.length > 0 ? (
                        <div className="ai-task-run-metrics">
                          <div className="ai-task-run-metric accent">
                            <span className="ai-task-run-metric-k">最近状态</span>
                            <span className="ai-task-run-metric-v">
                              {renderApiCaseGenerateTaskRunStatusTag(runsQuery.data?.latestRun?.status ?? runRecords[0].status)}
                            </span>
                          </div>
                          <div className="ai-task-run-metric">
                            <span className="ai-task-run-metric-k">待审核</span>
                            <span className="ai-task-run-metric-v">{runStats.waitingCount}<small> 条</small></span>
                          </div>
                          <div className="ai-task-run-metric success">
                            <span className="ai-task-run-metric-k">成功</span>
                            <span className="ai-task-run-metric-v">{runStats.successCount}<small> 条</small></span>
                          </div>
                          <div className="ai-task-run-metric warn">
                            <span className="ai-task-run-metric-k">失败</span>
                            <span className="ai-task-run-metric-v">{runStats.failedCount}<small> 条</small></span>
                          </div>
                        </div>
                      ) : null}
                      {runsQuery.isLoading ? (
                        <div className="ai-task-run-history-placeholder">
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="运行记录加载中..." />
                        </div>
                      ) : runRecords.length > 0 ? (
                        <RunHistoryTable<RequirementAnalysisTaskRun>
                        pagination={runPagination}
                          rows={runRecords}
                          getRunId={(record) => record.runId}
                          selectedRunId={selectedRunId}
                          resolveRow={resolveRunRecord}
                          onSelect={(runId) => setSelectedRunRecordId(runId ?? null)}
                          renderStatus={(row) => {
                            const data = resolveRunRecord(row)
                            const recordStageMeta = getRequirementAnalysisStageMeta(data.currentStage)
                            return (
                              <RunPipelineStatus
                                run={data}
                                stages={['generate', 'review']}
                                stageTag={data.currentStage
                                  ? <Tag color={recordStageMeta.color}>{recordStageMeta.label}</Tag>
                                  : null}
                              />
                            )
                          }}
                          renderArtifacts={(row) => {
                            const data = resolveRunRecord(row)
                            const recordStatus = String(data.status ?? '').toLowerCase()
                            const reviewStatus = String(data.reviewStatus ?? '').toLowerCase()
                            const stageKeys = ['extracting_text', 'feature_understanding', 'completed']
                            const reachedStageIndex = stageKeys.indexOf(data.currentStage ?? '')
                            return (
                              <RunArtifacts
                                artifacts={runResultSectionDefinitions
                                  .filter((section) => section.key !== 'errorMessage')
                                  .filter((section) => !(section.key === 'resultYaml' && reviewStatus === 'approved'))
                                  .map((section, index) => ({
                                    key: section.key,
                                    label: section.label,
                                    available: recordStatus === 'success' || index <= reachedStageIndex,
                                  }))}
                                onOpen={(key) => {
                                  const section = runResultSectionDefinitions.find((item) => item.key === key)
                                  if (!section) return
                                  setSelectedRunRecordId(row.runId ?? null)
                                  setRunResultModal({ runId: row.runId, key: section.key, label: section.label, mode: 'view' })
                                }}
                              />
                            )
                          }}
                          renderActions={(row) => {
                            const data = resolveRunRecord(row)
                            const recordStatus = String(data.status ?? '').toLowerCase()
                            const recordFailed = ['failed', 'error'].includes(recordStatus)
                            const recordReviewStatus = String(data.reviewStatus ?? '').toLowerCase()
                            const recordHasErrorMessage = Boolean(data.errorMessage?.trim())
                            const reviewField = getRequirementAnalysisStageField(data.currentStage)
                            const showStageReview = Boolean(
                              reviewField && data.checkpointEnabled && recordStatus === 'waiting_review' && data.stageStatus === 'waiting_review' && recordReviewStatus === 'pending' && data.importStatus !== 'imported',
                            )
                            const showFinalReview = Boolean(
                              data.checkpointEnabled &&
                                ['success', 'waiting_review'].includes(recordStatus) &&
                                requirementAnalysisFinalStages.includes(data.currentStage ?? '') &&
                                recordReviewStatus === 'pending' &&
                                data.importStatus !== 'imported',
                            )
                            const canImportRecord = Boolean(
                              data.reviewStatus?.toLowerCase() === 'approved' &&
                                data.importStatus !== 'imported' &&
                                ['success', 'waiting_review'].includes(recordStatus),
                            )
                            const canRetry = recordFailed && row.runId &&
                              ['extracting_text', 'feature_understanding'].includes(data.currentStage ?? '') &&
                              ['failed', 'retrying'].includes(data.stageStatus ?? '') &&
                              recordReviewStatus === 'pending' && data.importStatus !== 'imported'
                            return (
                              <RunRowActions
                                inline={
                                  <>
                                    {/* 当前状态至多三个操作，按界面规范全部直接展示。 */}
                                    {showStageReview && reviewField ? (
                                      <Button
                                        size="small"
                                        type="primary"
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          setSelectedRunRecordId(row.runId ?? null)
                                          setRunResultModal({ runId: row.runId, key: reviewField.key, label: `${reviewField.label}（审核）`, mode: 'review' })
                                        }}
                                      >
                                        审核
                                      </Button>
                                    ) : null}
                                    {showFinalReview ? (
                                      <Button
                                        size="small"
                                        type="primary"
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          setSelectedRunRecordId(row.runId ?? null)
                                          setRunResultModal({ runId: row.runId, key: 'resultYaml', label: '需求理解记录（审核）', mode: 'review' })
                                        }}
                                      >
                                        审核
                                      </Button>
                                    ) : null}
                                    {canImportRecord ? (
                                      <Button
                                        size="small"
                                        type="primary"
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          setSelectedRunRecordId(row.runId ?? null)
                                          setRunResultModal({ runId: row.runId, key: 'resultYaml', label: '需求理解记录', mode: 'view' })
                                        }}
                                      >
                                        查看结果并导入
                                      </Button>
                                    ) : null}
                                    {recordFailed && recordHasErrorMessage ? (
                                      <button
                                        type="button"
                                        className="ai-task-run-result-popover-btn"
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          setSelectedRunRecordId(row.runId ?? null)
                                          setRunResultModal({ runId: row.runId, key: 'errorMessage', label: '错误信息', mode: 'view' })
                                        }}
                                      >
                                        错误信息
                                      </button>
                                    ) : null}
                                    {canRetry && can('execute') ? (
                                      <Button
                                        size="small"
                                        aria-label="重试阶段"
                                        disabled={stageActionPending}
                                        loading={retryStageMutation.isPending}
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          if (row.runId && data.currentStage) {
                                            retryStageMutation.mutate({ runId: row.runId, stage: data.currentStage })
                                          }
                                        }}
                                      >
                                        重试阶段
                                      </Button>
                                    ) : null}
                                    {row.runId && can('write') ? (
                                      <ActionButton
                                        operation="delete"
                                        iconOnly
                                        size="small"
                                        aria-label="删除运行记录"
                                        disabled={!isRunDeletable(recordStatus) || deleteRunMutation.isPending}
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          const runId = row.runId
                                          if (runId) confirmDeleteRun(() => deleteRunMutation.mutate(runId))
                                        }}
                                      />
                                    ) : null}
                                  </>
                                }
                              />
                            )
                          }}
                        />
                      ) : (
                        <div className="ai-task-run-history-placeholder">
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运行记录" />
                        </div>
                      )}
                    </div>
                  </>
                ) : activeSection === 'sourceContent' ? (
                  <>
                    {showSourceDocument ? null : (
                      <div className="ai-task-detail-main-head">
                        <span className="ai-task-detail-main-head-title">来源内容</span>
                        <div className="ai-task-detail-main-head-extra">
                          <div className="ai-task-run-history-toolbar">
                            <span className="ai-task-run-history-field">{sourceSummary}</span>
                          </div>
                        </div>
                      </div>
                    )}
                    <div className="ai-task-detail-main-body">
                      {boundRequirementQuery.isLoading && !displaySourceContent ? (
                        <div className="ai-task-run-history-placeholder compact">
                          <Spin />
                          <span>需求内容加载中...</span>
                        </div>
                      ) : displaySourceContent ? (
                        <pre className="ai-task-code-block">{displaySourceContent}</pre>
                      ) : canPreviewBoundRequirement && boundRequirement ? (
                        <RequirementDocumentPreviewContent
                          embedded
                          requirementId={normalizeRequirementId(boundRequirement)}
                          requirementName={boundRequirement.name}
                          documentType={boundRequirement.documentType}
                          documentContent={boundRequirement.documentContent}
                          documentFilename={boundRequirement.documentFilename}
                          documentDownloadUrl={boundRequirement.documentDownloadUrl}
                        />
                      ) : (
                        <div className="ai-task-run-history-placeholder compact">
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前任务未返回来源内容，绑定需求也暂无可展示文档" />
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="ai-task-detail-main-head">
                      <span className="ai-task-detail-main-head-title">补充指令</span>
                    </div>
                    <div className="ai-task-detail-main-body">
                      <TaskDetailInstructionEditor
                        value={instructionDraft}
                        dirty={instructionDirty}
                        saving={updateTaskMutation.isPending}
                        onChange={(value) => {
                          setInstructionDraft(value)
                          setInstructionDirty(true)
                        }}
                        onSave={handleSaveInstruction}
                      />
                    </div>
                  </>
                )}
              </section>
            </div>
          </div>
        ) : (
          <Empty description="未找到需求分析任务" />
        )}
      </div>

      <RequirementAnalysisTaskDrawer
        title="编辑需求分析任务"
        open={drawerOpen}
        form={form}
        loading={updateTaskMutation.isPending}
        error={updateTaskMutation.error}
        sprintOptions={sprintOptions}
        requirementOptions={requirementOptions}
        onSprintChange={(value) => {
          setDrawerSprintId(value)
          form.setFieldValue('requirementId', undefined)
        }}
        onClose={() => setDrawerOpen(false)}
        onFinish={(values) => updateTaskMutation.mutate(values)}
      />

      <RequirementAnalysisRunModal
        open={runModalOpen}
        projectId={task?.projectId}
        loading={runTaskMutation.isPending}
        onClose={() => setRunModalOpen(false)}
        onConfirm={(values) => runTaskMutation.mutate(values)}
      />

      <Modal
        mask={{ closable: false }}
        title={
          <div className="ai-task-run-result-expanded-title">
            <span>{showStageReviewInRunResultModal ? '审核' : runResultModal?.label || '运行结果'}</span>
            <div className="ai-task-run-result-expanded-actions">
              {canImportRunResultModal && !finalResultEditable ? (
                <ProjectActionButton action="execute"
                  type="primary"
                  size="small"
                  loading={importRunMutation.isPending}
                  onClick={handleImportSelectedRun}
                >
                  导入需求
                </ProjectActionButton>
              ) : null}
            </div>
          </div>
        }
        open={Boolean(runResultModal)}
        onCancel={() => { if (!reviseStageMutation.isPending) { setRunResultModal(null); setReviseModalOpen(false) } }}
        footer={
          reviseModalOpen ? <div ref={setRevisionFooter} /> : editableRunResultModal
            ? [
                <Button key="close" onClick={() => { setRunResultModal(null); setReviseModalOpen(false) }}>
                  关闭
                </Button>,
                <ProjectActionButton action="write"
                  key="save"
                  onClick={handleSaveStageOutput}
                  loading={saveStageOutputMutation.isPending && !stageReviewAction}
                  disabled={reviewStageMutation.isPending || reviseStageMutation.isPending}
                >
                  保存修改
                </ProjectActionButton>,
                ...(finalResultEditable ? [
                  <Button
                    key="reject"
                    danger
                    onClick={handleRejectFinalReview}
                    loading={stageActionPending && stageReviewAction === 'reject'}
                    disabled={reviseModalOpen || (stageActionPending && stageReviewAction !== 'reject')}
                  >
                    审核不通过
                  </Button>,
                ] : []),
                <ProjectActionButton action="execute"
                  key="revise"
                  onClick={openReviseStageModal}
                  loading={reviseStageMutation.isPending && stageReviewAction === 'revise'}
                  disabled={stageActionPending && stageReviewAction !== 'revise'}
                >
                  继续优化
                </ProjectActionButton>,
                <ProjectActionButton action="execute"
                  key="approve"
                  type="primary"
                  onClick={finalResultEditable ? handleApproveStageReview : finalResultApproved ? handleImportSelectedRun : handleApproveStageReview}
                  loading={finalResultEditable ? stageActionPending && stageReviewAction === 'approve' : finalResultApproved ? importRunMutation.isPending : stageActionPending && stageReviewAction === 'approve'}
                  disabled={reviseModalOpen || (finalResultEditable ? stageActionPending && stageReviewAction !== 'approve' : finalResultApproved ? importRunMutation.isPending : stageActionPending && stageReviewAction !== 'approve')}
                >
                  {finalResultEditable ? '审核通过' : finalResultApproved ? '导入需求' : '审核通过并继续'}
                </ProjectActionButton>,
              ]
            : null
        }
        width={runResultModal?.key === 'errorMessage' ? "min(1180px, calc(100vw - 56px))" : "calc(100vw - 56px)"}
        className={`ai-task-run-result-modal api-task-run-result-modal${editableRunResultModal ? ' review' : ' requirement-analysis-text-modal'} functional-stage-review-modal requirement-analysis-result-modal`}
        centered
        destroyOnHidden
      >
        <div className={`revision-workspace${reviseModalOpen ? " is-revising" : ""}`}><div className="revision-source">
        <div className={`ai-task-run-result-modal-content api-task-run-result-modal-content${editableRunResultModal ? ' review' : ''}`}>
          {selectedRunQuery.isLoading ? (
            <div className="ai-task-run-result-popover-loading">
              <Spin />
            </div>
          ) : editableRunResultModal ? (
            <div className="ai-task-stage-review-popover">
              <div className="ai-task-run-result-popover-header">
                <span>{runResultModal?.key === 'resultYaml' ? '最终需求理解记录' : '材料提取结果'}</span>
                <div className="ai-task-stage-review-mini-tags">
                  <Tag color={selectedStageMeta.color}>{selectedStageMeta.label}</Tag>
                  <Tag color={selectedStageStatusMeta.color}>{selectedStageStatusMeta.label}</Tag>
                </div>
              </div>
              <div className="ai-task-stage-review-note compact">
                <strong>{runResultModal?.key === 'resultYaml' ? finalResultApproved ? '已审核/可编辑' : '最终结果/可编辑' : '待审核/可编辑'}</strong>
                <span>{runResultModal?.key === 'resultYaml' ? '修改后需重新审核，审核通过后再导入需求。' : '保存后写回材料提取结果，审核通过后进入需求理解阶段。'}</span>
              </div>
              <Tabs className="requirement-analysis-artifact-tabs" defaultActiveKey="business" items={[
                { key: 'business', label: '业务内容', children: <div className="requirement-analysis-artifact-scroll is-material-comparison" role="region" aria-label="业务内容" tabIndex={0}>{runResultModal?.key === 'firstStepOutput' ? <RequirementMaterialComparison content={stageOutputDraft} /> : <RequirementUnderstandingComparison content={stageOutputDraft} extractionContent={selectedRunConfigJson.firstStepOutput} />}</div> },
                { key: 'json', label: '原始 JSON', children: <TextCodeEditor language="json" ariaLabel="阶段产物 JSON" value={stageOutputDraft} minHeight={360} onChange={value => { setStageOutputDraft(value); setStageOutputDirty(true) }} /> },
              ]} />
            </div>
          ) : runResultModalContent ? (
            runResultModal?.key !== 'errorMessage'
              ? <Tabs className="requirement-analysis-artifact-tabs" items={[
                { key: 'business', label: '业务内容', children: <div className="requirement-analysis-artifact-scroll is-material-comparison" role="region" aria-label="业务内容" tabIndex={0}>{runResultModal?.key === 'firstStepOutput' ? <RequirementMaterialComparison content={runResultModalContent} /> : <RequirementUnderstandingComparison content={runResultModalContent} extractionContent={selectedRunConfigJson.firstStepOutput} />}</div> },
                { key: 'json', label: '原始 JSON', children: <TextCodeEditor language="json" ariaLabel="阶段产物 JSON" readOnly value={runResultModalContent} /> },
              ]} />
              : <pre className="ai-task-code-block">{runResultModalContent}</pre>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无内容" />
          )}
        </div>
        </div>{reviseModalOpen && <><RevisionDivider /><RevisionSidePanel footerContainer={revisionFooter} projectId={task?.projectId} value={revisionInstruction} onChange={setRevisionInstruction} loading={reviseStageMutation.isPending} onCancel={() => setReviseModalOpen(false)} onSubmit={handleReviseStage} /></>}</div>
      </Modal>

    </div>
  )}</ProjectAccessScope>)
}
