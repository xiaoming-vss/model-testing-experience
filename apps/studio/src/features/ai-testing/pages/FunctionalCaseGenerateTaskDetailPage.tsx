import { useDeleteTaskRun, useStartTaskRun } from '@/features/ai-testing/hooks/useTaskRunActions'
import { FunctionalCaseRelationsViewer } from '../components/FunctionalCaseRelationsViewer'
import type { CaseNamesViewMode } from '@/features/ai-testing/components/CaseNamesResultView'
import { CaseNameTreeView, CaseNamesResultView } from '@/features/ai-testing/components/CaseNamesResultView'
import { FunctionalCaseGenerateTaskDrawer, type FunctionalCaseGenerateTaskFormValues } from '@/features/ai-testing/components/FunctionalCaseGenerateTaskDrawer'
import { FunctionalImportConflictModal } from '@/features/ai-testing/components/FunctionalImportConflictModal'
import { GeneratedCasesReviewView } from '@/features/ai-testing/components/GeneratedCasesReviewView'
import { LlmConnectionSelectModal } from '@/features/ai-testing/components/LlmConnectionSelectModal'
import type { RequirementAnalysisViewMode } from '@/features/ai-testing/components/RequirementAnalysisView'
import { RequirementAnalysisDiagramView, RequirementAnalysisView } from '@/features/ai-testing/components/RequirementAnalysisView'
import { RevisionDivider, RevisionSidePanel } from '@/features/ai-testing/components/RevisionSidePanel'
import { RunHistoryTable, RunMigrationWarningIcon, RunRowActions } from '@/features/ai-testing/components/RunHistoryTable'
import { confirmDeleteRun, isRunDeletable } from '@/features/ai-testing/utils/runDeletion'
import { RunArtifacts, RunPipelineStatus } from '@/features/ai-testing/components/RunPipelineStatus'
import { usePersonalLlmChoice } from '@/features/ai-testing/hooks/usePersonalLlmChoice'
import '@/features/ai-testing/styles/functional-import-confirm.css'
import '@/shared/styles/surface-tokens.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-review.css'
import '@/features/ai-testing/styles/candidate-review.css'
import '@/features/ai-testing/styles/requirement-analysis.css'
import '@/features/ai-testing/styles/case-name-tree.css'
import '@/features/ai-testing/styles/run-result.css'
import '@/features/ai-testing/styles/task-detail-v2.css'
import type { FunctionalCaseGenerateTaskRun, FunctionalCaseGenerateTaskRunImportConflict } from '@/features/ai-testing/types'
import { getConfigStageFieldContent, getGeneratedCaseImportStats, getOutputRepairProgress, isJsonText } from '@/features/ai-testing/utils/functionalOutput'
import { buildRevisionTemplate, getRevisionQuestions } from '@/features/ai-testing/utils/functionalRevision'
import { getRunPipelineModel, type RunPipelineFilterKey } from '@/features/ai-testing/utils/runPipeline'
import { getApiCaseGenerateTaskRunStatusMeta, isRunnableApiCaseGenerateTaskRun, renderApiCaseGenerateTaskRunStatusTag, summarizeRunStatuses } from '@/features/ai-testing/utils/taskStatus'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { RequirementDocumentPreviewContent } from '@/features/requirements/components/RequirementDocumentPreviewModal'
import { TaskDetailInstructionEditor, TaskDetailNavItem, TaskDetailNavPanel, TaskDetailRunMetrics, TaskDetailToolbar } from '../components/TaskDetailShell'
import { hasRequirementDocument, hasRequirementEnhancedText } from '@/features/requirements/utils/requirementDocument'
import { api, listItems } from '@/services/api'
import { ApiError } from '@/shared/api/request'
import { ActionButton } from '@/shared/components/ActionButton'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { message } from '@/shared/utils/feedback'
import { formatStructuredContent } from '@/shared/utils/value'
import { formatTime, getErrorMessage, normalizeRequirementId, normalizeSprintId, pickUpdatedAt } from '@/utils/format'
import { ArrowLeftOutlined, CodeOutlined, FileTextOutlined, HistoryOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Checkbox, Empty, Form, Input, Modal, Popconfirm, Select, Spin, Tabs, Tag } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

const runResultSectionDefinitions = [
  { key: 'enhancedText', label: '增强文本' },
  { key: 'requirementAnalysis', label: '需求分析' },
  { key: 'caseNames', label: '测试点' },
  { key: 'caseRelations', label: '图谱分析' },
  { key: 'errorMessage', label: '错误信息' },
] as const

type RunResultSectionKey = (typeof runResultSectionDefinitions)[number]['key']

type RunResultModalState = {
  key: RunResultSectionKey
  label: string
} | null

const functionalStageMetaMap: Record<string, { label: string; color: string }> = {
  enhanced_text: { label: '增强文档输出', color: 'cyan' },
  requirement_analysis: { label: '测试需求/风险/测试点输出', color: 'blue' },
  case_names: { label: '测试用例名称/测试点输出', color: 'geekblue' },
  detailed_cases: { label: '详细测试用例输出', color: 'purple' },
  relation_analysis: { label: '图谱分析', color: 'volcano' },
  completed: { label: '已完成', color: 'success' },
}

const stageConfigFieldMap: Record<string, { key: string; label: string }> = {
  enhanced_text: { key: 'enhancedText', label: '增强文本 enhancedText' },
  requirement_analysis: { key: 'requirementAnalysis', label: '需求分析 requirementAnalysis' },
  case_names: { key: 'caseNames', label: '测试点 caseNames' },
}

function getRunOperationErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 403) {
    return error.message ? `无权限执行当前操作：${error.message}` : '无权限执行当前操作'
  }
  return getErrorMessage(error)
}

function normalizeReviewStatus(status?: string) {
  return status ?? 'unknown'
}

function getFunctionalStageMeta(stage?: string) {
  if (!stage) return { label: '未开始', color: 'default' }
  return functionalStageMetaMap[stage] ?? { label: stage, color: 'default' }
}

function getStageConfigField(stage?: string) {
  return stage ? stageConfigFieldMap[stage] : undefined
}

const runStageFilterOptions: Array<{ label: string; value: 'all' | RunPipelineFilterKey }> = [
  { label: '全部状态', value: 'all' },
  { label: '待审核', value: 'review_pending' },
  { label: '待导入', value: 'import_pending' },
  { label: '已导入', value: 'imported' },
  { label: '已拒绝', value: 'rejected' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'canceled' },
  { label: '执行中', value: 'running' },
]

const runArtifactDefinitions = [
  { key: 'requirementAnalysis', label: '需求分析' },
  { key: 'caseNames', label: '测试点' },
  { key: 'caseRelations', label: '图谱分析' },
] as const

function getRunRecordArtifacts(configJson: unknown) {
  return runArtifactDefinitions.map((definition) => ({
    ...definition,
    available: Boolean(getConfigStageFieldContent(configJson, definition.key)),
  }))
}

export function FunctionalCaseGenerateTaskDetailPage() {
  const { taskId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerSprintId, setDrawerSprintId] = useState<string | undefined>(undefined)
  const [llmSelectOpen, setLlmSelectOpen] = useState(false)
  const [expandedSection, setExpandedSection] = useState<'instruction' | 'document' | 'runHistory' | null>('runHistory')
  const [instructionDraft, setInstructionDraft] = useState('')
  const [instructionDirty, setInstructionDirty] = useState(false)
  const [selectedRunRecordId, setSelectedRunRecordId] = useState<string | null>(null)
  const [runStageFilter, setRunStageFilter] = useState<'all' | RunPipelineFilterKey>('all')
  const [runResultModal, setRunResultModal] = useState<RunResultModalState>(null)
  const [graphRunId, setGraphRunId] = useState<string | null>(null)
  const [resultModalRunId, setResultModalRunId] = useState<string | null>(null)
  const [reviewSubmitAction, setReviewSubmitAction] = useState<'approve' | 'reject' | null>(null)
  const [reviewComment, setReviewComment] = useState('')
  const [candidateModalView, setCandidateModalView] = useState<'preview' | 'edit'>('preview')
  const [candidateYaml, setCandidateYaml] = useState('')
  const [revisionTarget, setRevisionTarget] = useState<'stage' | 'final' | null>(null)
  const [revisionFooter, setRevisionFooter] = useState<HTMLDivElement | null>(null)
  const [revisionInstruction, setRevisionInstruction] = useState('')
  const [revisionDraftKey, setRevisionDraftKey] = useState('')
  const [revisionTemplate, setRevisionTemplate] = useState('')
  const [importConfirmRunId, setImportConfirmRunId] = useState<string | null>(null)
  const [importAcknowledged, setImportAcknowledged] = useState(false)
  const [importConflict, setImportConflict] = useState<{
    runId: string
    conflicts: FunctionalCaseGenerateTaskRunImportConflict[]
  } | null>(null)
  const [checkpointEnabled, setCheckpointEnabled] = useState(false)
  const [stageOutputDraft, setStageOutputDraft] = useState('')
  const [stageOutputDirty, setStageOutputDirty] = useState(false)
  const [stageOutputSourceKey, setStageOutputSourceKey] = useState('')
  const [stageReviewComment, setStageReviewComment] = useState('')
  const [stageReviewAction, setStageReviewAction] = useState<'approve' | 'reject' | null>(null)
  const [runResultCaseNamesView, setRunResultCaseNamesView] = useState<CaseNamesViewMode>('tree')
  const [stageRequirementAnalysisView, setStageRequirementAnalysisView] = useState<RequirementAnalysisViewMode>('diagram')
  const [form] = Form.useForm<FunctionalCaseGenerateTaskFormValues>()

  const taskQuery = useQuery({
    queryKey: ['functionalCaseGenerateTask', taskId],
    queryFn: () => api.getFunctionalCaseGenerateTask(taskId),
    enabled: Boolean(taskId),
  })

  const task = taskQuery.data
  const { can } = useProjectAccess(task?.projectId ?? '')
  const personalLlm = usePersonalLlmChoice(task?.projectId)
  const taskRequirementQuery = useQuery({
    queryKey: ['requirement', task?.requirementId],
    queryFn: () => api.getRequirement(task!.requirementId!),
    enabled: Boolean(task?.requirementId),
  })
  const runsQuery = useQuery({
    queryKey: ['functionalCaseGenerateTaskRuns', taskId],
    queryFn: () => api.getFunctionalCaseGenerateTaskRuns(taskId),
    enabled: Boolean(taskId),
    refetchInterval: expandedSection === 'runHistory' ? 5000 : false,
  })
  const sprintsQuery = useQuery({
    queryKey: ['sprints', 'functionalAiTestingDetail', task?.projectId],
    queryFn: async () => {
      const projectId = task?.projectId
      if (!projectId) return []
      return api.getSprints(projectId)
    },
    enabled: Boolean(task?.projectId),
  })
  const sprintOptions = useMemo(
    () => listItems(sprintsQuery.data).map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) })),
    [sprintsQuery.data],
  )
  const requirementsQuery = useQuery({
    queryKey: ['requirements', 'functionalAiTestingDetail', drawerSprintId],
    queryFn: () => api.getRequirements(drawerSprintId!),
    enabled: Boolean(drawerSprintId),
  })
  const requirementOptions = useMemo(
    () =>
      listItems(requirementsQuery.data).map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    [requirementsQuery.data],
  )
  const sprintNameMap = useMemo(
    () => new Map(listItems(sprintsQuery.data).map((sprint) => [normalizeSprintId(sprint), sprint.name])),
    [sprintsQuery.data],
  )
  const requirementNameMap = useMemo(
    () => new Map(listItems(requirementsQuery.data).map((requirement) => [normalizeRequirementId(requirement), requirement.name])),
    [requirementsQuery.data],
  )

  const runRecords = useMemo(
    () =>
      [...listItems(runsQuery.data)].sort((left, right) => {
        const leftTime = new Date(left.createdAt || left.startedAt || left.updatedAt || '').getTime()
        const rightTime = new Date(right.createdAt || right.startedAt || right.updatedAt || '').getTime()
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
      }),
    [runsQuery.data],
  )
  const latestRunRecord = runRecords[0]
  const filteredRunRecords = useMemo(
    () =>
      runStageFilter === 'all'
        ? runRecords
        : runRecords.filter((record) => getRunPipelineModel(record).filterKey === runStageFilter),
    [runRecords, runStageFilter],
  )
  const selectedRunId = selectedRunRecordId ?? runRecords[0]?.runId ?? ''
  const selectedRunQuery = useQuery({
    queryKey: ['functionalCaseGenerateTaskRun', selectedRunId],
    queryFn: () => api.getFunctionalCaseGenerateTaskRun(selectedRunId),
    enabled: Boolean(selectedRunId),
    refetchInterval: expandedSection === 'runHistory' && selectedRunId ? 5000 : false,
  })
  const selectedRun = selectedRunQuery.data
  const importDetailsReady = Boolean(importConfirmRunId && selectedRun?.runId === importConfirmRunId && selectedRunQuery.isSuccess)
  const selectedStage = selectedRun?.currentStage
  const selectedStageField = getStageConfigField(selectedStage)
  const selectedStageOutputContent = useMemo(
    () =>
      formatStructuredContent(selectedRun?.stageOutput) ||
      getConfigStageFieldContent(selectedRun?.configJson, selectedStageField?.key),
    [selectedRun?.configJson, selectedRun?.stageOutput, selectedStageField?.key],
  )
  const selectedRunResultSections = useMemo(
    () =>
      selectedRun
        ? runResultSectionDefinitions
          .map((section) => {
            const rawValue =
              section.key === 'enhancedText' ||
                section.key === 'requirementAnalysis' ||
                section.key === 'caseNames' ||
                section.key === 'caseRelations'
                ? getConfigStageFieldContent(selectedRun.configJson, section.key)
                : selectedRun[section.key as keyof FunctionalCaseGenerateTaskRun]
            return { ...section, value: formatStructuredContent(rawValue) }
          })
          .filter((item) => item.value)
        : [],
    [selectedRun],
  )

  useEffect(() => {
    if (!task) return
    setDrawerSprintId(task.sprintId)
    form.setFieldsValue({
      name: task.name,
      sprintId: task.sprintId,
      requirementId: task.requirementId,
      instruction: task.instruction,
    })
  }, [form, task])

  useEffect(() => {
    setExpandedSection('runHistory')
  }, [taskId])

  useEffect(() => {
    if (runRecords.length === 0) {
      setSelectedRunRecordId(null)
      return
    }
    setSelectedRunRecordId((current) =>
      current && runRecords.some((record) => record.runId === current) ? current : (runRecords[0].runId ?? null),
    )
  }, [runRecords])

  useEffect(() => {
    setRunResultModal(null)
  }, [selectedRunId])

  useEffect(() => {
    setGraphRunId(null)
  }, [taskId])

  useEffect(() => {
    if (runResultModal?.key !== 'caseNames') {
      setRunResultCaseNamesView('tree')
    }
    if (runResultModal?.key !== selectedStageField?.key) {
      setStageRequirementAnalysisView('diagram')
    }
  }, [runResultModal?.key, selectedStageField?.key])

  useEffect(() => {
    setInstructionDraft(task?.instruction ?? '')
    setInstructionDirty(false)
  }, [task?.instruction, task?.taskId])

  function handleSaveInstruction() {
    if (!task) return
    updateTaskMutation.mutate({
      name: task.name,
      sprintId: task.sprintId ?? '',
      requirementId: task.requirementId ?? '',
      instruction: instructionDraft,
    })
  }

  const updateTaskMutation = useMutation({
    mutationFn: (values: FunctionalCaseGenerateTaskFormValues) => api.updateFunctionalCaseGenerateTask(taskId, values),
    onSuccess: (updatedTask) => {
      message.success('任务已更新')
      setDrawerOpen(false)
      queryClient.setQueryData(['functionalCaseGenerateTask', taskId], updatedTask)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTasks', updatedTask.projectId] })
    },
  })

  const runTaskMutation = useStartTaskRun({
    kind: 'functional',
    taskId,
    projectId: task?.projectId,
    startRun: ({ connectionId, checkpointEnabled }: { connectionId: string; checkpointEnabled?: boolean }) =>
      api.runFunctionalCaseGenerateTask(taskId, { connectionId, checkpointEnabled }),
    onStarted: (run) => {
      setLlmSelectOpen(false)
      setCheckpointEnabled(false)
      setExpandedSection('runHistory')
      setSelectedRunRecordId(run.runId ?? null)
    },
  })

  const reviewRunMutation = useMutation({
    mutationFn: (payload: {
      runId: string
      body: { action: 'approve'; reviewComment?: string } | { action: 'reject'; reviewComment?: string }
    }) => api.reviewFunctionalCaseGenerateTaskRun(payload.runId, payload.body),
    onSuccess: (updatedRun, payload) => {
      message.success(payload.body.action === 'approve' ? '候选结果审核通过' : '候选结果审核已拒绝')
      setResultModalRunId(null)
      setReviewSubmitAction(null)
      setSelectedRunRecordId(updatedRun.runId ?? payload.runId)
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getRunOperationErrorMessage(error))
      if (resultModalRunId) {
        queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', resultModalRunId] })
      }
    },
  })

  const updateRunResultMutation = useMutation({
    mutationFn: (payload: { runId: string; resultYaml: string }) =>
      api.updateFunctionalCaseGenerateTaskRunResult(payload.runId, { resultYaml: payload.resultYaml }),
    onSuccess: (updatedRun, payload) => {
      message.success('候选结果已保存')
      setCandidateYaml(formatStructuredContent(updatedRun.resultYaml ?? payload.resultYaml))
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error, payload) => {
      message.error(getRunOperationErrorMessage(error))
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
    },
  })

  const importRunMutation = useMutation({
    mutationFn: (payload: { runId: string; confirmOverwrite: boolean }) =>
      api.importFunctionalCaseGenerateTaskRun(payload.runId, {
        confirmOverwrite: payload.confirmOverwrite,
      }),
    onSuccess: (result, payload) => {
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], result.run)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })

      if (result.requiresConfirmation) {
        setImportConflict({ runId: payload.runId, conflicts: result.conflicts })
        return
      }

      setImportConflict(null)
      message.success('正式功能用例导入成功')
      const targetRequirementId = task?.requirementId ?? result.run.requirementId
      if (targetRequirementId) {
        queryClient.invalidateQueries({ queryKey: ['functionTestSuites', targetRequirementId] })
      }
      queryClient.invalidateQueries({ queryKey: ['functionTestSuites'] })
      queryClient.invalidateQueries({ queryKey: ['functionTestCases'] })
    },
    onError: (error, payload) => {
      message.error(getRunOperationErrorMessage(error))
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
  })

  const generateRelationMutation = useMutation({
    mutationFn: (payload: { runId: string }) =>
      api.generateFunctionalCaseRelationAnalysis(payload.runId),
    onSuccess: (updatedRun) => {
      message.success('图谱生成任务已提交，完成后可在运行记录查看')
      setSelectedRunRecordId(updatedRun.runId ?? null)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', updatedRun.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getRunOperationErrorMessage(error))
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
  })

  const saveStageOutputMutation = useMutation({
    mutationFn: (payload: { runId: string; stage: string; configJson: string; silent?: boolean }) => {
      const field = getStageConfigField(payload.stage)
      if (field?.key !== 'requirementAnalysis' && field?.key !== 'caseNames') {
        return api.updateFunctionalCaseGenerateTaskRunStageOutput(payload.runId, {
          stage: payload.stage,
          configJson: payload.configJson,
        })
      }
      let parsed: unknown
      try {
        parsed = JSON.parse(payload.configJson)
      } catch {
        throw new Error('阶段产物必须是有效的 JSON 对象')
      }
      if (!field || !parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('阶段产物必须是有效的 JSON 对象')
      }
      const record = parsed as Record<string, unknown>
      return api.updateFunctionalCaseGenerateTaskRunStageOutput(payload.runId, {
        stage: payload.stage,
        configJson: JSON.stringify({ [field.key]: record[field.key] ?? record }),
      })
    },
    onSuccess: (updatedRun, payload) => {
      if (!payload.silent) {
        message.success('阶段产物已保存')
      }
      setStageOutputDirty(false)
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const reviewStageMutation = useMutation({
    mutationFn: async (payload: {
      runId: string
      body: { stage: string; action: 'approve'; comment?: string } | { stage: string; action: 'reject'; comment?: string }
    }) => api.reviewFunctionalCaseGenerateTaskRunStage(payload.runId, { ...payload.body, llmConnectionId: payload.body.action === 'approve' ? await personalLlm.choose() : undefined }),
    onSuccess: (updatedRun, payload) => {
      message.success(payload.body.action === 'approve' ? '阶段审核已通过，继续生成' : '已拒绝并停止继续生成')
      setStageReviewAction(null)
      setStageReviewComment('')
      setSelectedRunRecordId(updatedRun.runId ?? payload.runId)
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
      setStageReviewAction(null)
    },
  })

  const reviseStageMutation = useMutation({
    mutationFn: async (payload: { runId: string; body: { llmConnectionId: string; stage: string; revisionInstruction: string; configJson?: Record<string, unknown>; resultYaml?: string } }) =>
      api.reviseFunctionalCaseGenerateTaskRunStage(payload.runId, payload.body),
    onSuccess: (updatedRun, payload) => {
      message.success('已提交优化，等待重新生成')
      setRevisionTarget(null)
      setRevisionInstruction('')
      setRevisionDraftKey('')
      setRunResultModal(null)
      setResultModalRunId(null)
      setStageOutputDirty(false)
      setExpandedSection('runHistory')
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const retryStageMutation = useMutation({
    mutationFn: async (payload: { runId: string; stage: string }) =>
      api.retryFunctionalCaseGenerateTaskRunStage(payload.runId, { stage: payload.stage, llmConnectionId: await personalLlm.choose() }),
    onSuccess: (updatedRun, payload) => {
      message.success('已提交阶段重试，等待重新执行')
      setSelectedRunRecordId(updatedRun.runId ?? payload.runId)
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTask', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const deleteTaskMutation = useMutation({
    mutationFn: () => api.deleteFunctionalCaseGenerateTask(taskId),
    onSuccess: () => {
      message.success('任务已删除')
      queryClient.removeQueries({ queryKey: ['functionalCaseGenerateTask', taskId], exact: true })
      if (task?.projectId) {
        queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTasks', task.projectId] })
      }
      navigate('/ai-testing?tab=tasks')
    },
  })

  const deleteRunMutation = useDeleteTaskRun({
    kind: 'functional',
    taskId,
    selectedRunId: selectedRunRecordId,
    onSelectedRunDeleted: () => {
      setSelectedRunRecordId(null)
    },
  })

  const runnableTask = isRunnableApiCaseGenerateTaskRun(latestRunRecord?.status)
  const selectedRunResultSectionMap = useMemo(
    () => new Map(selectedRunResultSections.map((section) => [section.key, section.value])),
    [selectedRunResultSections],
  )
  const runResultModalContent = runResultModal ? selectedRunResultSectionMap.get(runResultModal.key) : undefined
  const selectedRunImportStats = useMemo(
    () => getGeneratedCaseImportStats(selectedRun?.resultYaml),
    [selectedRun?.resultYaml],
  )
  const importTargetRequirementName = task?.requirementId
    ? taskRequirementQuery.data?.name ?? requirementNameMap.get(task.requirementId) ?? task.requirementId
    : selectedRun?.requirementId
      ? requirementNameMap.get(selectedRun.requirementId) ?? selectedRun.requirementId
      : '-'
  const runHistoryRefreshing = runsQuery.isFetching || selectedRunQuery.isFetching
  const resultModalOpen = Boolean(resultModalRunId)
  const selectedRunReviewStatus = normalizeReviewStatus(selectedRun?.reviewStatus)
  const selectedRunStatus = String(selectedRun?.status ?? '')
  const selectedStageMeta = getFunctionalStageMeta(selectedStage)
  const stageOutputIsCaseNames = selectedStageField?.key === 'caseNames'
  const stageOutputIsRequirementAnalysis = selectedStageField?.key === 'requirementAnalysis'
  const selectedStageStatusMeta = getApiCaseGenerateTaskRunStatusMeta(selectedRun?.stageStatus)
  const canRetryStage = Boolean(
    ['failed', 'retrying'].includes(String(selectedRun?.stageStatus ?? '')) &&
    ['requirement_analysis', 'case_names', 'detailed_cases'].includes(String(selectedStage ?? '')) &&
    selectedRunReviewStatus === 'pending' &&
    selectedRun?.importStatus !== 'imported' &&
    (selectedRunStatus === 'failed' || selectedRunStatus === 'error'),
  )
  const checkpointStageWaitingReview = Boolean(
    selectedRun?.checkpointEnabled &&
    selectedRunStatus === 'waiting_review' &&
    selectedRun?.stageStatus === 'waiting_review' &&
    selectedStage,
  )
  const showStageReviewInRunResultModal = runResultModal?.key === selectedStageField?.key && checkpointStageWaitingReview
  const checkpointStageVisible = Boolean(
    selectedRun?.checkpointEnabled &&
    selectedStage &&
    selectedRunStatus !== 'success' &&
    selectedRunStatus !== 'failed' &&
    selectedRunStatus !== 'error' &&
    selectedRunStatus !== 'canceled',
  )
  const canReviseCheckpoint = showStageReviewInRunResultModal
    && (selectedStage === 'requirement_analysis' || selectedStage === 'case_names')
    && selectedRunReviewStatus === 'pending' && selectedRun?.importStatus !== 'imported'
  const stageActionPending = saveStageOutputMutation.isPending || reviewStageMutation.isPending || reviseStageMutation.isPending
  const reviewAvailable = Boolean(selectedRun) && selectedRunReviewStatus === 'pending' && selectedRunStatus === 'success'
  const canReviewSelectedRun = can('review') && reviewAvailable
  const canReviseFinal = canReviewSelectedRun && selectedRun?.importStatus !== 'imported'
    && (!selectedStage || selectedStage === 'detailed_cases' || selectedStage === 'completed')
  const canEditCandidate = canReviewSelectedRun
  const candidateDirty = candidateYaml !== formatStructuredContent(selectedRun?.resultYaml ?? '')

  useEffect(() => {
    if (!resultModalRunId) {
      setCandidateYaml('')
      setReviewComment('')
      return
    }
    setReviewComment(selectedRun?.reviewComment ?? '')
    setCandidateYaml(formatStructuredContent(selectedRun?.resultYaml ?? ''))
  }, [resultModalRunId, selectedRun?.reviewComment, selectedRun?.resultYaml])

  useEffect(() => {
    const nextSourceKey = `${selectedRun?.runId ?? ''}:${selectedRun?.currentStage ?? ''}`

    if (stageOutputSourceKey !== nextSourceKey) {
      setStageOutputSourceKey(nextSourceKey)
      setStageOutputDraft(selectedStageOutputContent)
      setStageOutputDirty(false)
      setStageRequirementAnalysisView('diagram')
      setStageReviewComment('')
      setStageReviewAction(null)
      return
    }

    if (!stageOutputDirty) {
      setStageOutputDraft(selectedStageOutputContent)
    }
  }, [
    selectedRun?.currentStage,
    selectedRun?.runId,
    selectedStageOutputContent,
    stageOutputDirty,
    stageOutputSourceKey,
  ])

  async function handleRunTask() {
    if (runsQuery.isLoading) {
      message.warning('运行记录加载中，请稍后再试')
      return
    }
    if (!runnableTask) {
      message.warning('任务执行中，暂时不能重复运行')
      return
    }

    let requirement = taskRequirementQuery.data
    if (!requirement && task?.requirementId) {
      try {
        requirement = await queryClient.fetchQuery({
          queryKey: ['requirement', task.requirementId],
          queryFn: () => api.getRequirement(task.requirementId!),
        })
      } catch (error) {
        message.error(getErrorMessage(error))
        return
      }
    }

    if (!hasRequirementEnhancedText(requirement)) {
      message.warning('请先完成需求分析并导入增强文本，再生成功能用例')
      return
    }

    setLlmSelectOpen(true)
  }

  function handleLlmSelectConfirm(connectionId: string) {
    runTaskMutation.mutate({ connectionId, checkpointEnabled })
  }

  function handleRefreshRuns() {
    void runsQuery.refetch()
    if (selectedRunId) {
      void selectedRunQuery.refetch()
    }
  }

  function openRevisionModal(target: 'stage' | 'final') {
    if (!selectedRun?.runId) return
    const stage = target === 'final' ? 'detailed_cases' : selectedStage
    const label = stage === 'detailed_cases' ? '详细测试用例' : stage === 'case_names' ? '测试点' : '需求分析'
    const key = `${selectedRun.runId}:${stage}`
    // Initialize once per run/stage; closing, retrying and polling must preserve the draft.
    if (key !== revisionDraftKey) {
      const questions = stage === 'requirement_analysis' ? getRevisionQuestions(stageOutputDraft) : []
      const template = buildRevisionTemplate(questions, label)
      setRevisionTemplate(template)
      setRevisionInstruction(template)
      setRevisionDraftKey(key)
    }
    if (target === 'final') setCandidateModalView('edit')
    setRevisionTarget(target)
  }

  function handleReviseStage(connectionId: string) {
    if (!selectedRun?.runId || reviseStageMutation.isPending) return
    if (!revisionInstruction.trim()) {
      message.warning('请输入优化指令')
      return
    }
    if (revisionTemplate && revisionInstruction.trim() === revisionTemplate.trim()) {
      message.warning('请补充已确认的信息，或填写其他优化要求')
      return
    }
    const final = revisionTarget === 'final'
    if (final ? !canReviseFinal : !canReviseCheckpoint) return
    const content = final ? candidateYaml : stageOutputDraft
    if (!content.trim()) {
      message.warning('当前产物不能为空')
      return
    }
    let configJson: Record<string, unknown> | undefined
    if (!final) {
      try {
        const parsed: unknown = JSON.parse(content)
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || !selectedStageField) throw new Error()
        const record = parsed as Record<string, unknown>
        configJson = { [selectedStageField.key]: record[selectedStageField.key] ?? record }
      } catch {
        message.warning('阶段产物必须是有效的 JSON 对象')
        return
      }
    }
    reviseStageMutation.mutate({
      runId: selectedRun.runId,
      body: {
        stage: final ? 'detailed_cases' : selectedStage!,
        revisionInstruction: revisionInstruction.trim(),
        llmConnectionId: connectionId,
        ...(final ? { resultYaml: content } : { configJson }),
      },
    })
  }

  function handleSaveStageOutput() {
    if (!selectedRun?.runId || !selectedStage) return
    if (!stageOutputDraft.trim()) {
      message.warning('阶段产物不能为空')
      return
    }
    saveStageOutputMutation.mutate({
      runId: selectedRun.runId,
      stage: selectedStage,
      configJson: stageOutputDraft,
    })
  }

  async function handleApproveStageReview() {
    if (!selectedRun?.runId || !selectedStage) return
    if (!stageOutputDraft.trim()) {
      message.warning('阶段产物不能为空')
      return
    }
    setStageReviewAction('approve')
    try {
      await saveStageOutputMutation.mutateAsync({
        runId: selectedRun.runId,
        stage: selectedStage,
        configJson: stageOutputDraft,
        silent: true,
      })
      await reviewStageMutation.mutateAsync({
        runId: selectedRun.runId,
        body: {
          stage: selectedStage,
          action: 'approve',
          comment: stageReviewComment.trim() || undefined,
        },
      })
    } catch {
      setStageReviewAction(null)
    }
  }

  function handleRejectStageReview() {
    if (!selectedRun?.runId || !selectedStage) return
    setStageReviewAction('reject')
    reviewStageMutation.mutate({
      runId: selectedRun.runId,
      body: {
        stage: selectedStage,
        action: 'reject',
        comment: stageReviewComment.trim() || undefined,
      },
    })
  }

  function handleRetryStage() {
    if (!selectedRun?.runId || !selectedStage || !canRetryStage) return
    retryStageMutation.mutate({
      runId: selectedRun.runId,
      stage: selectedStage,
    })
  }

  function openResultModal(runId?: string) {
    if (!runId) return
    setSelectedRunRecordId(runId)
    setResultModalRunId(runId)
    setReviewSubmitAction(null)
    setCandidateModalView('preview')
  }

  function closeResultModal() {
    if (reviseStageMutation.isPending) return
    setRevisionTarget(null)
    if (reviewRunMutation.isPending || updateRunResultMutation.isPending) return
    setResultModalRunId(null)
    setReviewSubmitAction(null)
  }

  function handleApproveReview() {
    if (!resultModalRunId) return
    if (!canReviewSelectedRun) {
      message.warning('当前运行状态不允许批准候选结果')
      return
    }
    setReviewSubmitAction('approve')
    reviewRunMutation.mutate({
      runId: resultModalRunId,
      body: {
        action: 'approve',
        reviewComment: reviewComment.trim() || undefined,
      },
    })
  }

  function handleRejectReview() {
    if (!resultModalRunId) return
    if (!canReviewSelectedRun) {
      message.warning('当前运行状态不允许拒绝候选结果')
      return
    }
    if (!reviewComment.trim()) {
      message.warning('拒绝候选结果时请填写审核备注')
      return
    }
    setReviewSubmitAction('reject')
    reviewRunMutation.mutate({
      runId: resultModalRunId,
      body: {
        action: 'reject',
        reviewComment: reviewComment.trim() || undefined,
      },
    })
  }

  function handleSaveCandidateResult() {
    if (!resultModalRunId || !canEditCandidate) return
    updateRunResultMutation.mutate({ runId: resultModalRunId, resultYaml: candidateYaml })
  }

  function handleImportRun(runId?: string) {
    if (!runId || importRunMutation.isPending) return
    setSelectedRunRecordId(runId)
    setImportAcknowledged(false)
    setImportConfirmRunId(runId)
  }

  function handleConfirmImport() {
    if (!importConfirmRunId || !importDetailsReady || !importAcknowledged || importRunMutation.isPending) return
    importRunMutation.mutate({ runId: importConfirmRunId, confirmOverwrite: false })
    setImportConfirmRunId(null)
    setImportAcknowledged(false)
  }

  function handleConfirmImportOverwrite() {
    if (!importConflict || importRunMutation.isPending) return
    importRunMutation.mutate({ runId: importConflict.runId, confirmOverwrite: true })
  }

  function resolveRunRecord(record: FunctionalCaseGenerateTaskRun): FunctionalCaseGenerateTaskRun {
    return record.runId && record.runId === selectedRunId && selectedRun ? selectedRun : record
  }

  function openRunRecordSection(runId: string | undefined, key: RunResultSectionKey, label: string) {
    setSelectedRunRecordId(runId ?? null)
    // 保留任务页面和滚动位置，在近全屏弹框中查看当前运行图谱。
    if (key === 'caseRelations' && runId && taskId) {
      setGraphRunId(runId)
      return
    }
    setRunResultModal({ key, label })
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
                <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/ai-testing?tab=tasks')}>
                  返回生成任务
                </Button>
              )}
              fields={[
                { label: '任务名称', value: task.name || '未命名任务', kind: 'name', separator: 'line' },
                { label: '迭代', value: task.sprintId ? sprintNameMap.get(task.sprintId) ?? task.sprintId : '-', kind: 'chip-accent' },
                { label: '需求', value: taskRequirementQuery.data?.name ?? (task.requirementId ? requirementNameMap.get(task.requirementId) ?? task.requirementId : '-') },
                { label: '来源类型', value: '需求分析', kind: 'chip-muted' },
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
                  title="需求文档"
                  sub={taskRequirementQuery.data?.name || '查看关联需求内容'}
                  icon={<FileTextOutlined />}
                  active={expandedSection === 'document'}
                  onClick={() => setExpandedSection('document')}
                />
                <TaskDetailNavItem
                  title="生成指令"
                  sub={task.instruction?.trim() || '暂无补充指令'}
                  icon={<CodeOutlined />}
                  active={expandedSection === 'instruction'}
                  onClick={() => setExpandedSection('instruction')}
                />
                <div className="ai-task-detail-nav-label">输出</div>
                <TaskDetailNavItem
                  title="运行记录"
                  sub={`共 ${runRecords.length} 条运行记录`}
                  icon={<HistoryOutlined />}
                  active={expandedSection === 'runHistory'}
                  badge={runRecords.length}
                  onClick={() => setExpandedSection('runHistory')}
                />
              </TaskDetailNavPanel>

              <section className="ai-task-detail-main-panel">
                {expandedSection === 'document' ? (
                  <>
                    <div className="ai-task-detail-main-head">
                      <span className="ai-task-detail-main-head-title">需求文档</span>
                    </div>
                    <div className="ai-task-detail-main-body">
                      {taskRequirementQuery.isLoading ? (
                        <div className="ai-task-run-history-placeholder compact"><Spin /><span>需求内容加载中...</span></div>
                      ) : taskRequirementQuery.data && hasRequirementDocument(taskRequirementQuery.data) ? (
                        <RequirementDocumentPreviewContent
                          embedded
                          requirementId={normalizeRequirementId(taskRequirementQuery.data)}
                          requirementName={taskRequirementQuery.data.name}
                          documentType={taskRequirementQuery.data.documentType}
                          documentContent={taskRequirementQuery.data.documentContent}
                          documentFilename={taskRequirementQuery.data.documentFilename}
                          documentDownloadUrl={taskRequirementQuery.data.documentDownloadUrl}
                        />
                      ) : (
                        <div className="ai-task-run-history-placeholder compact"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="关联需求暂无可展示文档" /></div>
                      )}
                    </div>
                  </>
                ) : expandedSection === 'instruction' ? (
                  <>
                    <div className="ai-task-detail-main-head">
                      <span className="ai-task-detail-main-head-title">生成指令</span>
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
                ) : (
                  <>
                    <div className="ai-task-detail-main-head">
                      <span className="ai-task-detail-main-head-title">运行记录</span>
                      <div className="ai-task-detail-main-head-extra">
                        <div className="ai-task-run-history-toolbar">
                          <Select
                            size="small"
                            className="ai-task-run-stage-filter"
                            aria-label="按状态筛选运行记录"
                            value={runStageFilter}
                            options={runStageFilterOptions}
                            onChange={(value) => setRunStageFilter(value)}
                          />
                          <span className="ai-task-run-history-auto-refresh">每 5 秒自动刷新</span>
                          <ActionButton size="small" operation="refresh" loading={runHistoryRefreshing} onClick={handleRefreshRuns}>刷新</ActionButton>
                        </div>
                      </div>
                    </div>
                    <div className="ai-task-detail-main-body">
                      {runsQuery.isLoading ? (
                        <div className="ai-task-run-history-placeholder">
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="运行记录加载中..." />
                        </div>
                      ) : runRecords.length > 0 ? (
                        <>
                          <TaskDetailRunMetrics
                            {...summarizeRunStatuses(filteredRunRecords)}
                            latestStatus={renderApiCaseGenerateTaskRunStatusTag(filteredRunRecords[0]?.status)}
                          />
                          <RunHistoryTable<FunctionalCaseGenerateTaskRun>
                            rows={filteredRunRecords}
                            getRunId={(record) => record.runId}
                            selectedRunId={selectedRunId}
                            resolveRow={resolveRunRecord}
                            onSelect={(runId) => setSelectedRunRecordId(runId ?? null)}
                            renderStatus={(row) => {
                              const data = resolveRunRecord(row)
                              const repairProgress = String(data.status ?? '') === 'running' ? getOutputRepairProgress(data.resultSummaryJson) : null
                              const stageTag = row.runId === selectedRunId && data.checkpointEnabled && data.currentStage && data.currentStage !== 'completed'
                                ? <Tag color={selectedStageMeta.color}>{selectedStageMeta.label}</Tag>
                                : null
                              return <RunPipelineStatus run={data} repairProgress={repairProgress} stageTag={stageTag} />
                            }}
                            renderArtifacts={(row) => {
                              const artifacts = getRunRecordArtifacts(resolveRunRecord(row).configJson)
                              return (
                                <RunArtifacts
                                  artifacts={artifacts}
                                  onOpen={(key) => {
                                    const label = artifacts.find((artifact) => artifact.key === key)?.label ?? key
                                    openRunRecordSection(row.runId, key as RunResultSectionKey, label)
                                  }}
                                />
                              )
                            }}
                            getReviewedAt={(row) => resolveRunRecord(row).reviewedAt}
                            getReviewComment={(row) => resolveRunRecord(row).reviewComment}
                            getImportedAt={(row) => resolveRunRecord(row).importedAt}
                            renderActions={(row, active) => {
                              const data = resolveRunRecord(row)
                              const recordStatus = String(data.status ?? '')
                              const recordSucceeded = recordStatus.toLowerCase() === 'success'
                              const recordFailed = ['failed', 'error'].includes(recordStatus.toLowerCase())
                              const reviewStatus = normalizeReviewStatus(data.reviewStatus)
                              const canReviewRecord = reviewStatus === 'pending' && recordStatus === 'success'
                              const canImportRecord = reviewStatus === 'approved' && data.importStatus === 'pending' && recordStatus === 'success'
                              const recordHasResultYaml = Boolean(formatStructuredContent(data.resultYaml))
                              const recordHasErrorMessage = Boolean(data.errorMessage?.trim())
                              const hasGraph = Boolean(getConfigStageFieldContent(data.configJson, 'caseRelations'))
                              const relationActionAllowed = reviewStatus === 'approved' && (recordSucceeded || recordFailed)
                              const stageReviewEntry = active && checkpointStageWaitingReview && selectedStageField
                              return (
                                <RunRowActions
                                  inline={
                                    <>
                                      {/* 审核是本行最需要用户处理的动作，直接放在操作列，「更多」只留状态变更类操作。 */}
                                      {stageReviewEntry ? (
                                        <Button
                                          size="small"
                                          type="primary"
                                          onClick={(event) => {
                                            event.stopPropagation()
                                            openRunRecordSection(row.runId, selectedStageField!.key as RunResultSectionKey, '审核')
                                          }}
                                        >
                                          审核
                                        </Button>
                                      ) : null}
                                      {canReviewRecord && can('read') ? (
                                        <Button
                                          size="small"
                                          onClick={(event) => {
                                            event.stopPropagation()
                                            openResultModal(row.runId)
                                          }}
                                        >
                                          {can('review') ? '审核结果' : '查看候选结果'}
                                        </Button>
                                      ) : null}
                                      {!canReviewRecord && recordSucceeded && recordHasResultYaml ? (
                                        <Button
                                          size="small"
                                          onClick={(event) => {
                                            event.stopPropagation()
                                            openResultModal(row.runId)
                                          }}
                                        >
                                          查看结果
                                        </Button>
                                      ) : null}
                                      {recordFailed && recordHasErrorMessage ? (
                                        <button
                                          type="button"
                                          className="ai-task-run-result-popover-btn"
                                          onClick={(event) => {
                                            event.stopPropagation()
                                            openRunRecordSection(row.runId, 'errorMessage', '错误信息')
                                          }}
                                        >
                                          错误信息
                                        </button>
                                      ) : null}
                                      {!data.importMigrationComplete ? <RunMigrationWarningIcon /> : null}
                                    </>
                                  }
                                  menuItems={[
                                    ...(active && canRetryStage && can('execute')
                                      ? [{ key: 'retryStage', label: '重试阶段', disabled: retryStageMutation.isPending }]
                                      : []),
                                    ...(canImportRecord && can('execute')
                                      ? [{ key: 'importCases', label: '导入正式用例', disabled: importRunMutation.isPending }]
                                      : []),
                                    ...(relationActionAllowed && can('execute')
                                      ? [{
                                        key: 'generateRelations',
                                        label: hasGraph ? '重新生成图谱' : '生成图谱',
                                        disabled: generateRelationMutation.isPending && active,
                                      }]
                                      : []),
                                    ...(row.runId && can('write')
                                      ? [{
                                          key: 'deleteRun',
                                          label: '删除运行记录',
                                          danger: true,
                                          disabled: !isRunDeletable(data.status) || deleteRunMutation.isPending,
                                        }]
                                      : []),
                                  ]}
                                  onMenuAction={(key) => {
                                    if (key === 'retryStage') {
                                      handleRetryStage()
                                      return
                                    }
                                    if (key === 'importCases') {
                                      handleImportRun(row.runId)
                                      return
                                    }
                                    if (key === 'generateRelations' && row.runId) {
                                      generateRelationMutation.mutate({ runId: row.runId })
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
                          {selectedRunQuery.isLoading && !selectedRun ? (
                            <div className="ai-task-run-history-placeholder compact">
                              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="运行详情加载中..." />
                            </div>
                          ) : null}
                          {selectedRun && selectedRunResultSections.length === 0 && !checkpointStageVisible ? (
                            <div className="ai-task-run-history-hint compact">当前选中记录暂无可展示结果</div>
                          ) : null}
                        </>
                      ) : (
                        <div className="ai-task-run-history-placeholder">
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有运行记录" />
                          <div className="ai-task-run-history-hint">点击上方“运行”后，任务状态和最近一次执行信息会展示在这里。</div>
                        </div>
                      )}
                    </div>
                  </>
                )}
              </section>
            </div>
          </div>
        ) : (
          <Alert showIcon type="warning" title="未找到对应任务" />
        )}

        <FunctionalCaseGenerateTaskDrawer
          title="编辑功能用例生成任务"
          open={drawerOpen}
          form={form}
          editing
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

        <Modal
          className="ai-relations-modal"
          title="用例图谱"
          open={Boolean(graphRunId)}
          onCancel={() => setGraphRunId(null)}
          footer={null}
          width="95vw"
          style={{ top: '5dvh', paddingBottom: 0 }}
          styles={{ body: { height: 'calc(90dvh - 88px)', minHeight: 0, overflow: 'hidden' } }}
          mask={{ closable: false }}
          destroyOnHidden
        >
          {graphRunId ? <FunctionalCaseRelationsViewer key={`${taskId}:${graphRunId}`} taskId={taskId} runId={graphRunId} /> : null}
        </Modal>

        <Modal
          mask={{ closable: false }}
          className={`ai-task-run-result-modal${showStageReviewInRunResultModal ? ' review functional-stage-review-modal' : ''}${showStageReviewInRunResultModal && revisionTarget !== 'stage' ? ' stage-review-with-comment' : ''}`}
          title={showStageReviewInRunResultModal ? '审核' : runResultModal?.label ?? '运行结果'}
          open={Boolean(runResultModal)}
          onCancel={() => { if (!reviseStageMutation.isPending) { setRevisionTarget(null); setRunResultModal(null) } }}
          footer={
            revisionTarget === 'stage' ? <div ref={setRevisionFooter} /> : showStageReviewInRunResultModal
              ? [
                <div key="comment" className="ai-task-stage-review-footer-comment">
                  <Input.TextArea
                    className="ai-task-stage-review-comment"
                    value={stageReviewComment}
                    onChange={(event) => setStageReviewComment(event.target.value)}
                    rows={2}
                    aria-label="审核备注"
                    placeholder="审核备注，可选"
                  />
                </div>,
                <Button key="close" onClick={() => { setRevisionTarget(null); setRunResultModal(null) }}>
                  关闭
                </Button>,
                <ProjectActionButton operation="save" action="write"
                  key="save"
                  onClick={handleSaveStageOutput}
                  loading={saveStageOutputMutation.isPending && !stageReviewAction}
                  disabled={reviewStageMutation.isPending || reviseStageMutation.isPending}
                >
                  保存
                </ProjectActionButton>,
                canReviseCheckpoint ? (
                  <ProjectActionButton action="execute" key="revise" disabled={stageActionPending} onClick={() => openRevisionModal('stage')}>
                    继续优化
                  </ProjectActionButton>
                ) : null,
                <ProjectActionButton action="review"
                  key="reject"
                  danger
                  ghost
                  onClick={handleRejectStageReview}
                  loading={reviewStageMutation.isPending && stageReviewAction === 'reject'}
                  disabled={saveStageOutputMutation.isPending || reviseStageMutation.isPending}
                >
                  审核不通过
                </ProjectActionButton>,
                <ProjectActionButton action="review"
                  key="approve"
                  type="primary"
                  onClick={handleApproveStageReview}
                  loading={stageActionPending && stageReviewAction === 'approve'}
                  disabled={reviseStageMutation.isPending || (reviewStageMutation.isPending && stageReviewAction !== 'approve')}
                >
                  审核通过并继续
                </ProjectActionButton>,
              ]
              : [
                <Button key="close" type="primary" onClick={() => { setRevisionTarget(null); setRunResultModal(null) }}>
                  关闭
                </Button>,
              ]
          }
          width={revisionTarget === 'stage' ? "calc(100vw - 56px)" : "min(1620px, calc(100vw - 72px))"}
          centered
          destroyOnHidden
        >
          <div className={`revision-workspace${revisionTarget === 'stage' ? ' is-revising' : ''}`}><div className="revision-source">
            <div className={`ai-task-run-result-modal-content${showStageReviewInRunResultModal ? ' review' : ''}`}>
              {selectedRunQuery.isLoading ? (
                <div className="ai-task-run-result-popover-loading">
                  <Spin />
                </div>
              ) : showStageReviewInRunResultModal ? (
                <div className="ai-task-stage-review-popover">
                  <div className="ai-task-run-result-popover-header">
                    <span>阶段产物 {selectedStageField?.label ?? '当前阶段'}</span>
                    <div className="ai-task-stage-review-mini-tags">
                      <Tag color={selectedStageMeta.color}>{selectedStageMeta.label}</Tag>
                      <Tag color={selectedStageStatusMeta.color}>{selectedStageStatusMeta.label}</Tag>
                    </div>
                  </div>
                  <div className="ai-task-stage-review-note compact">
                    <strong>待审核/可编辑</strong>
                    <span>当前编辑的是本阶段产物，保存后会写回当前阶段输出，审核通过后继续进入下一阶段。</span>
                  </div>
                  {stageOutputIsCaseNames ? (
                    <Tabs
                      className="ai-case-names-inner-tabs expanded review"
                      size="small"
                      items={[
                        {
                          key: 'tree',
                          label: '可视化',
                          children: (
                            <CaseNameTreeView
                              content={stageOutputDraft}
                              rootTitle={task?.name || '功能测试用例生成'}
                              expanded
                              editable
                              onTreeChange={(value) => {
                                setStageOutputDraft(value)
                                setStageOutputDirty(true)
                              }}
                            />
                          ),
                        },
                        {
                          key: 'json',
                          label: 'json',
                          children: (
                            <TextCodeEditor
                              value={stageOutputDraft}
                              language="json"
                              onChange={(value) => {
                                setStageOutputDraft(value)
                                setStageOutputDirty(true)
                              }}
                              minHeight={360}
                            />
                          ),
                        },
                      ]}
                    />
                  ) : stageOutputIsRequirementAnalysis ? (
                    <Tabs
                      className="ai-requirement-analysis-tabs review"
                      size="small"
                      activeKey={stageRequirementAnalysisView}
                      onChange={(key) => setStageRequirementAnalysisView(key as RequirementAnalysisViewMode)}
                      items={[
                        {
                          key: 'diagram',
                          label: '可视化',
                          children: (
                            <div className="ai-requirement-analysis-review-diagram">
                              <RequirementAnalysisDiagramView content={stageOutputDraft} />
                            </div>
                          ),
                        },
                        {
                          key: 'json',
                          label: 'json',
                          children: (
                            <TextCodeEditor
                              value={stageOutputDraft}
                              language="json"
                              onChange={(value) => {
                                setStageOutputDraft(value)
                                setStageOutputDirty(true)
                              }}
                              minHeight={360}
                            />
                          ),
                        },
                      ]}
                    />
                  ) : (
                    <TextCodeEditor
                      value={stageOutputDraft}
                      onChange={(value) => {
                        setStageOutputDraft(value)
                        setStageOutputDirty(true)
                      }}
                      minHeight={360}
                    />
                  )}

                </div>
              ) : runResultModalContent ? (
                runResultModal?.key === 'caseNames' ? (
                  <CaseNamesResultView
                    content={runResultModalContent}
                    rootTitle={task?.name || '功能测试用例生成'}
                    expanded
                    activeView={runResultCaseNamesView}
                    onViewChange={setRunResultCaseNamesView}
                  />
                ) : runResultModal?.key === 'requirementAnalysis' ? (
                  <RequirementAnalysisView content={runResultModalContent} />
                ) : runResultModal?.key === 'enhancedText' ? (
                  isJsonText(runResultModalContent) ? (
                    <JsonEditor value={runResultModalContent} readOnly foldable minHeight={640} />
                  ) : (
                    <pre className="ai-task-code-block">{runResultModalContent}</pre>
                  )
                ) : (
                  <pre className="ai-task-code-block">{runResultModalContent}</pre>
                )
              ) : (
                <div className="ai-task-run-result-popover-empty">暂无内容</div>
              )}
            </div>
          </div>{revisionTarget === 'stage' && <><RevisionDivider /><RevisionSidePanel footerContainer={revisionFooter} projectId={task?.projectId} value={revisionInstruction} onChange={setRevisionInstruction} loading={reviseStageMutation.isPending} onCancel={() => setRevisionTarget(null)} onSubmit={handleReviseStage} /></>}</div>
        </Modal>

        <Modal
          mask={{ closable: false }}
          className="ai-task-import-result-modal functional-candidate-review-modal"
          title={
            <div className="functional-candidate-review-title">
              <div>
                <strong>{canReviewSelectedRun ? '审核结果' : '功能测试用例候选结果'}</strong>
                <span title={importTargetRequirementName}>关联需求：{importTargetRequirementName}</span>
              </div>
              <div className="functional-candidate-review-title-stats">
                <span>模块 <strong>{selectedRunImportStats.moduleCount}</strong></span>
                <span>用例 <strong>{selectedRunImportStats.caseCount}</strong></span>
              </div>
            </div>
          }
          open={resultModalOpen}
          onCancel={closeResultModal}
          footer={
            revisionTarget === 'final' ? <div ref={setRevisionFooter} /> : reviewAvailable
              ? (
                <div className="functional-candidate-review-footer">
                  <label htmlFor="functional-review-comment">
                    <span>审核备注 <em>拒绝时必填</em></span>
                    <Input.TextArea
                      id="functional-review-comment"
                      aria-label="审核备注"
                      autoSize={{ minRows: 1, maxRows: 2 }}
                      value={reviewComment}
                      onChange={(event) => setReviewComment(event.target.value)}
                      placeholder="请输入审核意见或补充说明"
                    />
                  </label>
                  <div className="functional-candidate-review-actions">
                    <span>已选择全部 <strong>{selectedRunImportStats.caseCount}</strong> 条</span>
                    <Button onClick={closeResultModal}>取消</Button>
                    {reviewAvailable && selectedRun?.importStatus !== 'imported' ? (
                      <ProjectActionButton action="execute" disabled={updateRunResultMutation.isPending || reviewRunMutation.isPending || reviseStageMutation.isPending}
                        onClick={() => openRevisionModal('final')}>继续优化</ProjectActionButton>
                    ) : null}
                    <ProjectActionButton action="review"
                      danger
                      ghost
                      loading={reviewRunMutation.isPending && reviewSubmitAction === 'reject'}
                      disabled={reviseStageMutation.isPending || updateRunResultMutation.isPending || (reviewRunMutation.isPending && reviewSubmitAction !== 'reject')}
                      onClick={handleRejectReview}
                    >
                      拒绝
                    </ProjectActionButton>
                    <ProjectActionButton action="review"
                      type="primary"
                      loading={reviewRunMutation.isPending && reviewSubmitAction === 'approve'}
                      disabled={reviseStageMutation.isPending || updateRunResultMutation.isPending || (reviewRunMutation.isPending && reviewSubmitAction !== 'approve')}
                      onClick={handleApproveReview}
                    >
                      批准 {selectedRunImportStats.caseCount} 条
                    </ProjectActionButton>
                  </div>
                </div>
              )
              : <Button type="primary" onClick={closeResultModal}>关闭</Button>
          }
          width={revisionTarget === 'final' ? "calc(100vw - 56px)" : "min(1620px, calc(100vw - 72px))"}
          centered
          destroyOnHidden
        >
          <div className={`revision-workspace${revisionTarget === 'final' ? ' is-revising' : ''}`}><div className="revision-source">
            <Form layout="vertical" className="ai-task-import-result-form">
              <Tabs
                className="functional-candidate-review-tabs"
                activeKey={candidateModalView}
                onChange={(key) => setCandidateModalView(key as 'preview' | 'edit')}
                items={[
                  {
                    key: 'preview',
                    label: '可视化',
                    children: (
                      <div className="ai-task-review-modal-content ai-task-result-preview-modal-content ai-task-import-result-preview-content single-column">
                        <div className="ai-task-review-modal-section">
                          <div className="ai-task-review-modal-preview ai-task-import-result-preview">
                            {selectedRunQuery.isLoading ? (
                              <div className="ai-task-run-result-popover-loading">
                                <Spin />
                              </div>
                            ) : selectedRun?.resultYaml ? (
                              <GeneratedCasesReviewView content={formatStructuredContent(selectedRun.resultYaml)} />
                            ) : (
                              <div className="ai-task-run-result-popover-empty">当前记录暂无结果</div>
                            )}
                          </div>
                        </div>
                      </div>
                    ),
                  },
                  {
                    key: 'edit',
                    label: '编辑候选',
                    children: (
                      <div className="ai-task-review-modal-content single-column functional-candidate-edit-pane">
                        <JsonEditor
                          ariaLabel="功能候选结果 JSON"
                          value={candidateYaml}
                          onChange={setCandidateYaml}
                          readOnly={!canEditCandidate}
                          foldable
                          minHeight={0}
                          downloadFileName="功能候选结果.json"
                        />
                        {updateRunResultMutation.error ? (
                          <Alert showIcon type="error" title={getErrorMessage(updateRunResultMutation.error)} />
                        ) : null}
                        {reviewAvailable ? (
                          <ProjectActionButton action="write"
                            type="primary"
                            loading={updateRunResultMutation.isPending}
                            disabled={!candidateDirty || reviewRunMutation.isPending || reviseStageMutation.isPending}
                            onClick={handleSaveCandidateResult}
                          >
                            保存候选结果
                          </ProjectActionButton>
                        ) : null}
                      </div>
                    ),
                  },
                ]}
              />
              {reviewRunMutation.error ? <Alert showIcon type="error" title={getErrorMessage(reviewRunMutation.error)} /> : null}
            </Form>
          </div>{revisionTarget === 'final' && <><RevisionDivider /><RevisionSidePanel footerContainer={revisionFooter} projectId={task?.projectId} value={revisionInstruction} onChange={setRevisionInstruction} loading={reviseStageMutation.isPending} onCancel={() => setRevisionTarget(null)} onSubmit={handleReviseStage} /></>}</div>
        </Modal>

        {importConfirmRunId ? <ProjectActionModal action="execute"
          title={<div className="functional-import-confirm-title"><span className="functional-import-confirm-icon"><FileTextOutlined /></span><span>确认导入正式用例</span></div>}
          className="functional-import-confirm-modal"
          width={560}
          centered
          open={Boolean(importConfirmRunId)}
          okText="确认导入"
          cancelText="取消"
          okButtonProps={{ disabled: !importDetailsReady || !importAcknowledged }}
          onOk={handleConfirmImport}
          onCancel={() => { setImportConfirmRunId(null); setImportAcknowledged(false) }}
        >
          <p className="functional-import-confirm-description">导入后，审核通过的结果将写入对应需求的功能测试集。</p>
          {selectedRunQuery.isError ? (
            <Alert
              showIcon
              type="error"
              title={getErrorMessage(selectedRunQuery.error)}
              action={<Button loading={selectedRunQuery.isFetching} onClick={() => { void selectedRunQuery.refetch() }}>重新加载结果</Button>}
            />
          ) : !importDetailsReady ? (
            <div role="status"><Spin size="small" /> <span>正在加载待导入结果…</span></div>
          ) : (
            <div className="functional-import-confirm-summary">
              <span className="functional-import-confirm-label">关联需求</span>
              <strong>{importTargetRequirementName}</strong>
              <div className="functional-import-confirm-counts">
                <span><b>{selectedRunImportStats.moduleCount}</b> 个模块</span>
                <span><b>{selectedRunImportStats.caseCount}</b> 条用例</span>
              </div>
            </div>
          )}
          <div className={`functional-import-confirm-check${importAcknowledged ? ' is-checked' : ''}`}>
            <Checkbox disabled={!importDetailsReady} checked={importAcknowledged} onChange={(event) => setImportAcknowledged(event.target.checked)}>
              我已确认结果，确定导入正式用例
            </Checkbox>
          </div>
        </ProjectActionModal> : null}

        <FunctionalImportConflictModal
          open={Boolean(importConflict)}
          conflicts={importConflict?.conflicts ?? []}
          loading={importRunMutation.isPending}
          error={importConflict ? importRunMutation.error : undefined}
          onCancel={() => setImportConflict(null)}
          onConfirm={handleConfirmImportOverwrite}
        />

        <LlmConnectionSelectModal
          open={llmSelectOpen}
          projectId={task?.projectId}
          onClose={() => {
            setLlmSelectOpen(false)
            setCheckpointEnabled(false)
          }}
          onConfirm={handleLlmSelectConfirm}
          loading={runTaskMutation.isPending}
          showCheckpointOption
          checkpointEnabled={checkpointEnabled}
          onCheckpointEnabledChange={setCheckpointEnabled}
        />
      </div>
    </div>
  )}</ProjectAccessScope>)
}
