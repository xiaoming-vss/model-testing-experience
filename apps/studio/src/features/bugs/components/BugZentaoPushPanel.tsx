import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, InputNumber, Space, Typography } from 'antd'
import { SendOutlined } from '@ant-design/icons'
import { bugsApi } from '../api/bugs.api'
import type { BugZentaoJob, BugZentaoPush } from '../types'
import { useBugZentaoStatus } from '../hooks/useBugZentaoStatus'
import { isZentaoJobActive, sameBuilds, zentaoJobLabel } from '../utils/zentaoJobs'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { BugZentaoPushModal } from './BugZentaoPushModal'

const labels: Record<BugZentaoPush['status'], string> = {
  not_pushed: '尚未推送', preparing: '正在核对目标', creating: '正在推送',
  succeeded: '已推送', failed: '推送失败', unknown: '结果待核对',
}

export function BugZentaoPushPanel({ bugId, canWrite }: { bugId: string; canWrite: boolean }) {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [remoteId, setRemoteId] = useState<number | null>(null)
  const [openedBuild, setOpenedBuild] = useState<string[]>(['trunk'])
  const [assignedTo, setAssignedTo] = useState('')
  const queryKey = ['bugZentaoPush', bugId]
  const jobs = useBugZentaoStatus(bugId)
  const query = jobs.query
  const existing = query.data?.status === 'succeeded'
  const options = useQuery({
    queryKey: ['bugZentaoPushOptions', bugId, query.data?.target, existing],
    queryFn: async () => {
      const result = await bugsApi.getBugZentaoPushOptions(bugId)
      if (existing && result.current) {
        setOpenedBuild(result.current.openedBuild)
        setAssignedTo(result.current.assignedTo)
      }
      return result
    },
    enabled: open && canWrite,
    staleTime: 0,
    refetchOnWindowFocus: false,
  })
  const current = options.data?.current
  const unchangedBuilds = existing && !!current && sameBuilds(openedBuild, current.openedBuild)
  const unchangedAssignee = existing && !!current && assignedTo === current.assignedTo
  const choicesValid = !!options.data && !options.isFetching && !options.error
    && openedBuild.length > 0
    && (unchangedBuilds || openedBuild.every((id) => options.data.builds.some((build) => build.id === id)))
    && (unchangedAssignee || !assignedTo || options.data.users.some((user) => user.account === assignedTo))
  const fieldsChanged = !!current && (assignedTo !== current.assignedTo
    || openedBuild.length !== current.openedBuild.length
    || openedBuild.some((id) => !current.openedBuild.includes(id)))
  const fieldPayload = () => ({
    openedBuild, assignedTo, expectedTarget: options.data!.target,
    expectedRemoteBugId: current!.remoteBugId,
    expectedOpenedBuild: current!.openedBuild,
    expectedAssignedTo: current!.assignedTo,
  })
  const saved = (result: BugZentaoPush | BugZentaoJob) => {
    if ('jobId' in result) {
      setOpen(false)
      jobs.accepted(result, result.taskType === 'zentao_bug_fields_update' && !!retrySync)
      return
    }
    client.setQueryData(queryKey, result)
    setOpen(false)
    void client.invalidateQueries({ queryKey })
    void client.invalidateQueries({ queryKey: ['bugActivities', bugId] })
    if (result.status === 'succeeded' && [result.attachmentStatus, result.descriptionStatus].every((status) => !status || ['none', 'succeeded'].includes(status))) message.success(`已关联禅道 Bug #${result.remoteBugId}`)
    else message.error(result.errorMessage || labels[result.status])
  }
  const push = useMutation({
    mutationFn: async () => {
      if (existing && fieldsChanged) return jobs.submitFields(fieldPayload())
      if (!existing) return jobs.submitSync({
        openedBuild, assignedTo, expectedTarget: options.data!.target,
      })
      if (retrySync) return jobs.submitSync()
      return query.data!
    }, onSuccess: saved,
    onError: (error) => {
      message.error(getErrorMessage(error))
      void client.invalidateQueries({ queryKey })
      void options.refetch()
    },
  })
  const reconcile = useMutation({
    mutationFn: () => bugsApi.reconcileBugZentaoPush(bugId, remoteId!), onSuccess: saved,
    onError: (error) => message.error(getErrorMessage(error)),
  })
  const data = query.data
  const latestJob = data?.activeJob ?? data?.latestJob
  const jobBusy = isZentaoJobActive(latestJob)
  const attachmentIncomplete = data?.status === 'succeeded' && data.attachmentStatus && !['none', 'succeeded'].includes(data.attachmentStatus)
  const descriptionIncomplete = data?.status === 'succeeded' && data.descriptionStatus && !['none', 'succeeded'].includes(data.descriptionStatus)
  const retrySync = data?.status === 'succeeded' && (['pending', 'failed'].includes(data.attachmentStatus ?? '') || ['pending', 'failed', 'unknown'].includes(data.descriptionStatus ?? ''))
  const busy = push.isPending || reconcile.isPending || jobBusy
  const fieldBusy = ['preparing', 'updating'].includes(data?.fieldUpdateStatus ?? '')
  const canConfirm = canWrite && !busy && !fieldBusy && choicesValid
    && (existing ? !!current : data?.ready)
    && data?.ready
  return <section className="bug-detail-panel">
    <h2 className="bug-panel-title">禅道同步</h2>
    {query.error && <Alert showIcon type="error" title={getErrorMessage(query.error)}
      action={<Button onClick={() => query.refetch()}>重新加载</Button>} />}
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      {latestJob && <Alert showIcon
        type={isZentaoJobActive(latestJob) ? 'info' : latestJob.jobStatus === 'succeeded' ? 'success' : 'warning'}
        title={zentaoJobLabel(latestJob)} />}
      <Typography.Text>{descriptionIncomplete ? 'Bug 已创建，正文图片同步未完成' : attachmentIncomplete ? 'Bug 已创建，附件同步未完成' : data ? labels[data.status] : '加载同步信息中…'}
        {data?.remoteBugId ? ` · 禅道 Bug #${data.remoteBugId}` : ''}</Typography.Text>
      {data?.reason && <Alert type="info" showIcon title={data.reason} />}
      {data?.errorMessage && <Alert type="warning" showIcon title={data.errorMessage} />}
      {data?.fieldUpdateError && <Alert type="warning" showIcon title={data.fieldUpdateError} />}
      {data?.status === 'unknown' && <>
        <Alert type="warning" showIcon title="请先在禅道核对创建结果，勿重复创建。找到对应 Bug 后可填写编号完成关联。" />
        {canWrite && <Space wrap>
          <InputNumber min={1} precision={0} aria-label="待核对的禅道 Bug 编号" placeholder="禅道 Bug 编号"
            value={remoteId} onChange={setRemoteId} />
          <Button disabled={!remoteId || busy} loading={reconcile.isPending} onClick={() => reconcile.mutate()}>核对并关联</Button>
        </Space>}
      </>}
      {canWrite && data?.status !== 'unknown' && <Button
        aria-label={data?.status === 'failed' || retrySync ? '重试推送到禅道' : '推送到禅道'}
        icon={<SendOutlined />} loading={push.isPending || fieldBusy} disabled={(!existing && !data?.ready) || busy || fieldBusy}
        onClick={() => {
          setOpenedBuild(data?.openedBuild ?? ['trunk'])
          setAssignedTo(data?.assignedTo ?? '')
          setOpen(true)
        }}>
        {data?.status === 'failed' || retrySync ? '重试推送到禅道' : '推送到禅道'}
      </Button>}
    </Space>
    <BugZentaoPushModal open={open} data={data} busy={busy} pending={push.isPending}
      canConfirm={!!canConfirm} choicesValid={choicesValid} fieldsChanged={fieldsChanged}
      retrySync={!!retrySync} openedBuild={openedBuild} assignedTo={assignedTo}
      setOpenedBuild={setOpenedBuild} setAssignedTo={setAssignedTo} setOpen={setOpen}
      onConfirm={() => push.mutate()} options={options} />
  </section>
}
