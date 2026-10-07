import type { BugZentaoJob, BugZentaoPush } from '../types'

export function isZentaoJobActive(job?: BugZentaoJob | null) {
  return !!job && ['queued', 'claimed', 'running'].includes(job.jobStatus)
}

export function zentaoPollingInterval(data?: BugZentaoPush) {
  return isZentaoJobActive(data?.activeJob ?? data?.latestJob) ? 3000 : false
}

export function zentaoJobLabel(job: BugZentaoJob) {
  const name = job.taskType === 'zentao_bug_fields_update' ? '版本和指派人修改' : '禅道同步'
  const labels: Record<BugZentaoJob['jobStatus'], string> = {
    queued: '已提交，等待执行', claimed: '已领取，正在核对', running: '正在执行',
    succeeded: '已完成', partial: '部分完成', failed: '失败', unknown: '结果待核对', canceled: '已取消',
    quarantined: '恢复隔离，等待外部核对',
  }
  if (job.jobStatus === 'queued' && job.queueReason) {
    const reasons = {
      waiting: '已提交，等待执行', paused: '执行已暂停，任务保留在队列',
      worker_offline: '等待执行服务上线', worker_incompatible: '当前执行服务不支持此任务，请升级执行服务',
      target_busy: '等待同一禅道实例的任务完成', runtime_changed: '运行代次已变化，等待运维核对',
    }
    return `${name}：${reasons[job.queueReason]}`
  }
  return `${name}：${labels[job.jobStatus]}`
}

export function sameBuilds(left: string[], right: string[]) {
  return left.length === right.length && left.every((id) => right.includes(id))
}
