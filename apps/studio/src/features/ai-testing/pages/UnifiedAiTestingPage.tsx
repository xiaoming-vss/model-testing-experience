import '@/shared/styles/list-table.css'
import '@/shared/styles/surface-tokens.css'
import { footerRange } from '@/shared/utils/pagination'
import { ActionButton } from '@/shared/components/ActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { usePersonalConnectionChoice } from '@/features/base-services/components/usePersonalConnectionChoice'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  FileTextOutlined,
  MoreOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Dropdown,
  Empty,
  Form,
  Input,
  Modal,
  Pagination,
  Popconfirm,
  Select,
  Space,
  Table,
  Tooltip,
  Typography,
} from 'antd'
import type { InputRef, TableProps } from 'antd'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiCaseGenerateTaskDrawer, type ApiCaseGenerateTaskFormValues } from '../components/ApiCaseGenerateTaskDrawer'
import { FunctionalCaseGenerateTaskDrawer, type FunctionalCaseGenerateTaskFormValues } from '../components/FunctionalCaseGenerateTaskDrawer'
import { UiCaseGenerateTaskDrawer, type UiCaseGenerateTaskFormValues } from '../components/UiCaseGenerateTaskDrawer'
import { LlmConnectionSelectModal } from '../components/LlmConnectionSelectModal'
import { RequirementAnalysisTaskDrawer, type RequirementAnalysisTaskFormValues } from '../components/RequirementAnalysisTaskDrawer'
import { RequirementAnalysisRunModal, type RequirementAnalysisRunFormValues } from '../components/RequirementAnalysisRunModal'
import { CodeRiskTaskDrawer, type CodeRiskTaskFormValues } from '../components/CodeRiskTaskDrawer'
import type { ApiCaseGenerateTask, ApiCaseGenerateTaskRun, ApiCaseGenerateTaskRunStatus, CodeRiskTask, CodeRiskTaskRun, CreateCodeRiskTaskPayload, FunctionalCaseGenerateTask, FunctionalCaseGenerateTaskRun, RequirementAnalysisTask, RequirementAnalysisTaskRun, UiCaseGenerateTask, UiCaseGenerateTaskRun } from '../types'
import { getApiCaseGenerateTaskRunStatusMeta, isApiCaseGenerateTaskRunInProgress, isRunnableApiCaseGenerateTaskRun } from '../utils/taskStatus'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-list-v2.css'
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

const taskKinds: AiTaskKind[] = ['analysis', 'functional', 'api', 'ui', 'codeRisk']

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

function getUnifiedTaskId(item: UnifiedAiTask) {
  if (item.kind === 'api') return getTaskId(item.task)
  if (item.kind === 'functional') return getFunctionalTaskId(item.task)
  if (item.kind === 'ui') return getUiTaskId(item.task)
  if (item.kind === 'analysis') return getRequirementAnalysisTaskId(item.task)
  return getCodeRiskTaskId(item.task)
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

/**
 * 状态筛选档位。设计稿给的是「全部 / 进行中 / 成功 / 待审核」，这里多一档「失败」——
 * 本项目的运行态里有 failed / error，如果只留四档，失败任务只能靠「全部」找，
 * 而失败恰是测试运维最需要一眼捞出来的那一类。
 */
type AiTaskStatusFilter = 'all' | 'in_progress' | 'success' | 'waiting_review' | 'failed'

const AI_TASK_STATUS_FILTERS: Array<{ key: AiTaskStatusFilter; label: string; dot?: string }> = [
  { key: 'all', label: '全部' },
  { key: 'in_progress', label: '进行中', dot: 'tone-status-running' },
  { key: 'success', label: '成功', dot: 'tone-status-success' },
  { key: 'waiting_review', label: '待审核', dot: 'tone-status-warning' },
  { key: 'failed', label: '失败', dot: 'tone-status-danger' },
]

/** 运行态 → 共享九色盘的色调名（surface-tokens.css 的 `.tone-*`）。 */
const runStatusTones: Record<string, string> = {
  draft: 'tone-slate',
  pending: 'tone-amber',
  claimed: 'tone-blue',
  running: 'tone-blue',
  waiting_review: 'tone-amber',
  success: 'tone-green',
  failed: 'tone-red',
  error: 'tone-red',
  canceled: 'tone-slate',
}

/** 一条任务落到哪个筛选档；未跑过（含已取消 / 草稿）不属于任何语义档，只在「全部」里出现。 */
function statusFilterBucket(status?: ApiCaseGenerateTaskRunStatus): AiTaskStatusFilter | null {
  if (status === 'success') return 'success'
  if (status === 'failed' || status === 'error') return 'failed'
  if (status === 'waiting_review') return 'waiting_review'
  if (isApiCaseGenerateTaskRunInProgress(status)) return 'in_progress'
  return null
}

function renderLatestRunStatus(status?: ApiCaseGenerateTaskRunStatus) {
  const meta = getApiCaseGenerateTaskRunStatusMeta(status)
  const label = status ? meta.label : '未运行'

  return (
    <span className={`tp-tone-tag ai-task-status-pill ${runStatusTones[status ?? ''] ?? 'tone-slate'}`}>
      <span className="ai-task-status-indicator" aria-hidden="true" />
      {label}
    </span>
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
  const [searchParams] = useSearchParams()
  const requestedKind = searchParams.get('kind')
  const activeKind: AiTaskKind = taskKinds.find((kind) => kind === requestedKind) ?? 'analysis'
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<AiTaskStatusFilter>('all')
  const [selectedTaskKeys, setSelectedTaskKeys] = useState<string[]>([])
  const keywordInputRef = useRef<InputRef>(null)
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
  /* 分类胶囊这一层只按任务类型收敛；关键词与状态都是它下面的进一步收敛，
     所以运行记录也按「本类型的全部任务」去取，状态档位的计数才是整套数据而不是当前页。 */
  const kindTasks = useMemo(
    () => unifiedTasks.filter((item) => item.kind === activeKind),
    [activeKind, unifiedTasks],
  )
  const keywordTasks = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    if (!text) return kindTasks
    return kindTasks.filter((item) => {
      const { requirementId, sprintId, name } = item.task
      const fields = [
        name,
        sprintId ? sprintNameMap.get(sprintId) : undefined,
        requirementId ? requirementNameMap.get(requirementId) : undefined,
        sourceTypeLabel(item),
      ]
      return fields.some((field) => (field ?? '').toLowerCase().includes(text))
    })
  }, [keyword, kindTasks, requirementNameMap, sprintNameMap])
  const keywordApiTasks = useMemo(
    () => keywordTasks.filter((item): item is Extract<UnifiedAiTask, { kind: 'api' }> => item.kind === 'api').map((item) => item.task),
    [keywordTasks],
  )
  const keywordFunctionalTasks = useMemo(
    () =>
      keywordTasks
        .filter((item): item is Extract<UnifiedAiTask, { kind: 'functional' }> => item.kind === 'functional')
        .map((item) => item.task),
    [keywordTasks],
  )
  const keywordUiTasks = useMemo(
    () => keywordTasks.filter((item): item is Extract<UnifiedAiTask, { kind: 'ui' }> => item.kind === 'ui').map((item) => item.task),
    [keywordTasks],
  )
  const keywordAnalysisTasks = useMemo(
    () => keywordTasks.filter((item): item is Extract<UnifiedAiTask, { kind: 'analysis' }> => item.kind === 'analysis').map((item) => item.task),
    [keywordTasks],
  )
  const keywordCodeRiskTasks = useMemo(
    () => keywordTasks.filter((item): item is Extract<UnifiedAiTask, { kind: 'codeRisk' }> => item.kind === 'codeRisk').map((item) => item.task),
    [keywordTasks],
  )
  const apiTaskRunQueries = useQueries({
    queries: keywordApiTasks.map((task) => {
      const taskId = getTaskId(task)
      return {
        queryKey: ['apiCaseGenerateTaskRuns', taskId],
        queryFn: () => api.getApiCaseGenerateTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const functionalTaskRunQueries = useQueries({
    queries: keywordFunctionalTasks.map((task) => {
      const taskId = getFunctionalTaskId(task)
      return {
        queryKey: ['functionalCaseGenerateTaskRuns', taskId],
        queryFn: () => api.getFunctionalCaseGenerateTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const uiTaskRunQueries = useQueries({
    queries: keywordUiTasks.map((task) => {
      const taskId = getUiTaskId(task)
      return {
        queryKey: ['uiCaseGenerateTaskRuns', taskId],
        queryFn: () => api.getUiCaseGenerateTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const analysisTaskRunQueries = useQueries({
    queries: keywordAnalysisTasks.map((task) => {
      const taskId = getRequirementAnalysisTaskId(task)
      return {
        queryKey: ['requirementAnalysisTaskRuns', taskId],
        queryFn: () => api.getRequirementAnalysisTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const codeRiskTaskRunQueries = useQueries({
    queries: keywordCodeRiskTasks.map((task) => {
      const taskId = getCodeRiskTaskId(task)
      return {
        queryKey: ['codeRiskTaskRuns', taskId],
        queryFn: () => api.getCodeRiskTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const latestApiRunMap = useMemo(() => {
    const entries = keywordApiTasks.map((task, index) => [
      getTaskId(task),
      {
        isLoading: apiTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(apiTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [apiTaskRunQueries, keywordApiTasks])
  const latestFunctionalRunMap = useMemo(() => {
    const entries = keywordFunctionalTasks.map((task, index) => [
      getFunctionalTaskId(task),
      {
        isLoading: functionalTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(functionalTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [functionalTaskRunQueries, keywordFunctionalTasks])
  const latestUiRunMap = useMemo(() => {
    const entries = keywordUiTasks.map((task, index) => [
      getUiTaskId(task),
      {
        isLoading: uiTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(uiTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [keywordUiTasks, uiTaskRunQueries])
  const latestAnalysisRunMap = useMemo(() => {
    const entries = keywordAnalysisTasks.map((task, index) => [
      getRequirementAnalysisTaskId(task),
      {
        isLoading: analysisTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(analysisTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [analysisTaskRunQueries, keywordAnalysisTasks])
  const latestCodeRiskRunMap = useMemo(() => {
    const entries = keywordCodeRiskTasks.map((task, index) => [
      getCodeRiskTaskId(task),
      {
        isLoading: codeRiskTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(codeRiskTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [codeRiskTaskRunQueries, keywordCodeRiskTasks])


  /** 一条任务的最新运行状态，供状态档位计数与过滤共用。 */
  const latestRunStatusOf = useCallback(
    (item: UnifiedAiTask) => {
      if (item.kind === 'api') return latestApiRunMap.get(getTaskId(item.task))?.latestRun?.status
      if (item.kind === 'functional') return latestFunctionalRunMap.get(getFunctionalTaskId(item.task))?.latestRun?.status
      if (item.kind === 'ui') return latestUiRunMap.get(getUiTaskId(item.task))?.latestRun?.status
      if (item.kind === 'analysis') return latestAnalysisRunMap.get(getRequirementAnalysisTaskId(item.task))?.latestRun?.status
      return latestCodeRiskRunMap.get(getCodeRiskTaskId(item.task))?.latestRun?.status
    },
    [latestApiRunMap, latestAnalysisRunMap, latestCodeRiskRunMap, latestFunctionalRunMap, latestUiRunMap],
  )

  /** 状态档位的计数与下面的过滤都基于同一份「本类型 + 关键词」集合。 */
  const statusFilterCounts = useMemo(() => {
    const counts = new Map<AiTaskStatusFilter, number>([['all', keywordTasks.length]])
    keywordTasks.forEach((item) => {
      const bucket = statusFilterBucket(latestRunStatusOf(item))
      if (bucket) counts.set(bucket, (counts.get(bucket) ?? 0) + 1)
    })
    return counts
  }, [keywordTasks, latestRunStatusOf])

  const filteredTasks = useMemo(
    () =>
      statusFilter === 'all'
        ? keywordTasks
        : keywordTasks.filter((item) => statusFilterBucket(latestRunStatusOf(item)) === statusFilter),
    [keywordTasks, latestRunStatusOf, statusFilter],
  )
  const pagedTasks = useMemo(
    () => filteredTasks.slice((page - 1) * pageSize, page * pageSize),
    [filteredTasks, page, pageSize],
  )
  const hasListFilters = Boolean(keyword) || statusFilter !== 'all'
  const deletableSelection = activeKind !== 'codeRisk'
  const selectedTasks = useMemo(
    () => keywordTasks.filter((item) => selectedTaskKeys.includes(getUnifiedTaskKey(item))),
    [keywordTasks, selectedTaskKeys],
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

  useEffect(() => {
    const timer = setTimeout(() => {
      setKeyword(keywordInput.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [keywordInput])

  // 搜索框标了 ⌘K，那就得真的能按：Mac 用 ⌘，其他平台用 Ctrl。
  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey)) return
      event.preventDefault()
      keywordInputRef.current?.focus()
    }

    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

  // 切类型、改筛选都会让勾选的行落出当前集合，勾选跟着清空，避免删掉看不见的任务。
  useEffect(() => {
    setSelectedTaskKeys([])
  }, [activeKind, activeProjectId, keyword, statusFilter])

  const createTaskMutation = useMutation({
    mutationFn: (values: ApiCaseGenerateTaskFormValues) => api.createApiCaseGenerateTask(activeProjectId!, values),
    onSuccess: () => {
      message.success('任务已创建')
      closeDrawer()
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTasks', activeProjectId] })
    },
  })

  /** 批量删除：列表同一时间只显示一个类型，所以勾选的行类型一致，按类型分派删除接口。 */
  const batchDeleteTasksMutation = useMutation({
    mutationFn: async (items: UnifiedAiTask[]) => {
      await Promise.all(
        items.map((item) => {
          const taskId = getUnifiedTaskId(item)
          if (item.kind === 'api') return api.deleteApiCaseGenerateTask(taskId)
          if (item.kind === 'functional') return api.deleteFunctionalCaseGenerateTask(taskId)
          if (item.kind === 'ui') return api.deleteUiCaseGenerateTask(taskId)
          return api.deleteRequirementAnalysisTask(taskId)
        }),
      )
      return items.length
    },
    onSuccess: (count) => {
      message.success(`已删除 ${count} 个任务`)
      setSelectedTaskKeys([])
      refreshActiveTaskList()
    },
    onError: (error) => message.error(getErrorMessage(error)),
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

  function openCreateTask() {
    const openDrawer = {
      api: openCreateDrawer,
      functional: openCreateFunctionalDrawer,
      analysis: openCreateAnalysisDrawer,
      codeRisk: openCodeRiskDrawer,
      ui: openCreateUiDrawer,
    }[activeKind]
    openDrawer()
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

  /**
   * 列表各列（名称、状态、迭代 / 需求、来源文档、操作）要用的派生数据。
   * 只有「任务 ID、详情路径、可运行性」随类型不同，其余一段算完再展开。
   */
  function getUnifiedTaskContext(item: UnifiedAiTask) {
    const task = item.task
    const requirement = task.requirementId ? requirementMap.get(task.requirementId) : undefined
    const common = {
      requirement,
      requirementName: requirementNameMap.get(task.requirementId ?? '') ?? task.requirementId ?? '-',
      source: sourceTypeLabel(item),
      sprintName: sprintNameMap.get(task.sprintId ?? '') ?? task.sprintId ?? '-',
    }

    if (item.kind === 'api') {
      const taskId = getTaskId(item.task)
      const runState = latestApiRunMap.get(taskId)
      const latestRun = runState?.latestRun
      return {
        ...common,
        detailPath: `/ai-testing/tasks/${taskId}`,
        latestRun,
        runState,
        runnableTask: !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(latestRun?.status),
        taskId,
      }
    }

    if (item.kind === 'ui') {
      const taskId = getUiTaskId(item.task)
      const runState = latestUiRunMap.get(taskId)
      const latestRun = runState?.latestRun
      return {
        ...common,
        detailPath: `/ai-testing/ui-tasks/${taskId}`,
        latestRun,
        runState,
        runnableTask: Boolean(item.task.sourceArchive) && !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(latestRun?.status),
        taskId,
      }
    }

    if (item.kind === 'analysis') {
      const taskId = getRequirementAnalysisTaskId(item.task)
      const runState = latestAnalysisRunMap.get(taskId)
      const latestRun = runState?.latestRun
      return {
        ...common,
        detailPath: `/ai-testing/requirement-analysis-tasks/${taskId}`,
        latestRun,
        runState,
        runnableTask: !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(latestRun?.status),
        taskId,
      }
    }

    if (item.kind === 'codeRisk') {
      const taskId = getCodeRiskTaskId(item.task)
      const runState = latestCodeRiskRunMap.get(taskId)
      const latestRun = runState?.latestRun
      return {
        ...common,
        detailPath: `/ai-testing/code-risk-tasks/${taskId}`,
        latestRun,
        runState,
        runnableTask: !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(latestRun?.status),
        taskId,
      }
    }

    const taskId = getFunctionalTaskId(item.task)
    const runState = latestFunctionalRunMap.get(taskId)
    const latestRun = runState?.latestRun
    return {
      ...common,
      detailPath: `/ai-testing/function-tasks/${taskId}`,
      latestRun,
      runState,
      runnableTask: !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(latestRun?.status),
      taskId,
    }
  }

  const columns: TableProps<UnifiedAiTask>['columns'] = [
    {
      title: '任务名称与属性',
      key: 'name',
      width: '28%',
      render: (_, item) => {
        const { source } = getUnifiedTaskContext(item)
        return (
          <div className="ai-task-list-name">
            <Tooltip title={item.task.name || '未命名任务'}>
              <Text ellipsis>{item.task.name || '未命名任务'}</Text>
            </Tooltip>
            <span className="ai-task-source-chip">{source}</span>
          </div>
        )
      },
    },
    {
      title: '生成状态',
      key: 'status',
      width: 112,
      render: (_, item) => (
        <div className="ai-task-list-tags">{renderLatestRunStatus(getUnifiedTaskContext(item).latestRun?.status)}</div>
      ),
    },
    {
      title: '所属迭代 / 需求',
      key: 'scope',
      ellipsis: true,
      render: (_, item) => {
        const { requirementName, sprintName } = getUnifiedTaskContext(item)
        return (
          <Tooltip title={`${sprintName} / ${requirementName}`}>
            <span className="ai-task-list-scope">
              <span className="ai-task-sprint-chip">{sprintName}</span>
              <Text ellipsis>{requirementName}</Text>
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: '来源文档',
      key: 'sourceDocument',
      width: 190,
      ellipsis: true,
      render: (_, item) => {
        const { requirement, requirementName } = getUnifiedTaskContext(item)
        const documentName = requirement?.documentFilename || requirementName
        return (
          <Tooltip title={documentName}>
            <span className="ai-task-source-document">
              <FileTextOutlined />
              <Text ellipsis>{documentName}</Text>
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: '创建时间',
      key: 'createdAt',
      width: 165,
      render: (_, item) => <Text className="ai-task-time-cell">{formatTime(pickCreatedAt(item.task))}</Text>,
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: 165,
      render: (_, item) => (
        <Text className="ai-task-time-cell">{formatTime(pickUpdatedAt(item.task) || pickCreatedAt(item.task))}</Text>
      ),
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
                <ProjectActionButton operation="run" iconOnly type="text" action="execute"
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
        {/* 工具栏卡片：左侧迭代与搜索，右侧刷新与新建任务 */}
        <section className="workbench-panel ai-testing-task-toolbar">
          <div className="panel-header ai-task-panel-header">
            <Space wrap size={10} className="ai-task-panel-filters">
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
              <div className="ai-task-search-field">
                <Input
                  ref={keywordInputRef}
                  className="ai-task-search-input"
                  allowClear
                  prefix={<SearchOutlined />}
                  suffix={<span className="ai-task-search-hint">⌘K</span>}
                  placeholder="搜索任务名称 / 所属需求"
                  value={keywordInput}
                  onChange={(event) => setKeywordInput(event.target.value)}
                />
              </div>
            </Space>
            <Space wrap size={10} className="ai-task-panel-tools">
              <Tooltip title="刷新当前任务列表">
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
              </Tooltip>
              <ProjectActionButton action="write"
                type="primary"
                className="action-btn-create"
                operation="create"
                disabled={!activeProjectId}
                onClick={openCreateTask}
              >
                新建任务
              </ProjectActionButton>
            </Space>
          </div>
        </section>

        {/* 表格卡片：状态筛选条 + 表格 + 页脚 */}
        <section className="workbench-panel workbench-board-panel ai-testing-task-panel">
          {projectsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(projectsQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {tasksQuery.error ? <Alert showIcon type="error" title={getErrorMessage(tasksQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {functionalTasksQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(functionalTasksQuery.error)} style={{ margin: '12px 18px 0' }} />
          ) : null}
          {uiTasksQuery.error ? <Alert showIcon type="error" title={getErrorMessage(uiTasksQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {analysisTasksQuery.error ? <Alert showIcon type="error" title={getErrorMessage(analysisTasksQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
          {codeRiskTasksQuery.error ? <Alert showIcon type="error" title={getErrorMessage(codeRiskTasksQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}

          <div className="ai-task-status-strip tp-quickbar">
            <div className="ai-task-status-strip-filters">
              <span className="ai-task-status-strip-label">状态筛选:</span>
              {AI_TASK_STATUS_FILTERS.map((filter) => (
                <button
                  key={filter.key}
                  type="button"
                  aria-pressed={statusFilter === filter.key}
                  className={`ai-task-status-chip${statusFilter === filter.key ? ' active' : ''}`}
                  onClick={() => {
                    setStatusFilter(filter.key)
                    setPage(1)
                  }}
                >
                  {filter.dot ? <span className={`ai-task-status-chip-dot ${filter.dot}`} aria-hidden="true" /> : null}
                  {filter.label} ({statusFilterCounts.get(filter.key) ?? 0})
                </button>
              ))}
            </div>
            <div className="ai-task-strip-actions">
              <span className="tp-selection">
                已勾选 <strong>{selectedTaskKeys.length}</strong> 项
              </span>
              {/* 代码风险分析任务没有删除接口，这个类型下不出现批量删除。 */}
              {deletableSelection ? (
                <Popconfirm
                  title={`确认删除选中的 ${selectedTasks.length} 个任务？`}
                  description="删除后无法恢复，请谨慎操作。"
                  okText="确认删除"
                  okButtonProps={{ danger: true }}
                  disabled={selectedTasks.length === 0}
                  onConfirm={() => batchDeleteTasksMutation.mutate(selectedTasks)}
                >
                  <ProjectActionButton
                    action="write"
                    size="small"
                    danger
                    className="action-btn-delete"
                    operation="delete"
                    disabled={selectedTasks.length === 0}
                    loading={batchDeleteTasksMutation.isPending}
                  >
                    批量删除{selectedTasks.length > 0 ? `（${selectedTasks.length}）` : ''}
                  </ProjectActionButton>
                </Popconfirm>
              ) : null}
            </div>
          </div>

          <div className="table-body-scroll ai-testing-card-scroll ai-task-table-scroll">
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
                <Empty description={hasListFilters ? '没有符合筛选条件的任务' : '当前类型下暂无任务'}>
                  {hasListFilters ? (
                    <ActionButton
                      operation="refresh"
                      onClick={() => {
                        setKeywordInput('')
                        setKeyword('')
                        setStatusFilter('all')
                        setPage(1)
                      }}
                    >
                      清空筛选条件
                    </ActionButton>
                  ) : (
                    <ActionButton type="primary" operation="create" onClick={openCreateTask}>
                      创建第一条任务
                    </ActionButton>
                  )}
                </Empty>
              </div>
            ) : (
              <Table<UnifiedAiTask>
                className="ai-task-list-table tp-list-table"
                columns={columns}
                dataSource={pagedTasks}
                rowKey={getUnifiedTaskKey}
                rowSelection={{
                  preserveSelectedRowKeys: true,
                  selectedRowKeys: selectedTaskKeys,
                  onChange: (keys) => setSelectedTaskKeys(keys.map(String)),
                  getCheckboxProps: (item) => ({
                    disabled: false,
                    'aria-label': `选择任务：${item.task.name || '未命名任务'}`,
                  }),
                }}
                pagination={false}
                onRow={(item) => ({
                  onClick: (event) => {
                    if ((event.target as HTMLElement).closest('.ant-table-selection-column')) return
                    navigate(getUnifiedTaskContext(item).detailPath)
                  },
                })}
              />
            )}
          </div>

          <div className="table-footer ai-task-list-footer">
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

  return <div className="workbench-page ai-testing-page tp-list-surface ai-testing-task-page tp-surface">{content}</div>
}
