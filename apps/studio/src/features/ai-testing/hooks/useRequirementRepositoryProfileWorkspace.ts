import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { listItems } from '@/services/api'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { RUN_HISTORY_POLL_INTERVAL } from '@/domain/runs/polling'
import { getErrorMessage } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { randomId } from '@/shared/utils/crypto'
import { generationChainApi } from '../api/generationChain.api'
import { generationCandidatesApi } from '../api/generationCandidates.api'
import { profileCandidatesApi } from '../api/profileCandidates.api'
import { repositoryProfileApi } from '../api/repositoryProfile.api'
import { isApiCaseGenerateTaskRunInProgress } from '../utils/taskStatus'
import { usePersonalLlmChoice } from './usePersonalLlmChoice'
import { usePersonalConnectionChoice } from '@/features/base-services/components/usePersonalConnectionChoice'
import type { RepositoryProfile, RepositoryProfileTaskRun, RepositoryProfileCandidateView } from '../types'

const LATEST_RUN_PAGE_SIZE = 1
const PROFILE_CANDIDATE_PAGE_SIZE = 20

function parseProfile(content: string): RepositoryProfile | null {
  try {
    const value: unknown = JSON.parse(content)
    if (!value || typeof value !== 'object') return null
    const profile = value as Partial<RepositoryProfile>
    return Array.isArray(profile.repositories) && typeof profile.overallSummary === 'string'
      ? profile as RepositoryProfile : null
  } catch { return null }
}

function getRunSortTime(run: RepositoryProfileTaskRun) {
  const time = new Date(run.createdAt || run.startedAt || run.updatedAt || '').getTime()
  return Number.isNaN(time) ? 0 : time
}

/**
 * Requirement-detail repository profile tab data source.
 *
 * Candidate results are separate from execution history; only an adopted candidate is current.
 */
export function useRequirementRepositoryProfileWorkspace(
  requirementId: string,
  projectId: string,
  active: boolean,
) {
  const client = useQueryClient()
  const [selectedCandidateId, setSelectedCandidateId] = useState<string>()
  const [candidatePage, setCandidatePage] = useState(1)
  const requestId = useRef<{ taskId: string; options: string; id: string } | undefined>(undefined)
  const reviewRequest = useRef<{ options: string; id: string } | undefined>(undefined)
  const selectAfterRunFromCandidateId = useRef<string | undefined>(undefined)

  const materialQuery = useQuery({
    queryKey: ['generationChain', requirementId, 'requirement_analysis', 'detail'],
    queryFn: () => generationChainApi.chain(requirementId, 'requirement_analysis'),
    enabled: active && Boolean(requirementId),
  })
  const materialCandidateMode = Boolean(materialQuery.data?.candidateMode)
  const currentMaterialQuery = useQuery({
    queryKey: ['candidateWorkflow', requirementId, 'requirement_analysis', 'extracting_text', 'current'],
    queryFn: () => generationCandidatesApi.current(requirementId, 'requirement_analysis', 'extracting_text'),
    enabled: active && Boolean(requirementId) && materialCandidateMode,
  })
  const currentMaterialAvailable = Boolean(currentMaterialQuery.data?.candidateId && !currentMaterialQuery.data.invalidatedAt)
  const personalLlm = usePersonalLlmChoice(projectId)
  const personalGitlab = usePersonalConnectionChoice('gitlab')

  const bindingsQuery = useQuery({
    queryKey: ['requirementSoftwareRepositories', requirementId],
    queryFn: () => interfaceLibraryApi.getRequirementSoftwareRepositories(requirementId),
    enabled: active && Boolean(requirementId),
  })
  const bindings = useMemo(
    () => listItems(bindingsQuery.data),
    [bindingsQuery.data],
  )
  const hasRunnableBindings = bindingsQuery.data
    ? bindings.some(binding => binding.branch.trim() && binding.baselineBranch.trim())
    : true

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

  const candidatesQuery = useQuery({
    queryKey: ['profileCandidates', requirementId, candidatePage],
    queryFn: () => profileCandidatesApi.list(requirementId, candidatePage, PROFILE_CANDIDATE_PAGE_SIZE),
    enabled: active && materialCandidateMode && Boolean(requirementId),
    refetchInterval: active ? RUN_HISTORY_POLL_INTERVAL : false,
  })
  const currentProfileQuery = useQuery({
    queryKey: ['profileCandidateCurrent', requirementId],
    queryFn: () => profileCandidatesApi.current(requirementId),
    enabled: active && materialCandidateMode && Boolean(candidatesQuery.data?.total),
  })
  const candidateDetail = useQuery({
    queryKey: ['profileCandidateDetail', requirementId, selectedCandidateId],
    queryFn: () => profileCandidatesApi.detail(requirementId, selectedCandidateId!),
    enabled: active && materialCandidateMode && Boolean(selectedCandidateId),
  })
  const candidateViews = useMemo<RepositoryProfileCandidateView[]>(() => {
    return (candidatesQuery.data?.items ?? []).map(candidate => {
        const content = candidateDetail.data && candidateDetail.data.candidateId === candidate.candidateId ? candidateDetail.data.content : ''
        return {
          candidateId: candidate.candidateId,
          label: `候选 ${candidate.candidateId.slice(0, 8)}`,
          sourceRunId: '',
          resultYaml: content,
          profile: parseProfile(content),
          createdAt: candidate.createdAt,
        }
      })
  }, [candidatesQuery.data, candidateDetail.data])
  const latestProfileView = candidateViews[0]
  const detailData = candidateDetail.data
  const selectedProfileView: RepositoryProfileCandidateView | undefined = candidateViews.find(candidate => candidate.candidateId === selectedCandidateId)
    ?? (materialCandidateMode && detailData && detailData.candidateId === selectedCandidateId ? {
      candidateId: detailData.candidateId, label: `候选 ${detailData.candidateId.slice(0, 8)}`,
      sourceRunId: '', resultYaml: detailData.content, profile: parseProfile(detailData.content),
      createdAt: detailData.createdAt,
    } : latestProfileView)
  const candidateViewsLoading = materialCandidateMode && (candidatesQuery.isPending || (Boolean(selectedCandidateId) && candidateDetail.isPending))
  const candidateViewsFetching = candidatesQuery.isFetching || candidateDetail.isFetching
  const candidateViewsError = candidatesQuery.error ?? candidateDetail.error

  useEffect(() => {
    if (!active) return
    const previousLatestId = selectAfterRunFromCandidateId.current
    if (previousLatestId !== undefined) {
      const latest = candidateViews[0]
      if (latest && latest.candidateId !== previousLatestId) {
        setSelectedCandidateId(latest.candidateId)
        selectAfterRunFromCandidateId.current = undefined
      }
      return
    }
    if (!candidateViews.length) {
      if (selectedCandidateId && selectedCandidateId !== currentProfileQuery.data?.candidateId) setSelectedCandidateId(undefined)
      return
    }
    if (materialCandidateMode && selectedCandidateId === currentProfileQuery.data?.candidateId) return
    if (selectedCandidateId && candidateViews.some(candidate => candidate.candidateId === selectedCandidateId)) {
      return
    }
    setSelectedCandidateId(candidateViews[0].candidateId)
  }, [active, candidateViews, selectedCandidateId, materialCandidateMode, currentProfileQuery.data?.candidateId])

  const refresh = useCallback(() => {
    void client.invalidateQueries({ queryKey: ['repositoryProfileTasks', projectId] })
    void client.invalidateQueries({ queryKey: ['repositoryProfileTaskRuns'] })
    void client.invalidateQueries({ queryKey: ['profileCandidates', requirementId] })
    void client.invalidateQueries({ queryKey: ['profileCandidateCurrent', requirementId] })
    void client.invalidateQueries({ queryKey: ['profileCandidateDetail', requirementId] })
    void client.invalidateQueries({ queryKey: ['generationChain', requirementId, 'ui', 'sourceOptions'] })
    void client.invalidateQueries({ queryKey: ['requirementSoftwareRepositories', requirementId] })
  }, [client, projectId, requirementId])

  function reviewId(options: unknown) {
    const serialized = JSON.stringify(options)
    if (reviewRequest.current?.options !== serialized) reviewRequest.current = { options: serialized, id: randomId() }
    return reviewRequest.current.id
  }
  const adopt = useMutation({
    mutationFn: async () => {
      const candidate = candidateDetail.data
      const current = currentProfileQuery.data
      if (!candidate || !candidate.currentAttemptId || !current || candidate.disposition !== 'available') throw new Error('候选或当前画像已变化，请刷新后重试')
      const body = { action: 'adopt' as const, candidateId: candidate.candidateId, expectedCandidateToken: candidate.candidateToken,
        expectedAttemptId: candidate.currentAttemptId, expectedCurrentToken: current.currentToken }
      return profileCandidatesApi.adopt(requirementId, { ...body, requestId: reviewId(body) })
    },
    onSuccess: () => { reviewRequest.current = undefined; refresh(); message.success('已采用当前画像') },
    onError: reason => { refresh(); message.error(getErrorMessage(reason)) },
  })
  const clearCurrent = useMutation({
    mutationFn: async () => {
      if (!currentProfileQuery.data?.candidateId) throw new Error('当前画像已变化，请刷新后重试')
      const body = { expectedCurrentToken: currentProfileQuery.data.currentToken }
      return profileCandidatesApi.clear(requirementId, { ...body, requestId: reviewId({ clear: body }) })
    },
    onSuccess: () => { reviewRequest.current = undefined; refresh(); message.success('已清空当前画像') },
    onError: reason => { refresh(); message.error(getErrorMessage(reason)) },
  })
  const dispose = useMutation({
    mutationFn: async (action: 'reject' | 'discard') => {
      const candidate = candidateDetail.data
      if (!candidate || candidate.isCurrent || candidate.disposition !== 'available') throw new Error('候选已变化，请刷新后重试')
      const body = { action, expectedCandidateToken: candidate.candidateToken }
      return profileCandidatesApi.dispose(requirementId, candidate.candidateId, { ...body, requestId: reviewId({ candidateId: candidate.candidateId, ...body }) })
    },
    onSuccess: () => { reviewRequest.current = undefined; refresh(); message.success('已处理画像候选') },
    onError: reason => { refresh(); message.error(getErrorMessage(reason)) },
  })

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
      })
      if (requestId.current?.taskId !== taskId || requestId.current.options !== options) {
        requestId.current = { taskId, options, id: randomId() }
      }
      return repositoryProfileApi.runRepositoryProfileTask(taskId, {
        llmConnectionId: connectionId,
        instruction: instruction || undefined,
        triggerType: 'manual',
        gitlabConnectionIds,
        requestId: requestId.current.id,
      })
    },
    onSuccess: () => {
      requestId.current = undefined
      selectAfterRunFromCandidateId.current = candidateViews[0]?.candidateId ?? ''
      refresh()
      message.success('已发起画像分析')
    },
    onError: reason => {
      if (getErrorMessage(reason) !== '已取消操作') message.error(getErrorMessage(reason))
    },
  })

  const busy = start.isPending || adopt.isPending || clearCurrent.isPending || dispose.isPending
  const runDisabledReason =
    materialQuery.isPending || (materialCandidateMode && currentMaterialQuery.isPending) || bindingsQuery.isPending || tasksQuery.isPending || candidateViewsLoading
      ? '正在读取运行信息，请稍候。'
      : materialQuery.error
        ? `材料读取失败：${getErrorMessage(materialQuery.error)}`
      : materialCandidateMode && currentMaterialQuery.error
        ? `当前材料读取失败：${getErrorMessage(currentMaterialQuery.error)}`
      : !materialCandidateMode || !currentMaterialAvailable
        ? '请先采用有效的材料整理结果，再进行仓库画像分析。'
        : !hasRunnableBindings
          ? bindings.length > 0
            ? '需求关联的软件仓库缺少工作分支或基线分支，请重新设置分支后再运行。'
            : '该需求未关联软件仓库，请先在需求列表完成「关联软件仓库」。'
          : busy
            ? '正在处理当前操作，请完成后再运行。'
            : runInProgress
              ? '当前画像运行尚未结束，请完成后再试。'
              : undefined

  return {
    busy,
    selectedCandidateId,
    setSelectedCandidateId,
    selectedProfileView,
    latestProfileView,
    candidateViews,
    candidateViewsLoading,
    candidateViewsFetching,
    candidateViewsError,
    latestRun,
    runsLoading,
    runsError,
    runInProgress,
    runDisabledReason,
    materialCandidateMode,
    currentMaterialAvailable,
    profileCandidateMode: materialCandidateMode,
    candidatePage,
    setCandidatePage,
    candidatePageSize: PROFILE_CANDIDATE_PAGE_SIZE,
    candidateTotal: candidatesQuery.data?.total ?? 0,
    candidateSummaries: candidatesQuery.data?.items ?? [],
    selectedCandidate: candidateDetail.data,
    currentProfile: currentProfileQuery.data,
    currentProfileError: currentProfileQuery.error,
    currentProfileLoading: currentProfileQuery.isPending && Boolean(candidatesQuery.data?.total),
    adopt,
    clearCurrent,
    dispose,
    materialLoading: materialQuery.isPending,
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
