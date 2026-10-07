import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { listItems, type ListResponse } from '@/shared/api/request'

type Run = {
  runId?: string
  status?: string
  updatedAt?: string
  reviewStatus?: string
  importStatus?: string
  currentStage?: string
  stageStatus?: string
}

function runVersion(run?: Run) {
  return JSON.stringify([run?.status, run?.updatedAt, run?.reviewStatus, run?.importStatus, run?.currentStage, run?.stageStatus])
}

/** Detail polling updates the history without a request. History discovers other users' changes. */
export function useTaskRunHistorySync<T extends Run>({ historyKey, detailKey, taskId, selectedRunId, history, detail }: {
  historyKey: string
  detailKey: string
  taskId: string
  selectedRunId?: string
  history?: ListResponse<T>
  detail?: T
}) {
  const client = useQueryClient()
  const previousHistory = useRef('')

  useEffect(() => {
    const record = listItems(history).find((item) => item.runId === selectedRunId)
    const version = record ? `${selectedRunId}:${runVersion(record)}` : ''
    const previous = previousHistory.current
    previousHistory.current = version
    // A summary never replaces a full detail. Fetch it once when a newer history disagrees.
    if (!record || !detail || !previous || previous === version || runVersion(record) === runVersion(detail)) return
    if (record.updatedAt && detail.updatedAt && new Date(record.updatedAt) < new Date(detail.updatedAt)) return
    void client.invalidateQueries({ queryKey: [detailKey, selectedRunId], exact: true })
  }, [client, detail, detailKey, history, selectedRunId])

  useEffect(() => {
    if (!detail?.runId || detail.runId !== selectedRunId) return
    client.setQueriesData<ListResponse<T> & { statusCounts?: Record<string, number>; latestRun?: T }>({ queryKey: [historyKey, taskId] }, (current) => {
      if (!current) return current
      const items = listItems(current)
      const record = items.find((item) => item.runId === detail.runId) ?? (current.latestRun?.runId === detail.runId ? current.latestRun : undefined)
      if (!record || record === detail) return current
      if (record.updatedAt && detail.updatedAt && new Date(record.updatedAt) > new Date(detail.updatedAt)) return current
      const next = items.map((item) => item.runId === detail.runId ? detail : item)
      const counts = current.statusCounts ? { ...current.statusCounts } : undefined
      if (counts && record.status !== detail.status) {
        if (record.status) counts[record.status] = Math.max(0, (counts[record.status] ?? 0) - 1)
        if (detail.status) counts[detail.status] = (counts[detail.status] ?? 0) + 1
      }
      return Object.assign(next, { items: next.slice(), total: current.total,
        statusCounts: counts, latestRun: current.latestRun?.runId === detail.runId ? detail : current.latestRun })
    })
  }, [client, detail, historyKey, selectedRunId, taskId])
}
