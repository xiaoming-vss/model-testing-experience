import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { listItems } from '@/services/api'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import { isGitlabRepositoryBinding } from '@/features/base-services/utils/resourceBinding'
import { RUN_HISTORY_POLL_INTERVAL } from '@/domain/runs/polling'
import { getErrorMessage } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { randomId } from '@/shared/utils/crypto'
import { generationChainApi } from '../api/generationChain.api'
import { repositoryProfileApi } from '../api/repositoryProfile.api'
import { isApiCaseGenerateTaskRunInProgress } from '../utils/taskStatus'
import { usePersonalLlmChoice } from './usePersonalLlmChoice'
import { usePersonalConnectionChoice } from '@/features/base-services/components/usePersonalConnectionChoice'
import type { RepositoryProfileTaskRun, RepositoryProfileVersion } from '../types'

const LATEST_RUN_PAGE_SIZE = 1

function getRunSortTime(run: RepositoryProfileTaskRun) {
  const time = new Date(run.createdAt || run.startedAt || run.updatedAt || '').getTime()
  return Number.isNaN(time) ? 0 : time
}

function getVersionSortTime(version: RepositoryProfileVersion) {
  const time = new Date(version.createdAt || '').getTime()
  return Number.isNaN(time) ? 0 : time
}

/**
 * Requirement-detail repository profile tab data source.
 *
 * Successful profile runs are exposed as immutable versions; failed or running
 * runs only contribute the latest execution state and never consume a version.
 */
export function useRequirementRepositoryProfileWorkspace(
  requirementId: string,
  projectId: string,
  active: boolean,
) {
  const client = useQueryClient()
  const [materialVersionId, setMaterialVersionId] = useState('')
  const [selectedVersionId, setSelectedVersionId] = useState<string>()
  const requestId = useRef<{ taskId: string; options: string; id: string } | undefined>(undefined)
  const selectAfterRunFromVersionId = useRef<string | undefined>(undefined)

  const materialQuery = useQuery({
    queryKey: ['generationChain', requirementId, 'requirement_analysis', 'detail'],
    queryFn: () => generationChainApi.chain(requirementId, 'requirement_analysis'),
    enabled: active && Boolean(requirementId),
  })
  const materialStage = materialQuery.data?.stages.find(
    item => item.stage === 'extracting_text',
  )
  const materialVersions = useMemo(
    () => materialStage?.versions ?? [],
    [materialStage],
  )
  const latestMaterialVersionId =
    materialStage?.latestVersion?.versionId ?? materialVersions[0]?.versionId

  useEffect(() => {
    if (!active) return
    if (!materialVersions.length) {
      if (materialVersionId) setMaterialVersionId('')
      return
    }
    if (materialVersions.some(item => item.versionId === materialVersionId)) return
    setMaterialVersionId(latestMaterialVersionId ?? materialVersions[0].versionId)
  }, [
    active,
    materialVersionId,
    materialVersions,
    latestMaterialVersionId,
  ])

  const personalLlm = usePersonalLlmChoice(projectId)
  const personalGitlab = usePersonalConnectionChoice('gitlab')

  const bindingsQuery = useQuery({
    queryKey: ['requirementCodeBindings', requirementId],
    queryFn: () => baseServicesApi.getGitlabRequirementBindings(requirementId),
    enabled: active && Boolean(requirementId),
  })
  const bindings = useMemo(
    () => listItems(bindingsQuery.data).filter(isGitlabRepositoryBinding),
    [bindingsQuery.data],
  )
  const hasRepoBindings = bindingsQuery.data ? bindings.length > 0 : true

  const tasksQuery = useQuery({
    queryKey: ['repositoryProfileTasks', projectId, requirementId],
    queryFn: () =>
      repositoryProfileApi.getRepositoryProfileTasks(projectId, {
        requirementId,
        page: 1,
        pageSize: 100,
      }),
    enabled: active && Boolean(projectId),
  })
  // Requirement-scoped task counts are small; the server filter avoids project-wide reads.
  const requirementTasks = useMemo(
    () =>
      listItems(tasksQuery.data)
        .sort(
          (left, right) =>
            new Date(left.createdAt ?? 0).getTime() -
            new Date(right.createdAt ?? 0).getTime(),
        )
        .reverse(),
    [tasksQuery.data],
  )

  const runsQueries = useQueries({
    queries: requirementTasks.map(task => ({
      queryKey: ['repositoryProfileTaskRuns', task.taskId, 1, LATEST_RUN_PAGE_SIZE],
      queryFn: () =>
        repositoryProfileApi.getRepositoryProfileTaskRuns(task.taskId!, {
          page: 1,
          pageSize: LATEST_RUN_PAGE_SIZE,
        }),
      enabled: active && Boolean(task.taskId),
      refetchInterval: active ? RUN_HISTORY_POLL_INTERVAL : false,
    })),
  })
  const latestRun = useMemo(
    () =>
      runsQueries
        .flatMap(query => listItems(query.data))
        .sort((left, right) => getRunSortTime(right) - getRunSortTime(left))[0],
    [runsQueries],
  )
  const runsLoading = runsQueries.some(query => query.isPending)
  const runsError = runsQueries.find(query => query.error)?.error ?? tasksQuery.error
  const runInProgress = isApiCaseGenerateTaskRunInProgress(latestRun?.status)

  const versionsQueries = useQueries({
    queries: requirementTasks.map(task => ({
      queryKey: ['repositoryProfileVersions', task.taskId],
      queryFn: () => repositoryProfileApi.getRepositoryProfileVersions(task.taskId!),
      enabled: active && Boolean(task.taskId),
      refetchInterval: active ? RUN_HISTORY_POLL_INTERVAL : false,
    })),
  })
  const versions = useMemo(() => {
    const seen = new Set<string>()
    const merged: RepositoryProfileVersion[] = []
    for (const query of versionsQueries) {
      for (const version of listItems(query.data)) {
        if (seen.has(version.versionId)) continue
        seen.add(version.versionId)
        merged.push(version)
      }
    }
    return merged.sort(
      (left, right) =>
        right.versionNo - left.versionNo ||
        getVersionSortTime(right) - getVersionSortTime(left),
    )
  }, [versionsQueries])
  const latestVersion = versions[0]
  const selectedVersion = versions.find(version => version.versionId === selectedVersionId)
    ?? latestVersion
  const versionsLoading = versionsQueries.some(query => query.isPending)
  const versionsFetching = versionsQueries.some(query => query.isFetching)
  const versionsError = versionsQueries.find(query => query.error)?.error

  useEffect(() => {
    if (!active) return
    const previousLatestId = selectAfterRunFromVersionId.current
    if (previousLatestId !== undefined) {
      const latest = versions[0]
      if (latest && latest.versionId !== previousLatestId) {
        setSelectedVersionId(latest.versionId)
        selectAfterRunFromVersionId.current = undefined
      }
      return
    }
    if (!versions.length) {
      if (selectedVersionId) setSelectedVersionId(undefined)
      return
    }
    if (selectedVersionId && versions.some(version => version.versionId === selectedVersionId)) {
      return
    }
    setSelectedVersionId(versions[0].versionId)
  }, [active, versions, selectedVersionId])

  const refresh = useCallback(() => {
    void client.invalidateQueries({ queryKey: ['repositoryProfileTasks', projectId] })
    void client.invalidateQueries({ queryKey: ['repositoryProfileTaskRuns'] })
    void client.invalidateQueries({ queryKey: ['repositoryProfileVersions'] })
    void client.invalidateQueries({ queryKey: ['requirementCodeBindings', requirementId] })
  }, [client, projectId, requirementId])

  const start = useMutation({
    mutationFn: async () => {
      const { connectionId, instruction } = await personalLlm.chooseRun(false)
      const gitlabConnectionIds = await personalGitlab.forRequirement(projectId, requirementId)
      let taskId = requirementTasks[0]?.taskId
      if (!taskId) {
        const task = await repositoryProfileApi.createRepositoryProfileTask(projectId, {
          requirementId,
        })
        if (!task.taskId) throw new Error('创建仓库画像任务失败，请重试')
        taskId = task.taskId
        await client.invalidateQueries({ queryKey: ['repositoryProfileTasks', projectId] })
      }
      const options = JSON.stringify({
        connectionId,
        instruction,
        gitlabConnectionIds: Object.entries(gitlabConnectionIds).sort(([a], [b]) =>
          a.localeCompare(b),
        ),
        requirementMaterialVersionId: materialVersionId,
      })
      if (requestId.current?.taskId !== taskId || requestId.current.options !== options) {
        requestId.current = { taskId, options, id: randomId() }
      }
      return repositoryProfileApi.runRepositoryProfileTask(taskId, {
        llmConnectionId: connectionId,
        instruction: instruction || undefined,
        triggerType: 'manual',
        gitlabConnectionIds,
        requirementMaterialVersionId: materialVersionId || undefined,
        requestId: requestId.current.id,
      })
    },
    onSuccess: () => {
      requestId.current = undefined
      selectAfterRunFromVersionId.current = versions[0]?.versionId ?? ''
      refresh()
      message.success('已发起画像分析')
    },
    onError: reason => {
      if (getErrorMessage(reason) !== '已取消操作') message.error(getErrorMessage(reason))
    },
  })

  const busy = start.isPending
  const runDisabledReason =
    materialQuery.isPending || bindingsQuery.isPending || tasksQuery.isPending || versionsLoading
      ? '正在读取运行信息，请稍候。'
      : !materialVersions.length
        ? '请先审核通过材料整理，再进行仓库画像分析。'
        : !hasRepoBindings
          ? '该需求未绑定代码仓库，请先在需求列表完成「代码绑定」。'
          : busy
            ? '正在处理当前操作，请完成后再运行。'
            : runInProgress
              ? '当前画像运行尚未结束，请完成后再试。'
              : undefined

  return {
    busy,
    selectedVersionId,
    setSelectedVersionId,
    selectedVersion,
    latestVersion,
    versions,
    versionsLoading,
    versionsFetching,
    versionsError,
    latestRun,
    runsLoading,
    runsError,
    runInProgress,
    runDisabledReason,
    materialVersions,
    latestMaterialVersionId,
    materialVersionId,
    setMaterialVersionId,
    materialLoading: materialQuery.isPending,
    hasRepoBindings,
    bindings,
    bindingsLoading: bindingsQuery.isPending,
    start,
    refresh,
    personalLlm,
    personalGitlab,
  }
}

export type RequirementRepositoryProfileWorkspace = ReturnType<
  typeof useRequirementRepositoryProfileWorkspace
>
