import { getRunEventFallbackInterval, getRunPollingInterval, RUN_HISTORY_POLL_INTERVAL } from '@/domain/runs/polling'
import { useRunReportRefresh } from '@/domain/runs/useRunReportRefresh'
import { useRunEvents } from '@/domain/runs/useRunEvents'
import { refreshRunQuery } from '@/domain/runs/refreshRunQuery'
import { DebugStreamUnavailable, startDebugStream } from '@/domain/runs/startDebugStream'
import {
  type CollectionReportView,
  type RunResultView
} from '@/features/api-automation/config/collectionConfig'
import {
  getCollectionRunItemKey
} from '@/features/api-automation/utils/apiCaseEditor'
import { getApiCaseRunId, isApiRunPollingStatus, isApiRunTerminalStatus } from '@/features/api-automation/utils/detailView'
import {
  api,
  type ApiCaseRunResult,
  type ApiCollectionRunSummary
} from '@/services/api'
import { message } from '@/shared/utils/feedback'
import {
  getErrorMessage
} from '@/utils/format'
import { listItems, listTotal } from '@/shared/api/request'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'

const RUN_HISTORY_PAGE_SIZE = 20

type Options = {
  collectionId: string
}

export function useApiExecution({ collectionId }: Options) {
  const queryClient = useQueryClient()
  const [runResult, setRunResult] = useState<ApiCaseRunResult | null>(null)

  const [activeApiCaseRunId, setActiveApiCaseRunId] = useState('')
  const [liveApiCaseRunId, setLiveApiCaseRunId] = useState('')
  const debugStreamRef = useRef<{ abort: () => void } | null>(null)
  useEffect(() => () => { debugStreamRef.current?.abort() }, [])

  const [runResultView, setRunResultView] = useState<RunResultView>('response')

  const [collectionRunReportOpen, setCollectionRunReportOpen] = useState(false)

  const [collectionRunHistoryOpen, setCollectionRunHistoryOpen] = useState(false)

  const [selectedCollectionRunId, setSelectedCollectionRunId] = useState('')

  const [activePollingCollectionRunId, setActivePollingCollectionRunId] = useState('')

  const [loadingCollectionRunHistoryId, setLoadingCollectionRunHistoryId] = useState('')

  const [refreshingCollectionRunReport, setRefreshingCollectionRunReport] = useState(false)

  const [collectionRunReportView, setCollectionRunReportView] = useState<CollectionReportView>('items')

  const [expandedCollectionRunItemIds, setExpandedCollectionRunItemIds] = useState<string[]>([])

  const [collectionRunItemViews, setCollectionRunItemViews] = useState<Record<string, RunResultView>>({})

  const previousApiCaseRunStatusRef = useRef<ApiCaseRunResult['status'] | ''>('')

  const previousActiveRunStatusRef = useRef<ApiCollectionRunSummary['status'] | ''>('')

  const initializedReportRef = useRef('')

  const caseEventsConnected = useRunEvents('api-case', activeApiCaseRunId, Boolean(activeApiCaseRunId) && activeApiCaseRunId !== liveApiCaseRunId, () => {
    void refreshRunQuery(queryClient, ['apiCaseRun', activeApiCaseRunId])
  })
  const activeCollectionEventsConnected = useRunEvents('api-collection', activePollingCollectionRunId, Boolean(activePollingCollectionRunId), () => {
    void refreshRunQuery(queryClient, ['apiCollectionRun', activePollingCollectionRunId])
    void refreshRunQuery(queryClient, ['apiCollectionRunReport', activePollingCollectionRunId])
  })
  const reportStatus = queryClient.getQueryData<ApiCollectionRunSummary>(['apiCollectionRunReport', selectedCollectionRunId])?.status
  const reportEventsConnected = useRunEvents('api-collection', selectedCollectionRunId,
    collectionRunReportOpen && selectedCollectionRunId !== activePollingCollectionRunId && Boolean(selectedCollectionRunId) && getRunPollingInterval(reportStatus) !== false, () => {
      void refreshRunQuery(queryClient, ['apiCollectionRunReport', selectedCollectionRunId])
    })

  const activeApiCaseRunQuery = useQuery({
    queryKey: ['apiCaseRun', activeApiCaseRunId],
    queryFn: ({ signal }) => api.getApiCaseRun(activeApiCaseRunId, signal),
    enabled: Boolean(activeApiCaseRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as ApiCaseRunResult | undefined
      return (caseEventsConnected || activeApiCaseRunId === liveApiCaseRunId) ? false : getRunEventFallbackInterval(data?.status)
    },
  })

  const collectionRunHistoryQuery = useInfiniteQuery({
    queryKey: ['apiCollectionRuns', collectionId],
    queryFn: ({ pageParam }) =>
      api.getApiCollectionRuns(collectionId, { page: pageParam, pageSize: RUN_HISTORY_PAGE_SIZE }),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, page) => sum + listItems(page).length, 0)
      return loaded < listTotal(lastPage) ? allPages.length + 1 : undefined
    },
    enabled: Boolean(collectionId),
    refetchOnWindowFocus: false,
    refetchInterval: collectionRunHistoryOpen ? RUN_HISTORY_POLL_INTERVAL : false,
  })
  const collectionRunHistory = useMemo(
    () => collectionRunHistoryQuery.data?.pages.flatMap((page) => listItems(page)) ?? [],
    [collectionRunHistoryQuery.data],
  )
  const collectionRunHistoryTotal = collectionRunHistoryQuery.data?.pages[0]
    ? listTotal(collectionRunHistoryQuery.data.pages[0])
    : 0

  const refetchHistory = collectionRunHistoryQuery.refetch
  useEffect(() => {
    if (collectionRunHistoryOpen) void refetchHistory({ cancelRefetch: false })
  }, [collectionRunHistoryOpen, refetchHistory])

  const activeCollectionRunQuery = useQuery({
    queryKey: ['apiCollectionRun', activePollingCollectionRunId],
    queryFn: ({ signal }) => api.getApiCollectionRun(activePollingCollectionRunId, signal),
    enabled: Boolean(activePollingCollectionRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as ApiCollectionRunSummary | undefined
      return activeCollectionEventsConnected ? false : getRunEventFallbackInterval(data?.status)
    },
  })

  const collectionRunReportQuery = useQuery({
    queryKey: ['apiCollectionRunReport', selectedCollectionRunId],
    queryFn: ({ signal }) => api.getApiCollectionRunReport(selectedCollectionRunId, signal),
    enabled: collectionRunReportOpen && Boolean(selectedCollectionRunId),
    refetchOnWindowFocus: false,
    // 用例级进度靠报告明细轮询：打开期间与运行摘要同节奏刷新，终态自动停止。
    refetchInterval: (query) => (reportEventsConnected || (selectedCollectionRunId === activePollingCollectionRunId && activeCollectionEventsConnected))
      ? false : getRunEventFallbackInterval(query.state.data?.status),
  })

  const selectedRunSummary = activeCollectionRunQuery.data?.collectionRunId === selectedCollectionRunId
    ? activeCollectionRunQuery.data
    : collectionRunHistory.find((run) => run.collectionRunId === selectedCollectionRunId)
      ?? collectionRunReportQuery.data
  useRunReportRefresh({
    queryKey: 'apiCollectionRunReport', runId: selectedCollectionRunId, open: collectionRunReportOpen,
    status: selectedRunSummary?.status, reportStatus: collectionRunReportQuery.data?.status,
  })

  useEffect(() => {
    const currentRun = activeCollectionRunQuery.data
    if (!currentRun?.collectionRunId) return

    const previousStatus = previousActiveRunStatusRef.current
    previousActiveRunStatusRef.current = currentRun.status ?? ''
    if (isApiRunPollingStatus(currentRun.status)) return
    if (previousStatus === currentRun.status) return

    setActivePollingCollectionRunId('')
    queryClient.invalidateQueries({ queryKey: ['apiCollectionRuns', collectionId] })
    if (currentRun.status === 'success') {
      message.success('测试运行完成')
      return
    }
    if (currentRun.status === 'failed' || currentRun.status === 'error') {
      message.error(currentRun.errorMessage || '测试运行完成，存在失败项')
    }
  }, [activeCollectionRunQuery.data, collectionId, queryClient])

  useEffect(() => {
    const currentRun = activeApiCaseRunQuery.data
    const currentRunId = getApiCaseRunId(currentRun) || activeApiCaseRunId
    if (!currentRun || !currentRunId) return

    const normalizedRun = { ...currentRun, runId: currentRunId }
    setRunResult(normalizedRun)
    const previousStatus = previousApiCaseRunStatusRef.current
    previousApiCaseRunStatusRef.current = normalizedRun.status ?? ''

    if (isApiRunPollingStatus(normalizedRun.status)) return
    if (!isApiRunTerminalStatus(normalizedRun.status)) return
    if (previousStatus === normalizedRun.status) return

    setActiveApiCaseRunId('')
    if (normalizedRun.environmentId) {
      queryClient.invalidateQueries({ queryKey: ['apiEnvironmentVars', normalizedRun.environmentId] })
    }

    if (normalizedRun.status === 'canceled') {
      message.info('运行已停止')
      return
    }
    if (normalizedRun.status === 'success') {
      message.success('运行完成')
      return
    }
    if (normalizedRun.status === 'failed') {
      message.error(normalizedRun.errorMessage || '运行完成，断言失败')
      return
    }
    message.error(normalizedRun.errorMessage || '运行异常')
  }, [activeApiCaseRunId, activeApiCaseRunQuery.data, queryClient])

  useEffect(() => {
    if (!activeApiCaseRunId || activeApiCaseRunId === liveApiCaseRunId || !activeApiCaseRunQuery.error) return

    const errorMessage = getErrorMessage(activeApiCaseRunQuery.error)
    setRunResult((currentRun) => ({
      ...(currentRun ?? {}),
      runId: getApiCaseRunId(currentRun) || activeApiCaseRunId,
      status: 'error',
      errorMessage: currentRun?.errorMessage || errorMessage,
    }))
    previousApiCaseRunStatusRef.current = 'error'
    setActiveApiCaseRunId('')
    message.error(errorMessage)
  }, [activeApiCaseRunId, liveApiCaseRunId, activeApiCaseRunQuery.error])

  useEffect(() => {
    if (!collectionRunReportOpen || !selectedCollectionRunId) {
      initializedReportRef.current = ''
      return
    }
    const report = collectionRunReportQuery.data
    if (!report || report.collectionRunId !== selectedCollectionRunId || initializedReportRef.current === selectedCollectionRunId) return
    initializedReportRef.current = selectedCollectionRunId

    const orderedItems = [...(report.items ?? [])].sort((left, right) => {
      const leftOrderNo = left.orderNo ?? Number.MAX_SAFE_INTEGER
      const rightOrderNo = right.orderNo ?? Number.MAX_SAFE_INTEGER
      if (leftOrderNo !== rightOrderNo) return leftOrderNo - rightOrderNo
      return (left.caseName ?? '').localeCompare(right.caseName ?? '')
    })
    const firstExpandedIndex = orderedItems.findIndex(
      (item) => item.status === 'failed' || item.status === 'error' || isApiRunPollingStatus(item.status),
    )
    const fallbackExpandedIndex = firstExpandedIndex >= 0 ? firstExpandedIndex : orderedItems.length > 0 ? 0 : -1
    const firstExpandedItem = fallbackExpandedIndex >= 0 ? orderedItems[fallbackExpandedIndex] : undefined

    setCollectionRunReportView('items')
    setExpandedCollectionRunItemIds(firstExpandedItem ? [getCollectionRunItemKey(firstExpandedItem, fallbackExpandedIndex)] : [])
    setCollectionRunItemViews({})
  }, [collectionRunReportOpen, collectionRunReportQuery.data, selectedCollectionRunId])

  useEffect(() => {
    if (!selectedCollectionRunId) {
      if (loadingCollectionRunHistoryId) setLoadingCollectionRunHistoryId('')
      return
    }
    if (collectionRunReportQuery.isFetching) return
    if (loadingCollectionRunHistoryId === selectedCollectionRunId) {
      setLoadingCollectionRunHistoryId('')
    }
  }, [collectionRunReportQuery.isFetching, loadingCollectionRunHistoryId, selectedCollectionRunId])

  const runApiCaseMutation = useMutation({
    mutationFn: async ({ caseId, environmentId }: { caseId: string; environmentId: string }) => {
      let runId = ''
      try {
        const stream = await startDebugStream<ApiCaseRunResult>('api-case', caseId, { environmentId }, (event) => {
          if (event.type === 'changed') {
            void queryClient.invalidateQueries({ queryKey: ['apiCaseRun', runId] })
          } else if (event.type === 'finished') {
            const result = event.data as ApiCaseRunResult
            void queryClient.cancelQueries({ queryKey: ['apiCaseRun', runId], exact: true })
            setRunResult(result)
            setLiveApiCaseRunId('')
            setActiveApiCaseRunId('')
            previousApiCaseRunStatusRef.current = result.status ?? ''
            if (result.status === 'success') message.success('运行完成')
            else if (result.status === 'canceled') message.info('运行已停止')
            else message.error(result.errorMessage || '运行完成，存在失败项')
          } else if (event.type === 'disconnected') {
            setLiveApiCaseRunId('')
            message.warning('实时连接已断开，结果可能无法找回')
          }
        })
        runId = getApiCaseRunId(stream.initial)
        return { result: stream.initial, stream }
      } catch (error) {
        if (!(error instanceof DebugStreamUnavailable)) throw error
        message.warning('实时连接不可用，结果可能无法找回')
        return { result: await api.runApiCase(caseId, { environmentId, liveDebug: true }), stream: null }
      }
    },
    onSuccess: ({ result, stream }) => {
      debugStreamRef.current?.abort()
      debugStreamRef.current = stream
      setRunResult(result)
      setRunResultView('response')
      previousApiCaseRunStatusRef.current = result.status ?? ''
      const resultRunId = getApiCaseRunId(result)

      if (resultRunId && isApiRunPollingStatus(result.status)) {
        setActiveApiCaseRunId(resultRunId)
        setLiveApiCaseRunId(stream ? resultRunId : '')
        message.info('已开始运行用例')
        stream?.activate()
        return
      }

      if (resultRunId && !isApiRunTerminalStatus(result.status)) {
        setActiveApiCaseRunId(resultRunId)
        setLiveApiCaseRunId(stream ? resultRunId : '')
        message.info('已创建运行记录，正在等待结果')
        stream?.activate()
        return
      }

      if (isApiRunPollingStatus(result.status)) {
        message.error('已创建运行记录，但未获取到运行 ID')
        return
      }

      setActiveApiCaseRunId('')
      if (result.status === 'success' || result.success) {
        message.success('运行完成')
        return
      }
      if (result.status === 'failed') {
        message.error(result.errorMessage || '运行完成，断言失败')
        return
      }
      message.error(result.errorMessage || '运行异常')
    },
    onSettled: (_result, _error, variables) => {
      if (!variables?.environmentId) return
      queryClient.invalidateQueries({ queryKey: ['apiEnvironmentVars', variables.environmentId] })
    },
    onError: () => {
      setLiveApiCaseRunId('')
      setRunResult(null)
      setActiveApiCaseRunId('')
      previousApiCaseRunStatusRef.current = ''
    },
  })

  const runApiCollectionMutation = useMutation({
    mutationFn: ({ collectionId: targetCollectionId, environmentId }: { collectionId: string; environmentId: string }) =>
      api.runApiCollection(targetCollectionId, { environmentId }),
    onSuccess: (summary) => {
      if (!summary.collectionRunId) {
        message.error('未获取到运行记录 ID')
        return
      }

      previousActiveRunStatusRef.current = summary.status ?? ''
      setActivePollingCollectionRunId(summary.collectionRunId)
      setCollectionRunHistoryOpen(true)
      queryClient.invalidateQueries({ queryKey: ['apiCollectionRuns', collectionId] })
      void refetchHistory()
      message.success(isApiRunPollingStatus(summary.status) ? '已开始运行测试' : '已创建运行记录')
    },
    onSettled: (_result, _error, variables) => {
      if (!variables?.environmentId) return
      queryClient.invalidateQueries({ queryKey: ['apiEnvironmentVars', variables.environmentId] })
      queryClient.invalidateQueries({ queryKey: ['apiCollectionRuns', collectionId] })
    },
  })
  return {
    runResult,
    setRunResult,
    setActiveApiCaseRunId,
    runResultView,
    setRunResultView,
    collectionRunReportOpen,
    setCollectionRunReportOpen,
    collectionRunHistoryOpen,
    setCollectionRunHistoryOpen,
    selectedCollectionRunId,
    setSelectedCollectionRunId,
    setActivePollingCollectionRunId,
    loadingCollectionRunHistoryId,
    setLoadingCollectionRunHistoryId,
    refreshingCollectionRunReport,
    setRefreshingCollectionRunReport,
    collectionRunReportView,
    setCollectionRunReportView,
    expandedCollectionRunItemIds,
    setExpandedCollectionRunItemIds,
    collectionRunItemViews,
    setCollectionRunItemViews,
    previousApiCaseRunStatusRef,
    previousActiveRunStatusRef,
    collectionRunHistoryQuery,
    collectionRunHistory,
    collectionRunHistoryTotal,
    activeCollectionRunQuery,
    collectionRunReportQuery,
    runApiCaseMutation,
    runApiCollectionMutation,
  }
}
