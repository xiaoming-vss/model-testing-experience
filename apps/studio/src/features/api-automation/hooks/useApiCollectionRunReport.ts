import type { useQueryClient } from '@tanstack/react-query'
import type { ApiCollectionRunSummary } from '@/services/api'
import { saveBlob } from '@/shared/utils/download'
import { message } from '@/shared/utils/feedback'
import { compareByOrderNo } from '@/shared/utils/order'
import { formatTime, getErrorMessage, normalizeEnvironmentId } from '@/utils/format'
import type { RunResultView } from '../config/collectionConfig'
import type { ApiEnvironment } from '../types'
import { buildCollectionRunReportHtml, sanitizeFileName } from '../utils/collectionRunReport'
import { isApiRunPollingStatus } from '../utils/detailView'
import type { useApiExecution } from './useApiExecution'

export function useApiCollectionRunReport({
  collectionId,
  queryClient,
  environments,
  collectionName,
  execution,
}: {
  collectionId: string
  queryClient: ReturnType<typeof useQueryClient>
  environments: ApiEnvironment[]
  collectionName: string
  execution: ReturnType<typeof useApiExecution>
}) {
  const selectedCollectionRunSummary =
    (execution.selectedCollectionRunId && execution.activeCollectionRunQuery.data?.collectionRunId === execution.selectedCollectionRunId ? execution.activeCollectionRunQuery.data : undefined) ??
    execution.collectionRunHistory.find((item) => item.collectionRunId === execution.selectedCollectionRunId)
  const collectionRunReport = execution.collectionRunReportQuery.data
    ? { ...execution.collectionRunReportQuery.data, ...(isApiRunPollingStatus(execution.collectionRunReportQuery.data.status) ? selectedCollectionRunSummary : undefined) }
    : null
  const orderedCollectionRunItems = [...(collectionRunReport?.items ?? [])].sort((left, right) => {
    const order = compareByOrderNo(left, right)
    if (order !== 0) return order
    return (left.caseName ?? '').localeCompare(right.caseName ?? '')
  })

  async function handleRefreshCollectionRunReport() {
    const collectionRunId = execution.selectedCollectionRunId
    if (!collectionRunId) return

    execution.setRefreshingCollectionRunReport(true)
    try {
      await execution.collectionRunReportQuery.refetch()
      await queryClient.invalidateQueries({ queryKey: ['apiCollectionRun', collectionRunId] })
      await queryClient.invalidateQueries({ queryKey: ['apiCollectionRuns', collectionId] })
      message.success('报告已刷新')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      execution.setRefreshingCollectionRunReport(false)
    }
  }

  function handleExportCollectionRunReportHtml() {
    if (!collectionRunReport) return

    const environmentName =
      environments.find((environment) => normalizeEnvironmentId(environment) === collectionRunReport.environmentId)?.name ??
      collectionRunReport.environmentId ??
      '-'
    const html = buildCollectionRunReportHtml({
      collectionName,
      environmentName,
      report: collectionRunReport,
      items: orderedCollectionRunItems,
    })
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const startedAtText = collectionRunReport.startedAt ? formatTime(collectionRunReport.startedAt).replaceAll(/[/: ]/g, '-') : 'report'
    saveBlob(blob, `${sanitizeFileName(collectionName)}-${sanitizeFileName(startedAtText)}.html`)
    message.success('HTML 报告已导出')
  }

  function handleOpenCollectionRunHistoryItem(historyItem: ApiCollectionRunSummary) {
    execution.setLoadingCollectionRunHistoryId(historyItem.collectionRunId ?? '')
    execution.setSelectedCollectionRunId(historyItem.collectionRunId ?? '')
    execution.setCollectionRunReportOpen(true)
    if (isApiRunPollingStatus(historyItem.status) && historyItem.collectionRunId) {
      execution.rememberActiveCollectionRunStatus(historyItem.status)
      execution.setActivePollingCollectionRunId(historyItem.collectionRunId)
    }
    execution.setCollectionRunHistoryOpen(false)
  }

  function toggleCollectionRunItem(itemKey: string) {
    execution.setExpandedCollectionRunItemIds((current) => (current.includes(itemKey) ? current.filter((key) => key !== itemKey) : [...current, itemKey]))
  }

  function handleCollectionRunItemViewChange(itemKey: string, view: RunResultView) {
    execution.setCollectionRunItemViews((current) => (current[itemKey] === view ? current : { ...current, [itemKey]: view }))
  }

  return {
    selectedCollectionRunSummary,
    collectionRunReport,
    orderedCollectionRunItems,
    handleRefreshCollectionRunReport,
    handleExportCollectionRunReportHtml,
    handleOpenCollectionRunHistoryItem,
    toggleCollectionRunItem,
    handleCollectionRunItemViewChange,
  } as const
}
