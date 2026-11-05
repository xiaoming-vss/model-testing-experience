import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Select, Typography } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { listTotal } from '@/shared/api/request'
import { listItems } from '@/services/api'
import { aiTestingApi } from '../api/aiTesting.api'
import { generationChainApi } from '../api/generationChain.api'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { RUN_HISTORY_POLL_INTERVAL } from '@/domain/runs/polling'
import { usePersonalLlmChoice } from './usePersonalLlmChoice'
import { usePersonalConnectionChoice } from '@/features/base-services/components/usePersonalConnectionChoice'
import { isGitlabRepositoryBinding } from '@/features/base-services/utils/resourceBinding'
import { isApiCaseGenerateTaskRunInProgress } from '../utils/taskStatus'
import type { CodeRiskTaskRun } from '../types'

const { Text } = Typography

/** 单个任务的运行摘要一次取满；超出后仅计数准确，明细仍可在任务详情查看。 */
const RUNS_PAGE_SIZE = 100

function getRunSortTime(run: CodeRiskTaskRun) {
  const time = new Date(run.createdAt || run.startedAt || run.updatedAt || '').getTime()
  return Number.isNaN(time) ? 0 : time
}

/**
 * 需求详情「代码风险」页签的工作区数据源，与其他设计类页签同一交互形态：
 * 运行记录按需求聚合展示，首次运行自动创建绑定当前需求的任务，不提供新建任务表单。
 */
export function useRequirementCodeRiskWorkspace(requirementId: string, projectId: string, active: boolean) {
  const client = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selectedRunId, setSelectedRunId] = useState<string>()
  const [understandingVersionId, setUnderstandingVersionId] = useState('')
  const requestId = useRef<{ taskId: string; options: string; id: string } | undefined>(undefined)
  const understandingQuery = useQuery({
    queryKey: ['generationChain', requirementId, 'requirement_analysis', 'detail'],
    queryFn: () => generationChainApi.chain(requirementId, 'requirement_analysis'),
    enabled: active && Boolean(requirementId),
  })
  const understandingStage = understandingQuery.data?.stages.find(item => item.stage === 'feature_understanding')
  const understandingVersions = understandingStage?.versions ?? []
  const latestUnderstandingVersionId = understandingStage?.latestVersion?.versionId ?? understandingVersions[0]?.versionId
  useEffect(() => {
    if (understandingVersionId || !latestUnderstandingVersionId) return
    setUnderstandingVersionId(latestUnderstandingVersionId)
  }, [understandingVersionId, latestUnderstandingVersionId])
  const understandingRunOptions = {
    // 没有已审核版本时服务端会拒绝运行，这里提前禁用确认并说明原因。
    confirmDisabled: understandingQuery.isSuccess && !understandingVersions.length,
    render: () => <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <Text strong>需求理解版本</Text>
      <Text type="secondary">代码风险分析读取已审核的需求理解版本，默认使用最新版本。</Text>
      {understandingVersions.length ? <Select aria-label="需求理解版本" value={understandingVersionId || undefined}
        onChange={setUnderstandingVersionId}
        options={understandingVersions.map(version => ({
          value: version.versionId,
          label: version.versionId === latestUnderstandingVersionId ? `${version.label}（最新）` : version.label,
        }))} /> : understandingQuery.isPending
        ? <Text type="secondary">正在读取需求理解版本…</Text>
        : <Alert showIcon type="info" title="当前需求还没有审核通过的需求理解，请先完成需求分析并审核通过。" />}
    </div>,
  }
  const personalLlm = usePersonalLlmChoice(projectId, understandingRunOptions)
  const personalGitlab = usePersonalConnectionChoice('gitlab')

  const tasksQuery = useQuery({
    queryKey: ['codeRiskTasks', projectId],
    queryFn: () => aiTestingApi.getCodeRiskTasks(projectId),
    enabled: Boolean(projectId),
  })
  const requirementTasks = listItems(tasksQuery.data)
    .filter(task => task.requirementId === requirementId)
    .sort((left, right) => new Date(left.createdAt ?? 0).getTime() - new Date(right.createdAt ?? 0).getTime())
    .reverse()
  const bindingsQuery = useQuery({
    queryKey: ['requirementCodeBindings', requirementId],
    queryFn: () => baseServicesApi.getGitlabRequirementBindings(requirementId),
    enabled: Boolean(requirementId),
  })
  const hasRepoBindings = bindingsQuery.data ? listItems(bindingsQuery.data).filter(isGitlabRepositoryBinding).length > 0 : true

  const runsQueries = useQueries({
    queries: requirementTasks.map(task => ({
      queryKey: ['codeRiskTaskRuns', task.taskId, 1, RUNS_PAGE_SIZE],
      queryFn: () => aiTestingApi.getCodeRiskTaskRuns(task.taskId!, { page: 1, pageSize: RUNS_PAGE_SIZE }),
      enabled: Boolean(task.taskId),
      refetchInterval: active ? RUN_HISTORY_POLL_INTERVAL : false,
    })),
  })
  const runs = runsQueries.flatMap(query => listItems(query.data)).sort((left, right) => getRunSortTime(right) - getRunSortTime(left))
  const total = runsQueries.reduce((sum, query) => sum + listTotal(query.data), 0)
  const runsLoading = runsQueries.some(query => query.isPending)
  const runsFetching = runsQueries.some(query => query.isFetching)
  const runsError = runsQueries.find(query => query.error)?.error ?? tasksQuery.error
  const latestRun = runs[0]
  const runInProgress = isApiCaseGenerateTaskRunInProgress(latestRun?.status)

  useEffect(() => {
    const last = Math.max(1, Math.ceil(total / pageSize))
    if (total && page > last) setPage(last)
  }, [total, page, pageSize])

  const pagedRows = runs.slice((page - 1) * pageSize, page * pageSize)
  const refresh = useCallback(() => {
    void client.invalidateQueries({ queryKey: ['codeRiskTasks', projectId] })
    void client.invalidateQueries({ queryKey: ['requirementCodeBindings', requirementId] })
    void client.invalidateQueries({ queryKey: ['codeRiskTaskRuns'] })
    // 统一 AI 测试列表用的是项目级最新运行摘要，发起或刷新后一并失效。
    void client.invalidateQueries({ queryKey: ['codeRiskTaskLatestRuns'] })
  }, [client, projectId, requirementId])

  const start = useMutation({
    mutationFn: async () => {
      const { connectionId, instruction } = await personalLlm.chooseRun(false)
      const gitlabConnectionIds = await personalGitlab.forRequirement(projectId, requirementId)
      let taskId = requirementTasks[0]?.taskId
      if (!taskId) {
        const task = await aiTestingApi.createCodeRiskTask(projectId, { requirementId })
        if (!task.taskId) throw new Error('创建代码风险分析任务失败，请重试')
        taskId = task.taskId
        await client.invalidateQueries({ queryKey: ['codeRiskTasks', projectId] })
      }
      const options = JSON.stringify({
        connectionId,
        instruction,
        gitlabConnectionIds: Object.entries(gitlabConnectionIds).sort(([a], [b]) => a.localeCompare(b)),
        requirementUnderstandingVersionId: understandingVersionId,
      })
      if (requestId.current?.taskId !== taskId || requestId.current.options !== options) requestId.current = { taskId, options, id: crypto.randomUUID() }
      return aiTestingApi.runCodeRiskTask(taskId, {
        llmConnectionId: connectionId,
        instruction: instruction || undefined,
        triggerType: 'manual',
        gitlabConnectionIds,
        requirementUnderstandingVersionId: understandingVersionId || undefined,
        requestId: requestId.current.id,
      })
    },
    onSuccess: run => {
      requestId.current = undefined
      setSelectedRunId(run.runId)
      setPage(1)
      refresh()
      message.success('已发起分析')
    },
    onError: reason => { if (getErrorMessage(reason) !== '已取消操作') message.error(getErrorMessage(reason)) },
  })

  const remove = useMutation({
    mutationFn: (runId: string) => aiTestingApi.deleteCodeRiskRun(runId),
    onSuccess: (_data, runId) => {
      setSelectedRunId(previous => previous === runId ? undefined : previous)
      refresh()
      message.success('运行记录已删除')
    },
    onError: reason => message.error(getErrorMessage(reason)),
  })

  const busy = start.isPending || remove.isPending
  const runDisabledReason = tasksQuery.isPending || bindingsQuery.isPending ? '正在读取运行信息，请稍候。'
    : !hasRepoBindings ? '该需求未绑定代码仓库，请先在需求列表完成「代码绑定」。'
    : busy ? '正在处理当前操作，请完成后再运行。'
    : runInProgress ? '当前任务尚未结束，请完成当前运行后再试。'
    : undefined

  return {
    busy, page, pageSize, setPage, setPageSize,
    pagedRows, total, count: tasksQuery.isPending ? undefined : total, countError: Boolean(tasksQuery.error),
    selectedRunId, setSelectedRunId, runsLoading, runsFetching, runsError,
    runDisabledReason, start, remove, refresh, personalLlm, personalGitlab,
  }
}

export type RequirementCodeRiskWorkspace = ReturnType<typeof useRequirementCodeRiskWorkspace>
