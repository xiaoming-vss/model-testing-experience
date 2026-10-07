import { useCallback, useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from '@/shared/utils/feedback'
import { getAuthenticatedUserId } from '@/features/auth/api/auth.api'
import { bugsApi } from '../api/bugs.api'
import { getErrorMessage } from '@/utils/format'
import type { BugZentaoJob, BugZentaoPush, BugZentaoPushPayload, BugZentaoUpdatePayload } from '../types'
import { isZentaoJobActive, zentaoJobLabel, zentaoPollingInterval } from '../utils/zentaoJobs'
import { readFollowUp, saveFollowUp, type ZentaoFollowUp } from '../utils/zentaoFollowUp'

export function useBugZentaoStatus(bugId: string) {
  const client = useQueryClient()
  const queryKey = ['bugZentaoPush', bugId]
  const request = useRef<{ input: string; id: string } | null>(null)
  const seen = useRef(new Map<string, BugZentaoJob['jobStatus']>())
  const followUp = useRef<ZentaoFollowUp | null>(null)
  const query = useQuery({
    queryKey, queryFn: () => bugsApi.getBugZentaoPush(bugId),
    refetchInterval: (q) => zentaoPollingInterval(q.state.data),
  })
  const job = query.data?.activeJob ?? query.data?.latestJob
  const accepted = useCallback((result: BugZentaoJob, syncAfterFields = false) => {
    seen.current.set(result.jobId, result.jobStatus)
    const actor = getAuthenticatedUserId()
    followUp.current = syncAfterFields
      ? { actor, jobId: result.jobId, requestId: crypto.randomUUID(), started: false } : null
    saveFollowUp(actor, bugId, followUp.current)
    client.setQueryData<BugZentaoPush>(['bugZentaoPush', bugId], (current) => current && ({
      ...current, ready: false, activeJob: result, latestJob: result,
    }))
    message.info(syncAfterFields
      ? '已提交版本和指派人修改，完成后将继续同步附件和正文图片'
      : '已提交，执行结果将自动更新')
    void client.invalidateQueries({ queryKey: ['bugZentaoPush', bugId] })
  }, [bugId, client])
  useEffect(() => () => { followUp.current = null }, [bugId])
  useEffect(() => {
    if (!job) return
    const previous = seen.current.get(job.jobId)
    seen.current.set(job.jobId, job.jobStatus)
    if (previous === job.jobStatus || isZentaoJobActive(job)) return
    void client.invalidateQueries({ queryKey: ['bugActivities', bugId] })
    if (previous) { // Opening an old result refreshes history without another toast.
      if (job.jobStatus === 'succeeded') message.success(zentaoJobLabel(job))
      else if (job.jobStatus === 'failed') message.error(zentaoJobLabel(job))
      else message.warning(zentaoJobLabel(job))
    }
    const actor = getAuthenticatedUserId()
    const next = followUp.current ?? readFollowUp(actor, bugId)
    if (!next || next.started) return
    if (next.actor !== actor) {
      followUp.current = null
      return
    }
    if (next.jobId !== job.jobId || job.taskType !== 'zentao_bug_fields_update') {
      saveFollowUp(actor, bugId, null)
      followUp.current = null
      return
    }
    if (job.jobStatus !== 'succeeded') {
      saveFollowUp(actor, bugId, null)
      followUp.current = null
      return
    }
    followUp.current = { ...next, started: true }
    request.current = { input: JSON.stringify({ bugId, type: 'sync', body: {} }), id: next.requestId }
    void bugsApi.submitBugZentaoSync(bugId, { requestId: next.requestId }).then((result) => {
      request.current = null
      accepted(result)
    }).catch((error: unknown) => {
      followUp.current = null
      message.error(getErrorMessage(error))
      void client.invalidateQueries({ queryKey: ['bugZentaoPush', bugId] })
    })
  }, [accepted, bugId, client, job])

  function requestId(type: string, body: object) {
    const input = JSON.stringify({ bugId, type, body })
    if (request.current?.input !== input) request.current = { input, id: crypto.randomUUID() }
    return request.current.id
  }

  async function submitSync(body: Partial<BugZentaoPushPayload> = {}) {
    const result = await bugsApi.submitBugZentaoSync(bugId, {
      ...body, requestId: requestId('sync', body),
    })
    request.current = null
    return result
  }

  async function submitFields(body: BugZentaoUpdatePayload) {
    const result = await bugsApi.submitBugZentaoFields(bugId, {
      ...body, requestId: requestId('fields', body),
    })
    request.current = null
    return result
  }

  return { query, submitSync, submitFields, accepted }
}
