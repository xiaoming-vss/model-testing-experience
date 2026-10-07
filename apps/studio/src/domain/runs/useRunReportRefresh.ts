import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { getRunPollingInterval } from './polling'

/** Fetch the final report once, only while it is open, after its summary finishes. */
export function useRunReportRefresh({ queryKey, runId, open, status, reportStatus }: {
  queryKey: string
  runId: string
  open: boolean
  status?: string
  reportStatus?: string
}) {
  const client = useQueryClient()
  const refreshed = useRef('')
  useEffect(() => {
    if (!open || !runId || !status || getRunPollingInterval(status) !== false || !reportStatus) return
    if (getRunPollingInterval(reportStatus) === false) return
    const key = `${queryKey}:${runId}:${status}`
    if (refreshed.current === key) return
    refreshed.current = key
    void client.invalidateQueries({ queryKey: [queryKey, runId], exact: true })
  }, [client, open, queryKey, reportStatus, runId, status])
}
