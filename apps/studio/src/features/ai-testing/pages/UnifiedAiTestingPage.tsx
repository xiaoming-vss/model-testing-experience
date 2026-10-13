import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { ListPagination } from '@/shared/components/ListPagination'
import '@/shared/styles/list-table.css'
import '@/shared/styles/surface-tokens.css'
import { ActionButton } from '@/shared/components/ActionButton'
import { usePersonalConnectionChoice } from '@/features/base-services/components/usePersonalConnectionChoice'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import {
  EyeOutlined,
  FileTextOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  Space,
  Table,
  Tooltip,
  Typography,
} from 'antd'
import type { InputRef, TableProps } from 'antd'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LlmConnectionSelectModal } from '../components/LlmConnectionSelectModal'
import { CodeRiskTaskDrawer, type CodeRiskTaskFormValues } from '../components/CodeRiskTaskDrawer'
import type { CodeRiskTask, CodeRiskTaskRun, CreateCodeRiskTaskPayload } from '../types'
import { getApiCaseGenerateTaskRunStatusMeta, isApiCaseGenerateTaskRunInProgress, isRunnableApiCaseGenerateTaskRun } from '../utils/taskStatus'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-list-v2.css'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage, normalizeRequirementId, normalizeSprintId, pickCreatedAt, pickUpdatedAt } from '@/utils/format'

const { Text } = Typography

function getCodeRiskTaskId(task: CodeRiskTask) {
  return task.taskId ?? ''
}

function getTaskTime(item: CodeRiskTask) {
  const time = new Date(item.updatedAt || item.createdAt || '').getTime()
  return Number.isNaN(time) ? 0 : time
}

function getLatestRun(runs?: CodeRiskTaskRun[]) {
  const time = (run: CodeRiskTaskRun) => {
    const value = new Date(run.createdAt || run.startedAt || run.updatedAt || '').getTime()
    return Number.isNaN(value) ? 0 : value
  }
  return [...(runs ?? [])].sort((left, right) => time(right) - time(left))[0]
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
function statusFilterBucket(status?: CodeRiskTaskRun['status']): AiTaskStatusFilter | null {
  if (status === 'success') return 'success'
  if (status === 'failed' || status === 'error') return 'failed'
  if (status === 'waiting_review') return 'waiting_review'
  if (isApiCaseGenerateTaskRunInProgress(status)) return 'in_progress'
  return null
}

function renderLatestRunStatus(status?: CodeRiskTaskRun['status']) {
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
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const personalGitlab = usePersonalConnectionChoice('gitlab')
  const { activeProjectId, projectsQuery } = useActiveProject()
  const { activeSprintId: globalSprintId } = useActiveSprint()
  const [codeRiskLlmSelectTaskId, setCodeRiskLlmSelectTaskId] = useState<string | null>(null)
  const [codeRiskDrawerOpen, setCodeRiskDrawerOpen] = useState(false)
  const [codeRiskDrawerSprintId, setCodeRiskDrawerSprintId] = useState<string | undefined>(undefined)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<AiTaskStatusFilter>('all')
  const keywordInputRef = useRef<InputRef>(null)
  const [codeRiskForm] = Form.useForm<CodeRiskTaskFormValues>()

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
  const allRequirementsQuery = useQuery({
    queryKey: ['requirementsPool', 'aiTesting', activeProjectId, sprintOptions.map((item) => item.value).join(',')],
    queryFn: async () => {
      if (!sprintsQuery.data || sprintsQuery.data.length === 0) return []
      const groups = await Promise.all(sprintsQuery.data.map((sprint) => api.getRequirements(normalizeSprintId(sprint))))
      return groups.flat()
    },
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })
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

  const tasks = useMemo(
    () => listItems(codeRiskTasksQuery.data)
      .filter((task) => !globalSprintId || task.sprintId === globalSprintId)
      .sort((left, right) => getTaskTime(right) - getTaskTime(left)),
    [codeRiskTasksQuery.data, globalSprintId],
  )
  const keywordTasks = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    if (!text) return tasks
    return tasks.filter((item) => {
      const { requirementId, sprintId, name } = item
      const fields = [
        name,
        sprintId ? sprintNameMap.get(sprintId) : undefined,
        requirementId ? requirementNameMap.get(requirementId) : undefined,
        '需求代码',
      ]
      return fields.some((field) => (field ?? '').toLowerCase().includes(text))
    })
  }, [keyword, tasks, requirementNameMap, sprintNameMap])
  const codeRiskTaskRunQueries = useQueries({
    queries: keywordTasks.map((task) => {
      const taskId = getCodeRiskTaskId(task)
      return {
        queryKey: ['codeRiskTaskRuns', taskId],
        queryFn: () => api.getCodeRiskTaskRuns(taskId),
        enabled: Boolean(taskId),
      }
    }),
  })
  const latestCodeRiskRunMap = useMemo(() => {
    const entries = keywordTasks.map((task, index) => [
      getCodeRiskTaskId(task),
      {
        isLoading: codeRiskTaskRunQueries[index]?.isLoading ?? false,
        latestRun: getLatestRun(codeRiskTaskRunQueries[index]?.data),
      },
    ] as const)
    return new Map(entries)
  }, [codeRiskTaskRunQueries, keywordTasks])

  /** 一条任务的最新运行状态，供状态档位计数与过滤共用。 */
  const latestRunStatusOf = useCallback(
    (task: CodeRiskTask) => latestCodeRiskRunMap.get(getCodeRiskTaskId(task))?.latestRun?.status,
    [latestCodeRiskRunMap],
  )

  /** 状态档位的计数与下面的过滤都基于同一份「当前迭代 + 关键词」集合。 */
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
  async function refreshActiveTaskList() {
    await Promise.all([
      codeRiskTasksQuery.refetch(),
      queryClient.refetchQueries({ queryKey: ['codeRiskTaskRuns'], type: 'active' }),
    ])
  }

  useEffect(() => {
    setPage(1)
  }, [activeProjectId, globalSprintId])

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

  const createCodeRiskTaskMutation = useMutation({
    mutationFn: (values: CreateCodeRiskTaskPayload) => api.createCodeRiskTask(activeProjectId!, values),
    onSuccess: () => {
      message.success('代码风险分析任务已创建')
      closeCodeRiskDrawer()
      queryClient.invalidateQueries({ queryKey: ['codeRiskTasks', activeProjectId] })
    },
  })

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

  function getTaskContext(task: CodeRiskTask) {
    const taskId = getCodeRiskTaskId(task)
    const runState = latestCodeRiskRunMap.get(taskId)
    return {
      requirement: task.requirementId ? requirementMap.get(task.requirementId) : undefined,
      requirementName: requirementNameMap.get(task.requirementId ?? '') ?? task.requirementId ?? '-',
      sprintName: sprintNameMap.get(task.sprintId ?? '') ?? task.sprintId ?? '-',
      detailPath: `/ai-testing/code-risk-tasks/${taskId}`,
      latestRun: runState?.latestRun,
      runState,
      runnableTask: !runState?.isLoading && isRunnableApiCaseGenerateTaskRun(runState?.latestRun?.status),
    }
  }

  const columns: TableProps<CodeRiskTask>['columns'] = [
    {
      title: '任务名称与属性',
      key: 'name',
      width: '28%',
      render: (_, item) => {
        return (
          <div className="tp-list-name ai-task-list-name">
            <Tooltip title={item.name || '未命名任务'}>
              <Text ellipsis>{item.name || '未命名任务'}</Text>
            </Tooltip>
            <span className="ai-task-source-chip">需求代码</span>
          </div>
        )
      },
    },
    {
      title: '生成状态',
      key: 'status',
      width: 112,
      render: (_, item) => (
        <div className="ai-task-list-tags">{renderLatestRunStatus(getTaskContext(item).latestRun?.status)}</div>
      ),
    },
    {
      title: '所属迭代 / 需求',
      key: 'scope',
      ellipsis: true,
      render: (_, item) => {
        const { requirementName, sprintName } = getTaskContext(item)
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
        const { requirement, requirementName } = getTaskContext(item)
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
      render: (_, item) => <Text className="ai-task-time-cell">{formatTime(pickCreatedAt(item))}</Text>,
    },
    {
      title: '最近更新',
      key: 'updatedAt',
      width: 165,
      render: (_, item) => (
        <Text className="ai-task-time-cell">{formatTime(pickUpdatedAt(item) || pickCreatedAt(item))}</Text>
      ),
    },
    {
      title: <span className="tp-actions-col-title" style={{ width: 62 }}>操作</span>,
      key: 'actions',
      width: 138,
      align: 'right',
      render: (_, item) => {
        const { detailPath, runState, runnableTask } = getTaskContext(item)
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
                  onClick={() => handleRunCodeRiskTask(item)}
                >
                  运行
                </ProjectActionButton>
              </span>
            </Tooltip>
            <Button
              icon={<EyeOutlined />}
              type="text"
              size="small"
              shape="circle"
              className="app-action app-action-icon app-action-read"
              aria-label="查看详情"
              onClick={() => navigate(detailPath)}
            />
          </Space>
        )
      },
    },
  ]

  const content = (
    <>
      <div className="workbench-tabs">
        <section className="workbench-panel workbench-board-panel ai-testing-task-panel tp-board tp-list-panel">
        <section className="ai-testing-task-toolbar tp-list-toolbar">
          <div className="panel-header ai-task-panel-header">
            <Space wrap size={8} className="ai-task-panel-filters">
              <h1 className="tp-list-title">代码风险分析</h1>
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
            <Space wrap size={8} className="ai-task-panel-tools tp-refresh-actions">
              <Tooltip title="刷新当前任务列表">
                <ActionButton
                  type="text"
                  className="ai-task-refresh-button"
                  operation="refresh"
                  loading={codeRiskTasksQuery.isFetching}
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
                onClick={openCodeRiskDrawer}
              >
                新建任务
              </ProjectActionButton>
            </Space>
          </div>
        </section>


          {projectsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(projectsQuery.error)} style={{ margin: '12px 18px 0' }} /> : null}
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
          </div>

          <div className="table-body-scroll ai-testing-card-scroll ai-task-table-scroll tp-list-scroll">
            {!activeProjectId ? (
              <div className="sprint-card-loading ai-testing-empty-shell">
                <Empty description="请先选择项目" />
              </div>
            ) : codeRiskTasksQuery.isLoading ? (
              <div className="sprint-card-loading ai-testing-empty-shell">
                <Empty description="任务加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </div>
            ) : filteredTasks.length === 0 ? (
              <div className="ai-testing-empty-shell">
                <Empty description={hasListFilters ? '没有符合筛选条件的任务' : '暂无代码风险分析任务'}>
                  {hasListFilters ? (
                    <Button
                      onClick={() => {
                        setKeywordInput('')
                        setKeyword('')
                        setStatusFilter('all')
                        setPage(1)
                      }}
                    >
                      清空筛选条件
                    </Button>
                  ) : (
                    <ActionButton type="primary" operation="create" onClick={openCodeRiskDrawer}>
                      创建第一条任务
                    </ActionButton>
                  )}
                </Empty>
              </div>
            ) : (
              <Table<CodeRiskTask>
                className="ai-task-list-table tp-list-table"
                columns={columns}
                dataSource={pagedTasks}
                rowKey={getCodeRiskTaskId}
                pagination={false}
                onRow={(item) => ({
                  onClick: () => {
                    navigate(getTaskContext(item).detailPath)
                  },
                })}
              />
            )}
          </div>

          <div className="table-footer ai-task-list-footer">
            <ListPagination loading={codeRiskTasksQuery.isFetching || codeRiskTasksQuery.isError}
              current={page}
              pageSize={pageSize}
              total={filteredTasks.length}
              onChange={(nextPage, nextPageSize) => {
                setPage(nextPage)
                setPageSize(nextPageSize)
              }}
            />
          </div>
        </section>
      </div>

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
    </>
  )

  if (embedded) return content

  return <div className="workbench-page ai-testing-page tp-list-surface ai-testing-task-page tp-surface">{content}</div>
}
