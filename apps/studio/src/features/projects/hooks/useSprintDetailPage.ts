import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs, { type Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useLocalDate } from '@/domain/projects/hooks/useLocalDate'
import { useSprintBoundaryRefresh } from '@/domain/projects/hooks/useSprintBoundaryRefresh'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { normalizeDailyMetrics } from '../utils/sprintMetrics'
import { useQueryErrorToast } from './useQueryErrorToast'
import { useSprintReports } from './useSprintReports'

export function useSprintDetailPage() {
  const { projectId: routeProjectId = '', sprintId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [historyDateRange, setHistoryDateRange] = useState<[Dayjs, Dayjs]>(() => [dayjs().subtract(6, 'day'), dayjs()])

  const sprintQuery = useQuery({
    queryKey: ['sprint', sprintId],
    queryFn: () => api.getSprint(sprintId),
    enabled: Boolean(sprintId),
  })
  const projectId = sprintQuery.data?.projectId || sprintQuery.data?.project_id || ''
  const projectMismatch = Boolean(routeProjectId && projectId && routeProjectId !== projectId)
  const projectScopeError = sprintQuery.error ?? (projectMismatch
    ? new Error('迭代所属项目与访问路径不一致')
    : sprintQuery.isSuccess && !projectId ? new Error('无法确认迭代所属项目') : undefined)
  const sprintForBoundaryRefresh = useMemo(() => (sprintQuery.data ? [sprintQuery.data] : []), [sprintQuery.data])
  useSprintBoundaryRefresh({
    sprints: sprintForBoundaryRefresh,
    enabled: Boolean(sprintId),
    refresh: sprintQuery.refetch,
  })
  const metricsRange = useMemo(() => {
    const [start, end] = historyDateRange
    const startDate = start.format('YYYY-MM-DD')
    const endDate = end.format('YYYY-MM-DD')
    return { startDate, endDate }
  }, [historyDateRange])
  const todayDate = useLocalDate()
  const currentMetricsQuery = useQuery({
    queryKey: ['sprintDailyMetricsByDate', sprintId, todayDate],
    queryFn: () => api.getSprintDailyMetricsByDate(sprintId, todayDate),
    enabled: Boolean(sprintId && projectId && !projectScopeError),
  })
  const historyMetricsQuery = useQuery({
    queryKey: ['sprintDailyMetrics', sprintId, metricsRange.startDate, metricsRange.endDate],
    queryFn: () => api.getSprintDailyMetrics(sprintId, metricsRange),
    enabled: Boolean(sprintId && projectId && !projectScopeError),
  })

  const generateMetricsMutation = useMutation({
    mutationFn: async () => {
      return api.generateSprintDailyMetrics(sprintId, todayDate)
    },
    onSuccess: () => {
      message.success('已生成最新统计快照')
      queryClient.invalidateQueries({ queryKey: ['sprintDailyMetricsByDate', sprintId, todayDate] })
      queryClient.invalidateQueries({ queryKey: ['sprintDailyMetrics', sprintId] })
    },
    onError: (error) => {
      const content = getErrorMessage(error)
      if (content === '已取消操作' || content === '页面已关闭') return
      message.error(content)
    },
  })

  const sprintName = sprintQuery.data?.name ?? '迭代详情'
  const latestMetrics = normalizeDailyMetrics(currentMetricsQuery.data)
  const historyMetrics = listItems(historyMetricsQuery.data).map(normalizeDailyMetrics)
  useQueryErrorToast(currentMetricsQuery.error, `sprint-metrics-${sprintId}`)
  useQueryErrorToast(historyMetricsQuery.error, `sprint-history-${sprintId}`)

  const reports = useSprintReports({
    projectId,
    sprintId,
    todayDate,
    metricsLoading: currentMetricsQuery.isLoading,
    metricsError: currentMetricsQuery.error,
    metricsHasData: Boolean(currentMetricsQuery.data),
  })

  return {
    routeProjectId,
    sprintId,
    navigate,
    sprintQuery,
    projectId,
    projectScopeError,
    historyDateRange,
    setHistoryDateRange,
    todayDate,
    currentMetricsQuery,
    historyMetricsQuery,
    generateMetricsMutation,
    sprintName,
    latestMetrics,
    historyMetrics,
    ...reports,
  } as const
}

export type SprintDetailPageModel = ReturnType<typeof useSprintDetailPage>
