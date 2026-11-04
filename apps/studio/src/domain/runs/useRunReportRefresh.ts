import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { getRunPollingInterval } from './polling'
import { refreshRunQuery } from './refreshRunQuery'

/** Fetch the final report as soon as its summary finishes, without waiting for the report's own poll. */
export function useRunReportRefresh({ queryKey, runId, open, status, reportStatus }: {
  queryKey: string
  runId: string
  open: boolean
  status?: string
  reportStatus?: string
}) {
  const client = useQueryClient()
  useEffect(() => {
    if (!open || !runId || !status || getRunPollingInterval(status) !== false || !reportStatus) return
    if (getRunPollingInterval(reportStatus) === false) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempts = 0
    const refresh = async () => {
      attempts += 1
      try {
        await refreshRunQuery(client, [queryKey, runId])
      } catch {
        // The query retains its own error state; the bounded retry can recover it.
      }
      if (!stopped && attempts < 3) timer = setTimeout(() => { void refresh() }, 1000)
    }
    void refresh()
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
    }
  }, [client, open, queryKey, reportStatus, runId, status])
}
