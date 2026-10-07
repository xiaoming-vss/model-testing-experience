import { describe, expect, it } from 'vitest'
import type { BugZentaoJob } from '../types'
import { zentaoJobLabel, zentaoPollingInterval } from './zentaoJobs'

const job: BugZentaoJob = { jobId: 'queued', jobStatus: 'queued', taskType: 'zentao_bug_sync', protocolVersion: 1, result: { steps: {} } }

describe('queued executor availability', () => {
  it.each([
    ['paused', '执行已暂停'], ['worker_offline', '等待执行服务上线'],
    ['worker_incompatible', '当前执行服务不支持此任务'], ['target_busy', '等待同一禅道实例'],
    ['runtime_changed', '运行代次已变化'],
  ] as const)('explains %s while continuing local polling', (queueReason, text) => {
    const queued = { ...job, queueReason }
    expect(zentaoJobLabel(queued)).toContain(text)
    expect(zentaoPollingInterval({ status: 'not_pushed', ready: false, reason: '', remoteBugId: null,
      target: {}, errorMessage: '', actorUserId: '', updatedAt: null, warnings: [],
      executionMode: 'worker', activeJob: queued })).toBe(3000)
  })
  it('keeps the label compatible with older control planes and ignores stale queue reasons at completion', () => {
    expect(zentaoJobLabel(job)).toBe('禅道同步：已提交，等待执行')
    expect(zentaoJobLabel({ ...job, jobStatus: 'succeeded', queueReason: 'worker_offline' })).toBe('禅道同步：已完成')
  })
})
