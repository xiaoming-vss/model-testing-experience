import {
  type CollectionReportView,
  type RunResultView
} from '@/features/api-automation/config/collectionConfig'
import type { ApiCollectionRunReport } from '@/features/api-automation/types'
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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

type Options = {
  collectionId: string
}

export function useApiExecution({ collectionId }: Options) {
  const queryClient = useQueryClient()
  const [runResult, setRunResult] = useState<ApiCaseRunResult | null>(null)

  const [activeApiCaseRunId, setActiveApiCaseRunId] = useState('')

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

  const activeApiCaseRunQuery = useQuery({
    queryKey: ['apiCaseRun', activeApiCaseRunId],
    queryFn: () => api.getApiCaseRun(activeApiCaseRunId),
    enabled: Boolean(activeApiCaseRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as ApiCaseRunResult | undefined
      return !data || isApiRunPollingStatus(data.status) ? 1500 : false
    },
  })

  const collectionRunHistoryQuery = useQuery({
    queryKey: ['apiCollectionRuns', collectionId],
    queryFn: () => api.getApiCollectionRuns(collectionId),
    enabled: Boolean(collectionId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = (query.state.data as ApiCollectionRunSummary[] | undefined) ?? []
      return data.some((item) => isApiRunPollingStatus(item.status)) ? 3000 : false
    },
  })

  const activeCollectionRunQuery = useQuery({
    queryKey: ['apiCollectionRun', activePollingCollectionRunId],
    queryFn: () => api.getApiCollectionRun(activePollingCollectionRunId),
    enabled: Boolean(activePollingCollectionRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as ApiCollectionRunSummary | undefined
      return !data || isApiRunPollingStatus(data.status) ? 3000 : false
    },
  })

  const collectionRunReportQuery = useQuery({
    queryKey: ['apiCollectionRunReport', selectedCollectionRunId],
    queryFn: () => api.getApiCollectionRunReport(selectedCollectionRunId),
    enabled: collectionRunReportOpen && Boolean(selectedCollectionRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as ApiCollectionRunReport | undefined
      return collectionRunReportOpen && (!data || isApiRunPollingStatus(data.status)) && Boolean(selectedCollectionRunId) ? 3000 : false
    },
  })

  useEffect(() => {
    const currentRun = activeCollectionRunQuery.data
    if (!currentRun?.collectionRunId) return

    queryClient.setQueryData<ApiCollectionRunSummary[]>(['apiCollectionRuns', collectionId], (current) => {
      const currentItems = current ?? []
      const nextItems = [currentRun, ...currentItems.filter((item) => item.collectionRunId !== currentRun.collectionRunId)]
      return nextItems.sort((left, right) => {
        const leftTime = new Date(left.startedAt || left.createdAt || left.updatedAt || '').getTime()
        const rightTime = new Date(right.startedAt || right.createdAt || right.updatedAt || '').getTime()
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
      })
    })

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
    if (!activeApiCaseRunId || !activeApiCaseRunQuery.error) return

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
  }, [activeApiCaseRunId, activeApiCaseRunQuery.error])

  useEffect(() => {
    const report = collectionRunReportQuery.data
    if (!report) return

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
  }, [collectionRunReportQuery.data])

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
    mutationFn: ({ caseId, environmentId }: { caseId: string; environmentId: string }) => api.runApiCase(caseId, { environmentId }),
    onSuccess: (result) => {
      setRunResult(result)
      setRunResultView('response')
      previousApiCaseRunStatusRef.current = result.status ?? ''
      const resultRunId = getApiCaseRunId(result)

      if (resultRunId && isApiRunPollingStatus(result.status)) {
        setActiveApiCaseRunId(resultRunId)
        message.info('已开始运行用例')
        return
      }

      if (resultRunId && !isApiRunTerminalStatus(result.status)) {
        setActiveApiCaseRunId(resultRunId)
        message.info('已创建运行记录，正在等待结果')
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
      queryClient.setQueryData<ApiCollectionRunSummary[]>(['apiCollectionRuns', collectionId], (current) => {
        const currentItems = current ?? []
        return [summary, ...currentItems.filter((item) => item.collectionRunId !== summary.collectionRunId)]
      })
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
    activeCollectionRunQuery,
    collectionRunReportQuery,
    runApiCaseMutation,
    runApiCollectionMutation,
  }
}
