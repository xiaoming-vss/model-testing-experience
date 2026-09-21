import { footerRange } from '@/shared/utils/pagination'
import { ActionButton } from '@/shared/components/ActionButton'
import { AppIcon } from '@/shared/icons'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { usePersonalConnectionChoice } from '@/features/base-services/components/usePersonalConnectionChoice'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { CheckOutlined, DeleteOutlined, EditOutlined, EyeOutlined, MoreOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Dropdown,
  Empty,
  Form,
  Modal,
  Pagination,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiCaseGenerateTaskDrawer, type ApiCaseGenerateTaskFormValues } from '../components/ApiCaseGenerateTaskDrawer'
import { FunctionalCaseGenerateTaskDrawer, type FunctionalCaseGenerateTaskFormValues } from '../components/FunctionalCaseGenerateTaskDrawer'
import { UiCaseGenerateTaskDrawer, type UiCaseGenerateTaskFormValues } from '../components/UiCaseGenerateTaskDrawer'
import { LlmConnectionSelectModal } from '../components/LlmConnectionSelectModal'
import { RequirementAnalysisTaskDrawer, type RequirementAnalysisTaskFormValues } from '../components/RequirementAnalysisTaskDrawer'
import { RequirementAnalysisRunModal, type RequirementAnalysisRunFormValues } from '../components/RequirementAnalysisRunModal'
import { CodeRiskTaskDrawer, type CodeRiskTaskFormValues } from '../components/CodeRiskTaskDrawer'
import type { ApiCaseGenerateTask, ApiCaseGenerateTaskRun, CodeRiskTask, CodeRiskTaskRun, CreateCodeRiskTaskPayload, FunctionalCaseGenerateTask, FunctionalCaseGenerateTaskRun, RequirementAnalysisTask, RequirementAnalysisTaskRun, UiCaseGenerateTask, UiCaseGenerateTaskRun } from '../types'
import { getApiCaseGenerateTaskRunStatusMeta, isRunnableApiCaseGenerateTaskRun } from '../utils/taskStatus'
import '@/features/ai-testing/styles/index.css'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { hasRequirementEnhancedText } from '@/features/requirements/utils/requirementDocument'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage, normalizeRequirementId, normalizeSprintId, pickCreatedAt, pickUpdatedAt } from '@/utils/format'

const { Text } = Typography

type AiTaskKind = 'api' | 'functional' | 'ui' | 'analysis' | 'codeRisk'

type UnifiedAiTask =
  | {
      kind: 'api'
      task: ApiCaseGenerateTask
    }
  | {
      kind: 'functional'
      task: FunctionalCaseGenerateTask
    }
  | {
      kind: 'ui'
      task: UiCaseGenerateTask
    }
  | {
      kind: 'analysis'
      task: RequirementAnalysisTask
    }
  | {
      kind: 'codeRisk'
      task: CodeRiskTask
    }

const createKindOptions: Array<{
  key: AiTaskKind
  title: string
  description: string
  icon: ReactNode
  disabled?: boolean
}> = [
  {
    key: 'analysis',
    title: '需求分析',
    description: '分析需求中的场景、歧义和风险点。',
    icon: <AppIcon name="analysis" />,
  },
  {
    key: 'functional',
    title: '功能测试',
    description: '根据需求文档生成结构化功能测试用例。',
    icon: <AppIcon name="functional" />,
  },
  {
    key: 'api',
    title: 'API测试',
    description: '根据 OpenAPI / Swagger 生成 API 用例。',
    icon: <AppIcon name="api" />,
  },
  {
    key: 'ui',
    title: 'UI测试',
    description: '上传 ZIP 源码包生成可编辑、可审核的 UI 候选用例。',
    icon: <AppIcon name="ui" />,
  },
  {
    key: 'codeRisk',
    title: '代码风险分析',
    description: '分析需求绑定代码的变更风险，输出受影响用例与覆盖缺口。',
    icon: <AppIcon name="codeRisk" />,
  },
]

function getTaskId(task: ApiCaseGenerateTask) {
  return task.taskId ?? ''
}

function getFunctionalTaskId(task: FunctionalCaseGenerateTask) {
  return task.taskId ?? ''
}

function getUiTaskId(task: UiCaseGenerateTask) {
  return task.taskId ?? ''
}

function getRequirementAnalysisTaskId(task: RequirementAnalysisTask) {
  return task.taskId ?? ''
}

function getCodeRiskTaskId(task: CodeRiskTask) {
  return task.taskId ?? ''
}

function getUnifiedTaskKey(item: UnifiedAiTask) {
  if (item.kind === 'api') return `api:${getTaskId(item.task)}`
  if (item.kind === 'functional') return `functional:${getFunctionalTaskId(item.task)}`
  if (item.kind === 'ui') return `ui:${getUiTaskId(item.task)}`
  if (item.kind === 'analysis') return `analysis:${getRequirementAnalysisTaskId(item.task)}`
  return `codeRisk:${getCodeRiskTaskId(item.task)}`
}

function getUnifiedTaskTime(item: UnifiedAiTask) {
  const time = new Date(item.task.updatedAt || item.task.createdAt || '').getTime()
  return Number.isNaN(time) ? 0 : time
}

function getRunSortTime(run: ApiCaseGenerateTaskRun | FunctionalCaseGenerateTaskRun | UiCaseGenerateTaskRun | RequirementAnalysisTaskRun) {
  const time = new Date(run.createdAt || run.startedAt || run.updatedAt || '').getTime()
  return Number.isNaN(time) ? 0 : time
}

function getLatestRun<T extends ApiCaseGenerateTaskRun | FunctionalCaseGenerateTaskRun | UiCaseGenerateTaskRun | RequirementAnalysisTaskRun | CodeRiskTaskRun>(runs?: T[]) {
  return [...(runs ?? [])].sort((left, right) => getRunSortTime(right) - getRunSortTime(left))[0]
}

function sourceTypeLabel(item: UnifiedAiTask) {
  if (item.kind === 'api') {
    return item.task.sourceType === 'swagger' ? 'Swagger导入' : 'OpenAPI导入'
  }
  if (item.kind === 'ui') return 'ZIP 源码包'
  if (item.kind === 'analysis') return '需求文档'
  if (item.kind === 'codeRisk') return '需求代码'
  return '需求分析'
}

function renderLatestRunStatus(status?: ApiCaseGenerateTaskRun['status']) {
  if (!status) {
    return (
      <Tag className="ai-task-status-tag ai-task-status-idle">
        <span className="ai-task-status-indicator" />
        未运行
      </Tag>
    )
  }
  const meta = getApiCaseGenerateTaskRunStatusMeta(status)
  return (
    <Tag className={`ai-task-status-tag ai-task-status-${meta.value}`}>
      <span className="ai-task-status-indicator" />
      {meta.label}
    </Tag>
  )
}

export function UnifiedAiTestingPage({ embedded = false }: { embedded?: boolean }) {
  const { can } = useProjectAccess()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const personalGitlab = usePersonalConnectionChoice('gitlab')
  const { activeProjectId, projectsQuery } = useActiveProject()
  const { activeSprintId: globalSprintId, selectSprint: selectGlobalSprint } = useActiveSprint()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingTask, setEditingTask] = useState<ApiCaseGenerateTask | null>(null)
  const [drawerSprintId, setDrawerSprintId] = useState<string | undefined>(undefined)
  const [functionalDrawerOpen, setFunctionalDrawerOpen] = useState(false)
  const [editingFunctionalTask, setEditingFunctionalTask] = useState<FunctionalCaseGenerateTask | null>(null)
  const [functionalDrawerSprintId, setFunctionalDrawerSprintId] = useState<string | undefined>(undefined)
  const [createKindModalOpen, setCreateKindModalOpen] = useState(false)
  const [selectedCreateKind, setSelectedCreateKind] = useState<AiTaskKind>('api')
  const [llmSelectTaskId, setLlmSelectTaskId] = useState<string | null>(null)
  const [functionalLlmSelectTaskId, setFunctionalLlmSelectTaskId] = useState<string | null>(null)
  const [uiLlmSelectTaskId, setUiLlmSelectTaskId] = useState<string | null>(null)
  const [functionalCheckpointEnabled, setFunctionalCheckpointEnabled] = useState(false)
  const [uiDrawerOpen, setUiDrawerOpen] = useState(false)
  const [uiDrawerSprintId, setUiDrawerSprintId] = useState<string | undefined>(undefined)
  const [analysisDrawerOpen, setAnalysisDrawerOpen] = useState(false)
  const [editingAnalysisTask, setEditingAnalysisTask] = useState<RequirementAnalysisTask | null>(null)
  const [analysisDrawerSprintId, setAnalysisDrawerSprintId] = useState<string | undefined>(undefined)
  const [analysisRunTask, setAnalysisRunTask] = useState<RequirementAnalysisTask | null>(null)
  const [codeRiskLlmSelectTaskId, setCodeRiskLlmSelectTaskId] = useState<string | null>(null)
  const [codeRiskDrawerOpen, setCodeRiskDrawerOpen] = useState(false)
  const [codeRiskDrawerSprintId, setCodeRiskDrawerSprintId] = useState<string | undefined>(undefined)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [activeKind, setActiveKind] = useState<AiTaskKind>('analysis')
  const [form] = Form.useForm<ApiCaseGenerateTaskFormValues>()
  const [functionalForm] = Form.useForm<FunctionalCaseGenerateTaskFormValues>()
  const [uiForm] = Form.useForm<UiCaseGenerateTaskFormValues>()
  const [analysisForm] = Form.useForm<RequirementAnalysisTaskFormValues>()
  const [codeRiskForm] = Form.useForm<CodeRiskTaskFormValues>()

  const tasksQuery = useQuery({
    queryKey: ['apiCaseGenerateTasks', activeProjectId],
    queryFn: () => api.getApiCaseGenerateTasks(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const functionalTasksQuery = useQuery({
    queryKey: ['functionalCaseGenerateTasks', activeProjectId],
    queryFn: () => api.getFunctionalCaseGenerateTasks(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const uiTasksQuery = useQuery({
    queryKey: ['uiCaseGenerateTasks', activeProjectId],
    queryFn: () => api.getUiCaseGenerateTasks(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const analysisTasksQuery = useQuery({
    queryKey: ['requirementAnalysisTasks', activeProjectId],
    queryFn: () => api.getRequirementAnalysisTasks(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const codeRiskTasksQuery = useQuery({
    queryKey: ['codeRiskTasks', activeProjectId],
    queryFn: () => api.getCodeRiskTasks(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const sprintsQuery = useQuery({
    queryKey: ['sprints', 'aiTesting', activeProjectId],
    queryFn: () => api.getSprints(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const sprintOptions = useMemo(
    () => listItems(sprintsQuery.data).map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) })),
    [sprintsQuery.data],
  )
  const requirementOptionsQuery = useQuery({
    queryKey: ['requirements', 'aiTesting', drawerSprintId],
    queryFn: () => api.getRequirements(drawerSprintId!),
    enabled: Boolean(drawerSprintId),
  })
  const functionalRequirementOptionsQuery = useQuery({
    queryKey: ['requirements', 'aiTestingFunctional', functionalDrawerSprintId],
    queryFn: () => api.getRequirements(functionalDrawerSprintId!),
    enabled: Boolean(functionalDrawerSprintId),
  })
  const uiRequirementOptionsQuery = useQuery({
    queryKey: ['requirements', 'aiTestingUi', uiDrawerSprintId],
    queryFn: () => api.getRequirements(uiDrawerSprintId!),
    enabled: Boolean(uiDrawerSprintId),
  })
  const allRequirementsQuery = useQuery({
    queryKey: ['requirementsPool', 'aiTesting', activeProjectId, sprintOptions.map((item) => item.value).join(',')],
    queryFn: async () => {
      if (!sprintsQuery.data || sprintsQuery.data.length === 0) return []
      const groups = await Promise.all(sprintsQuery.data.map((sprint) => api.getRequirements(normalizeSprintId(sprint))))
      return groups.flat()
    },
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })
  const requirementOptions = useMemo(
    () =>
      listItems(requirementOptionsQuery.data).map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    [requirementOptionsQuery.data],
  )
  const functionalRequirementOptions = useMemo(
    () =>
      listItems(functionalRequirementOptionsQuery.data).map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    [functionalRequirementOptionsQuery.data],
  )
  const uiRequirementOptions = useMemo(
    () =>
      listItems(uiRequirementOptionsQuery.data).map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    [uiRequirementOptionsQuery.data],
  )
  const analysisRequirementOptions = useMemo(
    () =>
      listItems(allRequirementsQuery.data)
        .filter((requirement) => !analysisDrawerSprintId || requirement.sprintId === analysisDrawerSprintId)
        .map((requirement) => ({ label: requirement.name, value: normalizeRequirementId(requirement) })),
    [allRequirementsQuery.data, analysisDrawerSprintId],
  )
  const codeRiskRequirementOptions = useMemo(
    () =>
      listItems(allRequirementsQuery.data)
        .filter((requirement) => !codeRiskDrawerSprintId || requirement.sprintId === codeRiskDrawerSprintId)
        .map((requirement) => ({ label: requirement.name, value: normalizeRequirementId(requirement) })),
    [allRequirementsQuery.data, codeRiskDrawerSprintId],
  )
  const sprintNameMap = useMemo(
    () => new Map(listItems(sprintsQuery.data).map((sprint) => [normalizeSprintId(sprint), sprint.name])),
    [sprintsQuery.data],
  )
  const requirementNameMap = useMemo(
    () => new Map(listItems(allRequirementsQuery.data).map((requirement) => [normalizeRequirementId(requirement), requirement.name])),
    [allRequirementsQuery.data],
  )
  const requirementMap = useMemo(
    () => new Map(listItems(allRequirementsQuery.data).map((requirement) => [normalizeRequirementId(requirement), requirement])),
    [allRequirementsQuery.data],
  )

  const unifiedTasks = useMemo<UnifiedAiTask[]>(
    () =>
      [
        ...listItems(tasksQuery.data).map((task) => ({ kind: 'api' as const, task })),
        ...listItems(functionalTasksQuery.data).map((task) => ({ kind: 'functional' as const, task })),
        ...listItems(uiTasksQuery.data).map((task) => ({ kind: 'ui' as const, task })),
        ...listItems(analysisTasksQuery.data).map((task) => ({ kind: 'analysis' as const, task })),
        ...listItems(codeRiskTasksQuery.data).map((task) => ({ kind: 'codeRisk' as const, task })),
      ]
        .filter((item) => !globalSprintId || item.task.sprintId === globalSprintId)
        .sort((left, right) => getUnifiedTaskTime(right) - getUnifiedTaskTime(left)),
    [
      analysisTasksQuery.data,
      codeRiskTasksQuery.data,
      functionalTasksQuery.data,
      globalSprintId,
      tasksQuery.data,
      uiTasksQuery.data,
    ],
  )
  const filteredTasks = useMemo(
    () => unifiedTasks.filter((item) => item.kind === activeKind),
    [activeKind, unifiedTasks],
  )
  const pagedTasks = useMemo(
    () => filteredTasks.slice((page - 1) * pageSize, page * pageSize),
    [filteredTasks, page, pageSize],
  )
  const kindSegmentOptions = useMemo(
    () =>
      createKindOptions.map((option) => ({
        value: option.key,
        label: (
          <span className="ai-task-kind-segment-label">
            {option.icon}
            {option.title}
            <span className="ai-task-tab-count">{unifiedTasks.filter((item) => item.kind === option.key).length}</span>
          </span>
        ),
      })),
    [unifiedTasks],
  )
  const pagedApiTasks = useMemo(
    () => pagedTasks.filter((item): item is Extract<UnifiedAiTask, { kind: 'api' }> => item.kind === 'api').map((item) => item.task),
    [pagedTasks],
  )
  const pagedFunctionalTasks = useMemo(
    () =>
      pagedTasks
        .filter((item): item is Extract<UnifiedAiTask, { kind: 'functional' }> => item.kind === 'functional')
        .map((item) => item.task),
    [pagedTasks],
  )
  const pagedUiTasks = useMemo(
    () => pagedTasks.filter((item): item is Extract<UnifiedAiTask, { kind: 'ui' }> => item.kind === 'ui').map((item) => item.task),
    [pagedTasks],
  )
  const pagedAnalysisTasks = useMemo(
    () => pagedTasks.filter((item): item is Extract<UnifiedAiTask, { kind: 'analysis' }> => item.kind === 'analysis').map((item) => item.task),
    [pagedTasks],
  )
  const pagedCodeRiskTasks = useMemo(
    () => pagedTasks.filter((item): item is Extract<UnifiedAiTask, { kind: 'codeRisk' }> => item.kind === 'codeRisk').map((item) => item.task),
    [pagedTasks],
  )
  const apiTaskRunQueries = useQueries({
    queries: pagedApiTasks.map((task) => {
      const taskId = getTaskId(task)
      return {
        queryKey: ['apiCaseGenerateTaskRuns', taskId],
        queryFn: () => api.getApiCaseGenerateTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const functionalTaskRunQueries = useQueries({
    queries: pagedFunctionalTasks.map((task) => {
      const taskId = getFunctionalTaskId(task)
      return {
        queryKey: ['functionalCaseGenerateTaskRuns', taskId],
        queryFn: () => api.getFunctionalCaseGenerateTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const uiTaskRunQueries = useQueries({
    queries: pagedUiTasks.map((task) => {
      const taskId = getUiTaskId(task)
      return {
        queryKey: ['uiCaseGenerateTaskRuns', taskId],
        queryFn: () => api.getUiCaseGenerateTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const analysisTaskRunQueries = useQueries({
    queries: pagedAnalysisTasks.map((task) => {
      const taskId = getRequirementAnalysisTaskId(task)
      return {
        queryKey: ['requirementAnalysisTaskRuns', taskId],
        queryFn: () => api.getRequirementAnalysisTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const codeRiskTaskRunQueries = useQueries({
    queries: pagedCodeRiskTasks.map((task) => {
      const taskId = getCodeRiskTaskId(task)
      return {
        queryKey: ['codeRiskTaskRuns', taskId],
        queryFn: () => api.getCodeRiskTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const latestApiRunMap = useMemo(() => {
    const entries = pagedApiTasks.map((task, index) => [
      getTaskId(task),
      {
        isLoading: apiTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(apiTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [apiTaskRunQueries, pagedApiTasks])
  const latestFunctionalRunMap = useMemo(() => {
    const entries = pagedFunctionalTasks.map((task, index) => [
      getFunctionalTaskId(task),
      {
        isLoading: functionalTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(functionalTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [functionalTaskRunQueries, pagedFunctionalTasks])
  const latestUiRunMap = useMemo(() => {
    const entries = pagedUiTasks.map((task, index) => [
      getUiTaskId(task),
      {
        isLoading: uiTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(uiTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [pagedUiTasks, uiTaskRunQueries])
  const latestAnalysisRunMap = useMemo(() => {
    const entries = pagedAnalysisTasks.map((task, index) => [
      getRequirementAnalysisTaskId(task),
      {
        isLoading: analysisTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(analysisTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [analysisTaskRunQueries, pagedAnalysisTasks])
  const latestCodeRiskRunMap = useMemo(() => {
    const entries = pagedCodeRiskTasks.map((task, index) => [
      getCodeRiskTaskId(task),
      {
        isLoading: codeRiskTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(codeRiskTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [codeRiskTaskRunQueries, pagedCodeRiskTasks])
  const selectedCreateKindOption = useMemo(
    () => createKindOptions.find((option) => option.key === selectedCreateKind),
    [selectedCreateKind],
  )

  const activeTaskSource = {
    api: { query: tasksQuery, runsKey: 'apiCaseGenerateTaskRuns' },
    functional: { query: functionalTasksQuery, runsKey: 'functionalCaseGenerateTaskRuns' },
    ui: { query: uiTasksQuery, runsKey: 'uiCaseGenerateTaskRuns' },
    analysis: { query: analysisTasksQuery, runsKey: 'requirementAnalysisTaskRuns' },
    codeRisk: { query: codeRiskTasksQuery, runsKey: 'codeRiskTaskRuns' },
  }[activeKind]
  const activeTaskListFetching = activeTaskSource.query.isFetching

  async function refreshActiveTaskList() {
    await Promise.all([
      activeTaskSource.query.refetch(),
      queryClient.refetchQueries({ queryKey: [activeTaskSource.runsKey], type: 'active' }),
    ])
  }

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(filteredTasks.length / pageSize))
    if (page > maxPage) setPage(maxPage)
  }, [filteredTasks.length, page, pageSize])

  useEffect(() => {
    setPage(1)
  }, [activeProjectId])

  const createTaskMutation = useMutation({
    mutationFn: (values: ApiCaseGenerateTaskFormValues) => api.createApiCaseGenerateTask(activeProjectId!, values),
    onSuccess: () => {
      message.success('任务已创建')
      closeDrawer()
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTasks', activeProjectId] })
    },
  })

  const updateTaskMutation = useMutation({
    mutationFn: (values: ApiCaseGenerateTaskFormValues) => api.updateApiCaseGenerateTask(getTaskId(editingTask!), values),
    onSuccess: (task) => {
      const taskId = getTaskId(task)
      message.success('任务已更新')
      closeDrawer()
      queryClient.setQueryData(['apiCaseGenerateTask', taskId], task)
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTasks', activeProjectId] })
    },
  })

  const deleteTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.deleteApiCaseGenerateTask(taskId),
    onSuccess: (_, taskId) => {
      message.success('任务已删除')
      queryClient.removeQueries({ queryKey: ['apiCaseGenerateTask', taskId], exact: true })
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTasks', activeProjectId] })
    },
  })

  const runTaskMutation = useMutation({
    mutationFn: ({ taskId, connectionId }: { taskId: string; connectionId: string }) =>
      api.runApiCaseGenerateTask(taskId, connectionId),
    onSuccess: (run) => {
      message.success('任务已加入执行队列')
      setLlmSelectTaskId(null)
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTask', run.taskId] })
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTaskRuns', run.taskId] })
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTasks', activeProjectId] })
    },
  })

  const createFunctionalTaskMutation = useMutation({
    mutationFn: (values: FunctionalCaseGenerateTaskFormValues) => api.createFunctionalCaseGenerateTask(activeProjectId!, values),
    onSuccess: () => {
      message.success('功能测试任务已创建')
      closeFunctionalDrawer()
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTasks', activeProjectId] })
    },
  })

  const updateFunctionalTaskMutation = useMutation({
    mutationFn: (values: FunctionalCaseGenerateTaskFormValues) =>
      api.updateFunctionalCaseGenerateTask(getFunctionalTaskId(editingFunctionalTask!), values),
    onSuccess: () => {
      message.success('功能测试任务已更新')
      closeFunctionalDrawer()
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTasks', activeProjectId] })
    },
  })

  const deleteFunctionalTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.deleteFunctionalCaseGenerateTask(taskId),
    onSuccess: () => {
      message.success('功能测试任务已删除')
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTasks', activeProjectId] })
    },
  })

  const runFunctionalTaskMutation = useMutation({
    mutationFn: ({ taskId, connectionId, checkpointEnabled }: { taskId: string; connectionId: string; checkpointEnabled?: boolean }) =>
      api.runFunctionalCaseGenerateTask(taskId, { connectionId, checkpointEnabled }),
    onSuccess: (run) => {
      message.success('任务已加入执行队列')
      setFunctionalLlmSelectTaskId(null)
      setFunctionalCheckpointEnabled(false)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTask', run.taskId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', run.taskId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTasks', activeProjectId] })
    },
  })

  const createUiTaskMutation = useMutation({
    mutationFn: async (values: UiCaseGenerateTaskFormValues) => {
      const { sourceArchiveFile, ...payload } = values
      const task = await api.createUiCaseGenerateTask(activeProjectId!, payload)
      const taskId = getUiTaskId(task)
      try {
        return await api.uploadUiCaseGenerateTaskSourceArchive(taskId, sourceArchiveFile)
      } catch (error) {
        navigate(`/ai-testing/ui-tasks/${taskId}`, {
          state: {
            pendingSourceArchive: sourceArchiveFile,
            pendingSourceArchiveError: getErrorMessage(error),
          },
        })
        throw error
      }
    },
    onSuccess: (task) => {
      const taskId = getUiTaskId(task)
      message.success('UI 任务和源码包已创建')
      closeUiDrawer()
      queryClient.setQueryData(['uiCaseGenerateTask', taskId], task)
      queryClient.invalidateQueries({ queryKey: ['uiCaseGenerateTasks', activeProjectId] })
      navigate(`/ai-testing/ui-tasks/${taskId}`)
    },
  })

  const deleteUiTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.deleteUiCaseGenerateTask(taskId),
    onSuccess: () => {
      message.success('UI 任务已删除')
      queryClient.invalidateQueries({ queryKey: ['uiCaseGenerateTasks', activeProjectId] })
    },
  })

  const runUiTaskMutation = useMutation({
    mutationFn: ({ taskId, connectionId }: { taskId: string; connectionId: string }) =>
      api.runUiCaseGenerateTask(taskId, { connectionId }),
    onSuccess: (run) => {
      message.success('任务已加入执行队列')
      setUiLlmSelectTaskId(null)
      queryClient.invalidateQueries({ queryKey: ['uiCaseGenerateTaskRuns', run.taskId] })
      queryClient.invalidateQueries({ queryKey: ['uiCaseGenerateTasks', activeProjectId] })
    },
  })

  const createAnalysisTaskMutation = useMutation({
    mutationFn: (values: RequirementAnalysisTaskFormValues) => api.createRequirementAnalysisTask(activeProjectId!, values),
    onSuccess: () => {
      message.success('需求分析任务已创建')
      closeAnalysisDrawer()
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTasks', activeProjectId] })
    },
  })
  const createCodeRiskTaskMutation = useMutation({
    mutationFn: (values: CreateCodeRiskTaskPayload) => api.createCodeRiskTask(activeProjectId!, values),
    onSuccess: () => {
      message.success('代码风险分析任务已创建')
      closeCodeRiskDrawer()
      queryClient.invalidateQueries({ queryKey: ['codeRiskTasks', activeProjectId] })
    },
  })

  const updateAnalysisTaskMutation = useMutation({
    mutationFn: (values: RequirementAnalysisTaskFormValues) =>
      api.updateRequirementAnalysisTask(getRequirementAnalysisTaskId(editingAnalysisTask!), values),
    onSuccess: () => {
      message.success('需求分析任务已更新')
      closeAnalysisDrawer()
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTasks', activeProjectId] })
    },
  })
  const deleteAnalysisTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.deleteRequirementAnalysisTask(taskId),
    onSuccess: () => {
      message.success('需求分析任务已删除')
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTasks', activeProjectId] })
    },
  })
  const runAnalysisTaskMutation = useMutation({
    mutationFn: ({ taskId, values }: { taskId: string; values: RequirementAnalysisRunFormValues }) =>
      api.runRequirementAnalysisTask(taskId, { ...values, triggerType: 'manual', configJson: '{}' }),
    onSuccess: (run) => {
      message.success('需求分析任务已加入执行队列')
      setAnalysisRunTask(null)
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTaskRuns', run.taskId] })
      queryClient.invalidateQueries({ queryKey: ['requirementAnalysisTasks', activeProjectId] })
    },
  })

  function openCreateDrawer() {
    setEditingTask(null)
    const defaultSprintId = globalSprintId ?? sprintOptions[0]?.value
    setDrawerSprintId(defaultSprintId)
    form.setFieldsValue({
      name: '',
      sprintId: defaultSprintId,
      requirementId: undefined,
      sourceType: 'openapi',
      sourceContent: '',
      instruction: '',
    })
    setDrawerOpen(true)
  }

  function openEditDrawer(task: ApiCaseGenerateTask) {
    setEditingTask(task)
    setDrawerSprintId(task.sprintId)
    form.setFieldsValue({
      name: task.name,
      sprintId: task.sprintId,
      requirementId: task.requirementId,
      sourceType: task.sourceType,
      sourceContent: task.sourceContent,
      instruction: task.instruction,
    })
    setDrawerOpen(true)
  }

  function closeDrawer() {
    setDrawerOpen(false)
    setEditingTask(null)
    setDrawerSprintId(undefined)
    form.resetFields()
  }

  function openCreateFunctionalDrawer() {
    setEditingFunctionalTask(null)
    const defaultSprintId = globalSprintId ?? sprintOptions[0]?.value
    setFunctionalDrawerSprintId(defaultSprintId)
    functionalForm.setFieldsValue({
      name: '',
      sprintId: defaultSprintId,
      requirementId: undefined,
      instruction: '',
    })
    setFunctionalDrawerOpen(true)
  }

  function openEditFunctionalDrawer(task: FunctionalCaseGenerateTask) {
    setEditingFunctionalTask(task)
    setFunctionalDrawerSprintId(task.sprintId)
    functionalForm.setFieldsValue({
      name: task.name,
      sprintId: task.sprintId,
      requirementId: task.requirementId,
      instruction: task.instruction,
    })
    setFunctionalDrawerOpen(true)
  }

  function closeFunctionalDrawer() {
    setFunctionalDrawerOpen(false)
    setEditingFunctionalTask(null)
    setFunctionalDrawerSprintId(undefined)
    functionalForm.resetFields()
  }

  function openCreateUiDrawer() {
    const defaultSprintId = globalSprintId ?? sprintOptions[0]?.value
    setUiDrawerSprintId(defaultSprintId)
    uiForm.setFieldsValue({
      name: '',
      sprintId: defaultSprintId,
      requirementId: undefined,
      instruction: '',
      sourceArchiveFile: undefined,
    })
    setUiDrawerOpen(true)
  }

  function closeUiDrawer() {
    setUiDrawerOpen(false)
    setUiDrawerSprintId(undefined)
    uiForm.resetFields()
  }

  function openCreateAnalysisDrawer() {
    setEditingAnalysisTask(null)
    const defaultSprintId = globalSprintId ?? sprintOptions[0]?.value
    setAnalysisDrawerSprintId(defaultSprintId)
    analysisForm.setFieldsValue({ name: '需求分析', sprintId: defaultSprintId, requirementId: undefined, instruction: '' })
    setAnalysisDrawerOpen(true)
  }

  function openEditAnalysisDrawer(task: RequirementAnalysisTask) {
    setEditingAnalysisTask(task)
    setAnalysisDrawerSprintId(task.sprintId)
    analysisForm.setFieldsValue({ name: task.name, sprintId: task.sprintId, requirementId: task.requirementId, instruction: task.instruction })
    setAnalysisDrawerOpen(true)
  }

  function closeAnalysisDrawer() {
    setAnalysisDrawerOpen(false)
    setEditingAnalysisTask(null)
    setAnalysisDrawerSprintId(undefined)
    analysisForm.resetFields()
  }

  function openCodeRiskDrawer() {
    setCodeRiskDrawerSprintId(globalSprintId)
    codeRiskForm.resetFields()
    if (globalSprintId) {
      codeRiskForm.setFieldValue('sprintId', globalSprintId)
    }
    setCodeRiskDrawerOpen(true)
  }

  function closeCodeRiskDrawer() {
    setCodeRiskDrawerOpen(false)
    setCodeRiskDrawerSprintId(undefined)
    codeRiskForm.resetFields()
  }

  function openCreateKindModal() {
    setSelectedCreateKind('api')
    setCreateKindModalOpen(true)
  }

  function handleCreateKindSelect(kind: AiTaskKind) {
    const option = createKindOptions.find((item) => item.key === kind)
    if (option?.disabled) return
    setSelectedCreateKind(kind)
  }

  function handleCreateKindConfirm() {
    if (!selectedCreateKindOption || selectedCreateKindOption.disabled) return

    if (selectedCreateKind === 'api') {
      setCreateKindModalOpen(false)
      openCreateDrawer()
      return
    }
    if (selectedCreateKind === 'functional') {
      setCreateKindModalOpen(false)
      openCreateFunctionalDrawer()
      return
    }
    if (selectedCreateKind === 'analysis') {
      setCreateKindModalOpen(false)
      openCreateAnalysisDrawer()
      return
    }
    if (selectedCreateKind === 'codeRisk') {
      setCreateKindModalOpen(false)
      openCodeRiskDrawer()
      return
    }
    setCreateKindModalOpen(false)
    openCreateUiDrawer()
  }

  const runCodeRiskTaskMutation = useMutation({
    mutationFn: async ({ taskId, connectionId }: { taskId: string; connectionId: string }) =>
      api.runCodeRiskTask(taskId, { llmConnectionId: connectionId, triggerType: 'manual', gitlabConnectionIds: await personalGitlab.forRequirement(activeProjectId!, (await api.getCodeRiskTask(taskId)).requirementId!) }),
    onSuccess: (run) => {
      message.success('任务已加入执行队列')
      setCodeRiskLlmSelectTaskId(null)
      queryClient.invalidateQueries({ queryKey: ['codeRiskTaskRuns', run.taskId] })
      queryClient.invalidateQueries({ queryKey: ['codeRiskTasks', activeProjectId] })
    },
  })

  function handleRunCodeRiskTask(task: CodeRiskTask) {
    const taskId = getCodeRiskTaskId(task)
    const latestRun = latestCodeRiskRunMap.get(taskId)?.latestRun
    if (!isRunnableApiCaseGenerateTaskRun(latestRun?.status)) {
      message.warning('任务执行中，暂时不能重复运行')
      return
    }
    setCodeRiskLlmSelectTaskId(taskId)
  }

  function handleRunTask(task: ApiCaseGenerateTask) {
    const latestRun = latestApiRunMap.get(getTaskId(task))?.latestRun
    if (!isRunnableApiCaseGenerateTaskRun(latestRun?.status)) {
      message.warning('任务执行中，暂时不能重复运行')
      return
    }
    setLlmSelectTaskId(getTaskId(task))
  }

  function handleLlmSelectConfirm(connectionId: string) {
    if (!llmSelectTaskId) return
    runTaskMutation.mutate({ taskId: llmSelectTaskId, connectionId })
  }

  async function handleRunFunctionalTask(task: FunctionalCaseGenerateTask) {
    const latestRun = latestFunctionalRunMap.get(getFunctionalTaskId(task))?.latestRun
    if (!isRunnableApiCaseGenerateTaskRun(latestRun?.status)) {
      message.warning('任务执行中，暂时不能重复运行')
      return
    }

    if (!task.requirementId) {
      message.warning('请先关联需求')
      return
    }

    let requirement = requirementMap.get(task.requirementId)

    if (!requirement) {
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

    if (!requirement) {
      message.warning('未找到关联需求，请先重新选择需求')
      return
    }

    if (!hasRequirementEnhancedText(requirement)) {
      message.warning('请先完成需求分析并导入增强文本，再生成功能用例')
      return
    }

    setFunctionalLlmSelectTaskId(getFunctionalTaskId(task))
  }

  function handleFunctionalLlmSelectConfirm(connectionId: string) {
    if (!functionalLlmSelectTaskId) return
    runFunctionalTaskMutation.mutate({
      taskId: functionalLlmSelectTaskId,
      connectionId,
      checkpointEnabled: functionalCheckpointEnabled,
    })
  }

  function handleRunUiTask(task: UiCaseGenerateTask) {
    const taskId = getUiTaskId(task)
    const latestRun = latestUiRunMap.get(taskId)?.latestRun
    if (!task.sourceArchive) {
      message.warning('请先上传源码 ZIP')
      return
    }
    if (!isRunnableApiCaseGenerateTaskRun(latestRun?.status)) {
      message.warning('任务执行中，暂时不能重复运行')
      return
    }
    setUiLlmSelectTaskId(taskId)
  }

  function handleRunAnalysisTask(task: RequirementAnalysisTask) {
    const latestRun = latestAnalysisRunMap.get(getRequirementAnalysisTaskId(task))?.latestRun
    if (!isRunnableApiCaseGenerateTaskRun(latestRun?.status)) {
      message.warning('任务执行中，暂时不能重复运行')
      return
    }
    setAnalysisRunTask(task)
  }

  function getUnifiedTaskContext(item: UnifiedAiTask) {
    if (item.kind === 'api') {
      const task = item.task
      const taskId = getTaskId(task)
      const runState = latestApiRunMap.get(taskId)
      const latestRun = runState?.latestRun
      const runnableTask = !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(latestRun?.status)
      const detailPath = `/ai-testing/tasks/${taskId}`
      const sprintName = sprintNameMap.get(task.sprintId ?? '') ?? task.sprintId ?? '-'
      const requirementName = requirementNameMap.get(task.requirementId ?? '') ?? task.requirementId ?? '-'

      return { detailPath, latestRun, requirementName, runState, runnableTask, source: sourceTypeLabel(item), sprintName, taskId }
    }

    if (item.kind === 'ui') {
      const task = item.task
      const taskId = getUiTaskId(task)
      const runState = latestUiRunMap.get(taskId)
      const latestRun = runState?.latestRun
      const runnableTask = Boolean(task.sourceArchive) && !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(latestRun?.status)
      const detailPath = `/ai-testing/ui-tasks/${taskId}`
      const sprintName = sprintNameMap.get(task.sprintId ?? '') ?? task.sprintId ?? '-'
      const requirementName = requirementNameMap.get(task.requirementId ?? '') ?? task.requirementId ?? '-'
      return { detailPath, latestRun, requirementName, runState, runnableTask, source: sourceTypeLabel(item), sprintName, taskId }
    }

    if (item.kind === 'analysis') {
      const task = item.task
      const taskId = getRequirementAnalysisTaskId(task)
      const runState = latestAnalysisRunMap.get(taskId)
      const latestRun = runState?.latestRun
      const runnableTask = !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(latestRun?.status)
      const sprintName = sprintNameMap.get(task.sprintId ?? '') ?? task.sprintId ?? '-'
      const requirementName = requirementNameMap.get(task.requirementId ?? '') ?? task.requirementId ?? '-'
      return {
        detailPath: `/ai-testing/requirement-analysis-tasks/${taskId}`,
        latestRun,
        requirementName,
        runState,
        runnableTask,
        source: sourceTypeLabel(item),
        sprintName,
        taskId,
      }
    }

    if (item.kind === 'codeRisk') {
      const task = item.task
      const taskId = getCodeRiskTaskId(task)
      const runState = latestCodeRiskRunMap.get(taskId)
      const latestRun = runState?.latestRun
      const runnableTask = !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(latestRun?.status)
      const detailPath = `/ai-testing/code-risk-tasks/${taskId}`
      const sprintName = sprintNameMap.get(task.sprintId ?? '') ?? task.sprintId ?? '-'
      const requirementName = requirementNameMap.get(task.requirementId ?? '') ?? task.requirementId ?? '-'

      return { detailPath, latestRun, requirementName, runState, runnableTask, source: sourceTypeLabel(item), sprintName, taskId }
    }

    const task = item.task
    const taskId = getFunctionalTaskId(task)
    const runState = latestFunctionalRunMap.get(taskId)
    const latestRun = runState?.latestRun
    const runnableTask = !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(latestRun?.status)
    const detailPath = `/ai-testing/function-tasks/${taskId}`
    const sprintName = sprintNameMap.get(task.sprintId ?? '') ?? task.sprintId ?? '-'
    const requirementName = requirementNameMap.get(task.requirementId ?? '') ?? task.requirementId ?? '-'

    return { detailPath, latestRun, requirementName, runState, runnableTask, source: sourceTypeLabel(item), sprintName, taskId }
  }

  const columns: TableProps<UnifiedAiTask>['columns'] = [
    {
      title: '任务名称',
      key: 'name',
      width: '25%',
      render: (_, item) => (
        <div className="ai-task-list-name">
          <Tooltip title={item.task.name || '未命名任务'}>
            <Text ellipsis>{item.task.name || '未命名任务'}</Text>
          </Tooltip>
        </div>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 104,
      render: (_, item) => (
        <div className="ai-task-list-tags">{renderLatestRunStatus(getUnifiedTaskContext(item).latestRun?.status)}</div>
      ),
    },
    {
      title: '所属迭代/需求',
      key: 'scope',
      ellipsis: true,
      render: (_, item) => {
        const { requirementName, sprintName } = getUnifiedTaskContext(item)
        return (
          <Tooltip title={`${sprintName} / ${requirementName}`}>
            <Text className="ai-task-list-scope" ellipsis>
              {sprintName} / {requirementName}
            </Text>
          </Tooltip>
        )
      },
    },
    {
      title: '来源',
      key: 'source',
      width: 140,
      render: (_, item) => <Text type="secondary">{getUnifiedTaskContext(item).source}</Text>,
    },
    {
      title: '创建时间',
      key: 'createdAt',
      width: 160,
      render: (_, item) => <Text type="secondary">{formatTime(pickCreatedAt(item.task))}</Text>,
    },
    {
      title: '更新时间',
      key: 'updatedAt',
      width: 180,
      render: (_, item) => <Text type="secondary">{formatTime(pickUpdatedAt(item.task) || pickCreatedAt(item.task))}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 138,
      align: 'right',
      render: (_, item) => {
        const { detailPath, runState, runnableTask, taskId } = getUnifiedTaskContext(item)
        const isApiTask = item.kind === 'api'
        const isUiTask = item.kind === 'ui'
        const isAnalysisTask = item.kind === 'analysis'
        const isCodeRiskTask = item.kind === 'codeRisk'
        const runTask = () => {
          if (isApiTask) {
            handleRunTask(item.task)
            return
          }
          if (isUiTask) {
            handleRunUiTask(item.task)
            return
          }
          if (isAnalysisTask) {
            handleRunAnalysisTask(item.task)
            return
          }
          if (isCodeRiskTask) {
            handleRunCodeRiskTask(item.task)
            return
          }
          handleRunFunctionalTask(item.task)
        }
        const editTask = () => {
          if (isApiTask) {
            openEditDrawer(item.task)
            return
          }
          if (isUiTask) {
            navigate(detailPath)
            return
          }
          if (isAnalysisTask) {
            openEditAnalysisDrawer(item.task)
            return
          }
          if (isCodeRiskTask) {
            navigate(detailPath)
            return
          }
          openEditFunctionalDrawer(item.task)
        }
        const deleteTask = () => {
          if (isApiTask) {
            deleteTaskMutation.mutate(taskId)
            return
          }
          if (isUiTask) {
            deleteUiTaskMutation.mutate(taskId)
            return
          }
          if (isAnalysisTask) {
            deleteAnalysisTaskMutation.mutate(taskId)
            return
          }
          if (isCodeRiskTask) {
            message.info('代码风险分析任务不支持删除')
            return
          }
          deleteFunctionalTaskMutation.mutate(taskId)
        }
        const deleting = isApiTask
          ? deleteTaskMutation.isPending && deleteTaskMutation.variables === taskId
          : isUiTask
            ? deleteUiTaskMutation.isPending && deleteUiTaskMutation.variables === taskId
            : isAnalysisTask
              ? deleteAnalysisTaskMutation.isPending && deleteAnalysisTaskMutation.variables === taskId
              : deleteFunctionalTaskMutation.isPending && deleteFunctionalTaskMutation.variables === taskId
        return (
          <Space
            size={6}
            className="ai-task-list-actions"
            onClick={(event) => event.stopPropagation()}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <Tooltip title={runState?.isLoading ? '运行记录加载中' : undefined}>
              <span>
                <ProjectActionButton operation="run" action="execute"
                  size="small"
                  autoInsertSpace={false}
                  className="ai-task-run-button"
                  aria-label="运行任务"
                  disabled={!runnableTask}
                  onClick={runTask}
                >
                  运行
                </ProjectActionButton>
              </span>
            </Tooltip>
            <Dropdown
              trigger={['click']}
              placement="bottomRight"
              classNames={{ root: 'ai-task-more-dropdown' }}
              menu={{
                items: [
                  { key: 'view', icon: <EyeOutlined />, label: '查看详情' },
                  { key: 'edit', icon: <EditOutlined />, label: '编辑任务', title: can('write') ? undefined : '当前角色无此操作权限', disabled: !can('write') },
                  { type: 'divider' },
                  { key: 'delete', danger: true, icon: <DeleteOutlined />, label: '删除任务', title: can('write') ? undefined : '当前角色无此操作权限', disabled: deleting || !can('write') },
                ],
                onClick: ({ key }) => {
                  if (key === 'view') {
                    navigate(detailPath)
                    return
                  }
                  if (!can('write')) return
                  if (key === 'edit') {
                    editTask()
                    return
                  }
                  Modal.confirm({
                    mask: { closable: false },
                    title: '确认删除该任务？',
                    content: '删除后无法恢复，请谨慎操作。',
                    okText: '删除',
                    okButtonProps: { danger: true },
                    cancelText: '取消',
                    onOk: deleteTask,
                  })
                },
              }}
            >
              <Button
                type="text"
                size="small"
                className="ai-task-more-button"
                icon={<MoreOutlined />}
                aria-label="更多操作"
                loading={deleting}
                onClick={(event) => event.stopPropagation()}
              />
            </Dropdown>
          </Space>
        )
      },
    },
  ]

  const content = (
    <>
      <div className="workbench-tabs">
        <section className="workbench-panel workbench-board-panel ai-testing-task-panel">
          <div className="panel-header ai-task-panel-header">
            <div className="workbench-board-switcher">
              <Segmented
                value={activeKind}
                options={kindSegmentOptions}
                onChange={(value) => {
                  setActiveKind(value as AiTaskKind)
                  setPage(1)
                }}
              />
            </div>
            <Space wrap size={8} className="ai-task-panel-tools">
              <ActionButton
                type="text"
                className="ai-task-refresh-button"
                operation="refresh"
                loading={activeTaskListFetching}
                disabled={!activeProjectId}
                aria-label="刷新当前任务列表"
                onClick={() => void refreshActiveTaskList()}
              >
                刷新
              </ActionButton>
              <div className="ai-task-sprint-filter">
                <span className="ai-task-sprint-filter-label">迭代</span>
                <Select
                  className="ai-task-sprint-filter-select"
                  loading={sprintsQuery.isLoading}
                  value={globalSprintId ?? 'all'}
                  placeholder="全部迭代"
                  options={[{ label: '全部迭代', value: 'all' }, ...sprintOptions]}
                  onChange={(value) => {
                    selectGlobalSprint(value)
                    setPage(1)
                  }}
                />
              </div>
              <ProjectActionButton action="write"
                type="primary"
                className="action-btn-create"
                operation="create"
                disabled={!activeProjectId}
                onClick={openCreateKindModal}
              >
                新建任务
              </ProjectActionButton>
            </Space>
          </div>

          {projectsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(projectsQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {tasksQuery.error ? <Alert showIcon type="error" title={getErrorMessage(tasksQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {functionalTasksQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(functionalTasksQuery.error)} style={{ margin: '12px 18px 0' }} />
          ) : null}
          {uiTasksQuery.error ? <Alert showIcon type="error" title={getErrorMessage(uiTasksQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {analysisTasksQuery.error ? <Alert showIcon type="error" title={getErrorMessage(analysisTasksQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {codeRiskTasksQuery.error ? <Alert showIcon type="error" title={getErrorMessage(codeRiskTasksQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}

          <div className="table-body-scroll ai-testing-card-scroll">
            {!activeProjectId ? (
              <div className="sprint-card-loading ai-testing-empty-shell">
                <Empty description="请先选择项目" />
              </div>
            ) : tasksQuery.isLoading || functionalTasksQuery.isLoading || uiTasksQuery.isLoading || analysisTasksQuery.isLoading || codeRiskTasksQuery.isLoading ? (
              <div className="sprint-card-loading ai-testing-empty-shell">
                <Empty description="任务加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </div>
            ) : filteredTasks.length === 0 ? (
              <div className="ai-testing-empty-shell">
                <Empty description="当前类型下暂无任务">
                  <ActionButton type="primary" operation="create" onClick={openCreateKindModal}>
                    创建第一条任务
                  </ActionButton>
                </Empty>
              </div>
            ) : (
              <Table<UnifiedAiTask>
                className="ai-task-list-table"
                columns={columns}
                dataSource={pagedTasks}
                rowKey={getUnifiedTaskKey}
                pagination={false}
                onRow={(item) => ({
                  onClick: () => navigate(getUnifiedTaskContext(item).detailPath),
                })}
              />
            )}
          </div>

          <div className="table-footer">
            <Text type="secondary">{footerRange(filteredTasks.length, page, pageSize)}</Text>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={filteredTasks.length}
              showSizeChanger
              pageSizeOptions={['10', '20', '30', '50']}
              onChange={(nextPage, nextPageSize) => {
                setPage(nextPage)
                setPageSize(nextPageSize)
              }}
            />
          </div>
        </section>
      </div>

      <Modal
        mask={{ closable: false }}
        open={createKindModalOpen}
        title={
          <div className="ai-task-kind-modal-title">
            <span>选择模板</span>
            <Text type="secondary">选择一个生成入口后继续创建任务</Text>
          </div>
        }
        className="ai-task-kind-modal"
        width={760}
        footer={
          <Space size={10}>
            <Button onClick={() => setCreateKindModalOpen(false)}>取消</Button>
            <Button type="primary" disabled={!selectedCreateKindOption || selectedCreateKindOption.disabled} onClick={handleCreateKindConfirm}>
              确认
            </Button>
          </Space>
        }
        onCancel={() => setCreateKindModalOpen(false)}
        destroyOnHidden
      >
        <div className="ai-task-kind-list">
          {createKindOptions.map((option) => {
            const selected = option.key === selectedCreateKind

            return (
              <button
                key={option.key}
                type="button"
                aria-pressed={selected}
                className={`ai-task-kind-row${selected ? ' selected' : ''}`}
                disabled={option.disabled}
                onClick={() => handleCreateKindSelect(option.key)}
              >
                <span className="ai-task-kind-icon">{option.icon}</span>
                <span className="ai-task-kind-copy">
                  <span className="ai-task-kind-title">{option.title}</span>
                  <span className="ai-task-kind-description">{option.description}</span>
                </span>
                {option.disabled ? <span className="ai-task-kind-badge">暂未开放</span> : null}
                {!option.disabled && selected ? (
                  <span className="ai-task-kind-check" aria-hidden="true">
                    <CheckOutlined />
                  </span>
                ) : null}
              </button>
            )
          })}
        </div>
      </Modal>

      <ApiCaseGenerateTaskDrawer
        title={editingTask ? '编辑 API 用例生成任务' : '新建 API 用例生成任务'}
        open={drawerOpen}
        form={form}
        loading={createTaskMutation.isPending || updateTaskMutation.isPending}
        error={createTaskMutation.error ?? updateTaskMutation.error}
        sprintOptions={sprintOptions}
        requirementOptions={requirementOptions}
        onSprintChange={(value) => {
          setDrawerSprintId(value)
          form.setFieldValue('requirementId', undefined)
        }}
        onClose={closeDrawer}
        onFinish={(values) => {
          if (editingTask) {
            updateTaskMutation.mutate(values)
            return
          }
          createTaskMutation.mutate(values)
        }}
      />

      <FunctionalCaseGenerateTaskDrawer
        title={editingFunctionalTask ? '编辑功能用例生成任务' : '新建功能用例生成任务'}
        open={functionalDrawerOpen}
        form={functionalForm}
        editing={Boolean(editingFunctionalTask)}
        loading={createFunctionalTaskMutation.isPending || updateFunctionalTaskMutation.isPending}
        error={createFunctionalTaskMutation.error ?? updateFunctionalTaskMutation.error}
        sprintOptions={sprintOptions}
        requirementOptions={functionalRequirementOptions}
        onSprintChange={(value) => {
          setFunctionalDrawerSprintId(value)
          functionalForm.setFieldValue('requirementId', undefined)
        }}
        onClose={closeFunctionalDrawer}
        onFinish={(values) => {
          if (editingFunctionalTask) {
            updateFunctionalTaskMutation.mutate(values)
            return
          }
          createFunctionalTaskMutation.mutate(values)
        }}
      />

      <UiCaseGenerateTaskDrawer
        open={uiDrawerOpen}
        form={uiForm}
        loading={createUiTaskMutation.isPending}
        error={createUiTaskMutation.error}
        sprintOptions={sprintOptions}
        requirementOptions={uiRequirementOptions}
        onSprintChange={(value) => {
          setUiDrawerSprintId(value)
          uiForm.setFieldValue('requirementId', undefined)
        }}
        onClose={closeUiDrawer}
        onFinish={(values) => createUiTaskMutation.mutate(values)}
      />

      <RequirementAnalysisTaskDrawer
        title={editingAnalysisTask ? '编辑需求分析任务' : '新建需求分析任务'}
        open={analysisDrawerOpen}
        form={analysisForm}
        loading={createAnalysisTaskMutation.isPending || updateAnalysisTaskMutation.isPending}
        error={createAnalysisTaskMutation.error ?? updateAnalysisTaskMutation.error}
        sprintOptions={sprintOptions}
        requirementOptions={analysisRequirementOptions}
        onSprintChange={(value) => {
          setAnalysisDrawerSprintId(value)
          analysisForm.setFieldValue('requirementId', undefined)
        }}
        onClose={closeAnalysisDrawer}
        onFinish={(values) => {
          if (editingAnalysisTask) {
            updateAnalysisTaskMutation.mutate({ ...values, sprintId: analysisDrawerSprintId })
            return
          }
          createAnalysisTaskMutation.mutate({ ...values, sprintId: analysisDrawerSprintId })
        }}
      />

      <CodeRiskTaskDrawer
        title="新建代码风险分析任务"
        open={codeRiskDrawerOpen}
        form={codeRiskForm}
        loading={createCodeRiskTaskMutation.isPending}
        error={createCodeRiskTaskMutation.error}
        sprintOptions={sprintOptions}
        requirementOptions={codeRiskRequirementOptions}
        onSprintChange={(value) => {
          setCodeRiskDrawerSprintId(value)
          codeRiskForm.setFieldValue('requirementId', undefined)
        }}
        onClose={closeCodeRiskDrawer}
        onFinish={(values) => createCodeRiskTaskMutation.mutate(values)}
      />

      <RequirementAnalysisRunModal
        open={Boolean(analysisRunTask)}
        loading={runAnalysisTaskMutation.isPending}
        onClose={() => setAnalysisRunTask(null)}
        onConfirm={(values) => {
          if (analysisRunTask) runAnalysisTaskMutation.mutate({ taskId: getRequirementAnalysisTaskId(analysisRunTask), values })
        }}
      />

      {personalGitlab.dialog}
      <LlmConnectionSelectModal
        projectId={activeProjectId}
        open={Boolean(codeRiskLlmSelectTaskId)}
        onClose={() => setCodeRiskLlmSelectTaskId(null)}
        onConfirm={(connectionId) => {
          if (codeRiskLlmSelectTaskId) runCodeRiskTaskMutation.mutate({ taskId: codeRiskLlmSelectTaskId, connectionId })
        }}
        loading={runCodeRiskTaskMutation.isPending}
      />
      <LlmConnectionSelectModal
        projectId={activeProjectId}
        open={Boolean(llmSelectTaskId)}
        onClose={() => setLlmSelectTaskId(null)}
        onConfirm={handleLlmSelectConfirm}
        loading={runTaskMutation.isPending}
      />
      <LlmConnectionSelectModal
        projectId={activeProjectId}
        open={Boolean(uiLlmSelectTaskId)}
        onClose={() => setUiLlmSelectTaskId(null)}
        onConfirm={(connectionId) => {
          if (uiLlmSelectTaskId) runUiTaskMutation.mutate({ taskId: uiLlmSelectTaskId, connectionId })
        }}
        loading={runUiTaskMutation.isPending}
      />
      <LlmConnectionSelectModal
        projectId={activeProjectId}
        open={Boolean(functionalLlmSelectTaskId)}
        onClose={() => {
          setFunctionalLlmSelectTaskId(null)
          setFunctionalCheckpointEnabled(false)
        }}
        onConfirm={handleFunctionalLlmSelectConfirm}
        loading={runFunctionalTaskMutation.isPending}
        showCheckpointOption
        checkpointEnabled={functionalCheckpointEnabled}
        onCheckpointEnabledChange={setFunctionalCheckpointEnabled}
      />
    </>
  )

  if (embedded) return content

  return <div className="workbench-page ai-testing-page">{content}</div>
}
