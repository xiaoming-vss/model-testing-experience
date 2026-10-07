import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { message } from '@/shared/utils/feedback'
import * as auth from '@/features/auth/api/auth.api'
import { saveFollowUp } from '../utils/zentaoFollowUp'
import { bugsApi } from '../api/bugs.api'
import type { BugZentaoJob, BugZentaoPush } from '../types'
import { BugZentaoPushPanel } from './BugZentaoPushPanel'

vi.mock('@/shared/utils/feedback', () => ({ message: {
  success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(),
} }))
const clients: QueryClient[] = []
const ready: BugZentaoPush = {
  executionMode: 'worker', status: 'not_pushed', ready: true, reason: '', remoteBugId: null,
  target: { project: 10, execution: 20, story: 30 }, errorMessage: '', actorUserId: 'owner',
  updatedAt: null, warnings: [],
}
const queued: BugZentaoJob = {
  jobId: 'j1', jobStatus: 'queued', taskType: 'zentao_bug_sync', protocolVersion: 1,
  result: { steps: {} },
}
beforeEach(() => {
  sessionStorage.clear()
  vi.spyOn(auth, 'getAuthenticatedUserId').mockReturnValue('current-owner')
  vi.spyOn(bugsApi, 'getBugZentaoPushOptions').mockResolvedValue({
    target: ready.target, builds: [{ id: 'trunk', name: '主干' }],
    users: [{ account: 'dev', name: '开发甲' }],
    current: { remoteBugId: 50, openedBuild: ['999'], assignedTo: '' },
  })
})

it.each(['current-owner', 'other-member'])('restores a confirmed follow-up only for its original actor: %s', async (actor) => {
  saveFollowUp('current-owner', 'b1', { actor: 'current-owner', jobId: 'fields', requestId: 'same-request', started: false })
  vi.mocked(auth.getAuthenticatedUserId).mockReturnValue(actor)
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue({ ...ready, status: 'succeeded', remoteBugId: 50,
    latestJob: { ...queued, jobId: 'fields', taskType: 'zentao_bug_fields_update', jobStatus: 'succeeded' } })
  const sync = vi.spyOn(bugsApi, 'submitBugZentaoSync').mockResolvedValue(queued)
  mount()
  if (actor === 'current-owner') await waitFor(() => expect(sync).toHaveBeenCalledExactlyOnceWith('b1', { requestId: 'same-request' }))
  else {
    expect(await screen.findByText('版本和指派人修改：已完成')).toBeInTheDocument()
    expect(sync).not.toHaveBeenCalled()
  }
})
afterEach(() => {
  cleanup(); clients.forEach((client) => client.clear()); clients.length = 0
  vi.restoreAllMocks(); vi.clearAllMocks()
})
function mount(canWrite = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(<QueryClientProvider client={client}><BugZentaoPushPanel bugId="b1" canWrite={canWrite} /></QueryClientProvider>)
  return client
}

it('shows restored jobs as quarantined and prevents remote submission', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue({
    ...ready, ready: false, reason: '恢复环境的外部集成尚未核对，已暂停所有远端写入',
    latestJob: { ...queued, jobStatus: 'quarantined' },
  })
  const submit = vi.spyOn(bugsApi, 'submitBugZentaoSync')
  mount()
  expect(await screen.findByText('禅道同步：恢复隔离，等待外部核对')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '推送到禅道' })).toBeDisabled()
  expect(submit).not.toHaveBeenCalled()
})

it('accepts a job without reporting remote success or using the old write endpoint', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(ready)
  expect('pushBugToZentao' in bugsApi).toBe(false)
  const submit = vi.spyOn(bugsApi, 'submitBugZentaoSync').mockImplementation(async () => {
    vi.mocked(bugsApi.getBugZentaoPush).mockResolvedValue({ ...ready, ready: false, activeJob: queued, latestJob: queued })
    return queued
  })
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '推送到禅道' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '确认推送' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  expect(await screen.findByText('禅道同步：已提交，等待执行')).toBeInTheDocument()
  expect(submit).toHaveBeenCalledExactlyOnceWith('b1', {
    requestId: expect.any(String), openedBuild: ['trunk'], assignedTo: '', expectedTarget: ready.target,
  })
  expect(message.info).toHaveBeenCalledWith('已提交，执行结果将自动更新')
  expect(message.success).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '推送到禅道' })).toBeDisabled()
})

it('reuses the request identifier after an uncertain submission response', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(ready)
  const submit = vi.spyOn(bugsApi, 'submitBugZentaoSync')
    .mockRejectedValueOnce(new Error('连接中断'))
    .mockResolvedValue(queued)
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '推送到禅道' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '确认推送' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(message.error).toHaveBeenCalledWith('连接中断'))
  await waitFor(() => expect(screen.getByRole('button', { name: '确认推送' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(2))
  expect(submit.mock.calls[0]).toEqual(submit.mock.calls[1])
})

it('resumes queued polling after reopening and refreshes history on a partial terminal result', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue({ ...ready, ready: false, activeJob: queued, latestJob: queued })
  const submit = vi.spyOn(bugsApi, 'submitBugZentaoSync')
  const client = mount(false)
  const refresh = vi.spyOn(client, 'invalidateQueries')
  expect(await screen.findByText('禅道同步：已提交，等待执行')).toBeInTheDocument()
  const partial: BugZentaoJob = { ...queued, jobStatus: 'partial', result: {
    steps: { create_bug: 'succeeded', 'upload_attachment:f1': 'failed', update_description: 'blocked' },
  } }
  vi.mocked(bugsApi.getBugZentaoPush).mockResolvedValue({ ...ready, status: 'succeeded', remoteBugId: 50,
    attachmentStatus: 'failed', latestJob: partial, activeJob: null })
  await waitFor(() => expect(screen.getByText('禅道同步：部分完成')).toBeInTheDocument(), { timeout: 4500 })
  expect(refresh).toHaveBeenCalledWith({ queryKey: ['bugActivities', 'b1'] })
  expect(message.warning).toHaveBeenCalledWith('禅道同步：部分完成')
  expect(message.success).not.toHaveBeenCalled()
  expect(submit).not.toHaveBeenCalled()
}, 10000)

it.each(['succeeded', 'unknown'] as const)('continues the confirmed content sync only after fields are %s', async (status) => {
  const existing: BugZentaoPush = { ...ready, status: 'succeeded', remoteBugId: 50, attachmentStatus: 'failed' }
  const fieldJob: BugZentaoJob = { ...queued, jobId: 'fields', taskType: 'zentao_bug_fields_update' }
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(existing)
  const fields = vi.spyOn(bugsApi, 'submitBugZentaoFields').mockImplementation(async () => {
    vi.mocked(bugsApi.getBugZentaoPush).mockResolvedValue({ ...existing, ready: false, activeJob: fieldJob, latestJob: fieldJob })
    return fieldJob
  })
  const sync = vi.spyOn(bugsApi, 'submitBugZentaoSync').mockResolvedValue(queued)
  const client = mount()
  await userEvent.click(await screen.findByRole('button', { name: '重试推送到禅道' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '确认推送' })).toBeEnabled())
  await userEvent.click(screen.getByRole('combobox', { name: '禅道指派人' }).closest('.ant-select')!)
  await userEvent.click(await screen.findByText('开发甲 (dev)'))
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(fields).toHaveBeenCalledOnce())
  expect(fields.mock.calls[0][1]).toMatchObject({ openedBuild: ['999'], assignedTo: 'dev' })
  expect(sync).not.toHaveBeenCalled()
  vi.mocked(bugsApi.getBugZentaoPush).mockResolvedValue({ ...existing, activeJob: null,
    latestJob: { ...fieldJob, jobStatus: status } })
  await client.invalidateQueries({ queryKey: ['bugZentaoPush', 'b1'] })
  if (status === 'succeeded') await waitFor(() => expect(sync).toHaveBeenCalledOnce())
  else {
    expect(await screen.findByText('版本和指派人修改：结果待核对')).toBeInTheDocument()
    expect(sync).not.toHaveBeenCalled()
  }
})
