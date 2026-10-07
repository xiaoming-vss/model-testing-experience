import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { bugsApi } from '../api/bugs.api'
import type { BugZentaoJob, BugZentaoPush, BugZentaoPushOptions } from '../types'
import { BugZentaoPushPanel } from './BugZentaoPushPanel'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); clients.length = 0; vi.restoreAllMocks(); vi.clearAllMocks() })

const ready: BugZentaoPush = {
  status: 'not_pushed', ready: true, reason: '', remoteBugId: null, errorMessage: '', actorUserId: '', updatedAt: null,
  target: { project: 10, execution: 20, story: 30, projectName: '项目一', executionName: '迭代一', storyName: '需求一' },
  warnings: ['附件和正文图片随本次推送，使用所选影响版本和禅道指派人；状态暂未同步。'],
}
const choices: BugZentaoPushOptions = {
  target: ready.target,
  builds: [{ id: 'trunk', name: '主干 trunk' }, { id: '60', name: 'v1.0' }, { id: '61', name: 'v1.1' }],
  users: [{ account: 'dev', name: '开发甲' }],
}
beforeEach(() => { vi.spyOn(bugsApi, 'getBugZentaoPushOptions').mockResolvedValue({ ...choices,
  current: { remoteBugId: 50, openedBuild: ['trunk'], assignedTo: '' },
}) })
function submitted(result: BugZentaoPush, taskType: BugZentaoJob['taskType'] = 'zentao_bug_sync'): BugZentaoJob {
  const unknown = [result.status, result.attachmentStatus, result.descriptionStatus, result.fieldUpdateStatus].includes('unknown')
  const failed = [result.attachmentStatus, result.descriptionStatus, result.fieldUpdateStatus].includes('failed')
  const job: BugZentaoJob = {
    jobId: crypto.randomUUID(), protocolVersion: 1, taskType,
    jobStatus: taskType === 'zentao_bug_fields_update'
      ? result.fieldUpdateStatus === 'unknown' ? 'unknown' : result.fieldUpdateStatus === 'failed' ? 'failed' : 'succeeded'
      : unknown ? 'unknown' : failed ? 'partial' : result.status === 'failed' ? 'failed' : 'succeeded', result: { steps: {} },
  }
  vi.mocked(bugsApi.getBugZentaoPush).mockResolvedValue({ ...result, activeJob: null, latestJob: job })
  return { ...job, jobStatus: 'queued' }
}
function mount(canWrite = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(<QueryClientProvider client={client}><BugZentaoPushPanel bugId="b1" canWrite={canWrite} /></QueryClientProvider>)
  return client
}

it('shows bound targets and requires a manual confirmation before creating remotely', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(ready)
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync').mockImplementation(async () => {
    const result = { ...ready, status: 'succeeded' as const, ready: true, remoteBugId: 50 }
    vi.mocked(bugsApi.getBugZentaoPush).mockResolvedValue(result)
    return submitted(result)
  })
  mount()
  await waitFor(() => expect(screen.getByRole('button', { name: '推送到禅道' })).toBeEnabled())
  expect(push).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '推送到禅道' }))
  expect(await screen.findByText('迭代一 (#20)')).toBeInTheDocument()
  expect(screen.getByText('主干 trunk')).toBeInTheDocument()
  expect(push).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  expect(await screen.findByText('已推送 · 禅道 Bug #50')).toBeInTheDocument()
  expect(push).toHaveBeenCalledExactlyOnceWith('b1', {
    openedBuild: ['trunk'], assignedTo: '', expectedTarget: choices.target, requestId: expect.any(String),
  })
  expect(screen.getByRole('button', { name: '推送到禅道' })).toBeEnabled()
})

it('prevents pushing when bindings or personal authorization are unavailable', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue({ ...ready, ready: false, reason: '请先保存本人的 Token' })
  mount()
  expect(await screen.findByText('请先保存本人的 Token')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '推送到禅道' })).toBeDisabled()
})

it('does not expose push or reconcile actions to members without write permission', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(ready)
  mount(false)
  expect(await screen.findByText('尚未推送')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '推送到禅道' })).not.toBeInTheDocument()
})

it('offers reconciliation rather than another create when the outcome is unknown', async () => {
  const unknown = { ...ready, status: 'unknown' as const, ready: false }
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(unknown)
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync')
  const reconcile = vi.spyOn(bugsApi, 'reconcileBugZentaoPush').mockImplementation(async () => {
    const result = { ...unknown, status: 'succeeded' as const, remoteBugId: 50 }
    vi.mocked(bugsApi.getBugZentaoPush).mockResolvedValue(result)
    return result
  })
  mount()
  expect(await screen.findByText('结果待核对')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '推送到禅道' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '核对并关联' })).toBeDisabled()
  await userEvent.type(screen.getByLabelText('待核对的禅道 Bug 编号'), '50')
  await userEvent.click(screen.getByRole('button', { name: '核对并关联' }))
  await waitFor(() => expect(reconcile).toHaveBeenCalledExactlyOnceWith('b1', 50))
  expect(push).not.toHaveBeenCalled()
})

it('keeps the existing retry action when a Bug is created but attachments fail', async () => {
  const { message } = await import('@/shared/utils/feedback')
  const failed = { ...ready, status: 'succeeded' as const, remoteBugId: 50,
    attachmentStatus: 'failed' as const, errorMessage: 'Bug 已创建，附件同步失败' }
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(failed)
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync').mockImplementation(async () => submitted(failed))
  mount()
  const retry = await screen.findByRole('button', { name: '重试推送到禅道' })
  await userEvent.click(retry)
  expect(await screen.findByText('补传未成功的附件及正文图片，沿用已关联的禅道 Bug。')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(push).toHaveBeenCalledExactlyOnceWith('b1', { requestId: expect.any(String) }))
  await waitFor(() => expect(message.warning).toHaveBeenCalledWith('禅道同步：部分完成'))
  expect(message.success).not.toHaveBeenCalled()
  expect(screen.getByText('Bug 已创建，附件同步未完成 · 禅道 Bug #50')).toBeInTheDocument()
})

it('does not allow retrying an uncertain attachment write', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue({ ...ready, status: 'succeeded', ready: false,
    remoteBugId: 50, attachmentStatus: 'unknown', errorMessage: '附件结果待核对，请在禅道确认' })
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync')
  mount()
  expect(await screen.findByText('附件结果待核对，请在禅道确认')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '重试推送到禅道' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '核对并关联' })).not.toBeInTheDocument()
  expect(push).not.toHaveBeenCalled()
})

it('offers retry and reports incomplete when only description images are missing', async () => {
  const { message } = await import('@/shared/utils/feedback')
  const result = { ...ready, status: 'succeeded' as const, remoteBugId: 50,
    attachmentStatus: 'succeeded' as const, descriptionStatus: 'failed' as const,
    errorMessage: 'Bug 已创建，正文图片同步失败' }
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(result)
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync').mockImplementation(async () => submitted(result))
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '重试推送到禅道' }))
  await userEvent.click(await screen.findByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(push).toHaveBeenCalledExactlyOnceWith('b1', { requestId: expect.any(String) }))
  expect(message.success).not.toHaveBeenCalled()
  await waitFor(() => expect(message.warning).toHaveBeenCalledWith('禅道同步：部分完成'))
  expect(screen.getByText('Bug 已创建，正文图片同步未完成 · 禅道 Bug #50')).toBeInTheDocument()
})

it('offers readback verification for an uncertain description update', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue({ ...ready, status: 'succeeded',
    remoteBugId: 50, attachmentStatus: 'succeeded', descriptionStatus: 'unknown' })
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '重试推送到禅道' }))
  expect(await screen.findByText('先核对正文图片结果；确认旧图片地址错误后会修复引用，不重复上传文件。')).toBeInTheDocument()
})

it('loads choices only on opening and submits multiple builds with the remote account', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(ready)
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync').mockImplementation(async () => submitted({ ...ready, status: 'succeeded', remoteBugId: 50 }))
  mount()
  await waitFor(() => expect(screen.getByRole('button', { name: '推送到禅道' })).toBeEnabled())
  expect(bugsApi.getBugZentaoPushOptions).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '推送到禅道' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '确认推送' })).toBeEnabled())
  await userEvent.click(screen.getByRole('combobox', { name: '禅道影响版本' }))
  await userEvent.click(await screen.findByText('v1.0'))
  await userEvent.click(await screen.findByText('v1.1'))
  await userEvent.click(screen.getByRole('combobox', { name: '禅道指派人' }).closest('.ant-select')!)
  await userEvent.keyboard('dev')
  await userEvent.click(await screen.findByText('开发甲 (dev)'))
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(push).toHaveBeenCalledExactlyOnceWith('b1', {
    openedBuild: ['60', '61'], assignedTo: 'dev', expectedTarget: choices.target, requestId: expect.any(String),
  }))
})

it('blocks confirmation on a choice lookup failure and supports retry', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(ready)
  vi.mocked(bugsApi.getBugZentaoPushOptions).mockRejectedValueOnce(new Error('本人没有禅道人员查询权限'))
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync')
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '推送到禅道' }))
  expect(await screen.findByText('本人没有禅道人员查询权限')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '确认推送' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: '重新加载候选项' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '确认推送' })).toBeEnabled())
  expect(push).not.toHaveBeenCalled()
})

it('loads editable current remote choices in the existing retry modal', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue({ ...ready, status: 'succeeded', remoteBugId: 50,
    openedBuild: ['60'], assignedTo: 'dev', attachmentStatus: 'failed' })
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '重试推送到禅道' }))
  expect(await screen.findByRole('combobox', { name: '禅道影响版本' })).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: '禅道指派人' })).toBeInTheDocument()
  await waitFor(() => expect(bugsApi.getBugZentaoPushOptions).toHaveBeenCalledWith('b1'))
  expect(screen.queryByRole('button', { name: '修改禅道版本和指派人' })).not.toBeInTheDocument()
})

it('edits an existing Bug using current remote values in the push modal', async () => {
  const existing = { ...ready, status: 'succeeded' as const, ready: true, remoteBugId: 50,
    openedBuild: ['trunk'], assignedTo: 'local-old-value' }
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(existing)
  vi.mocked(bugsApi.getBugZentaoPushOptions).mockResolvedValue({ ...choices,
    users: [...choices.users, { account: 'dev2', name: '开发乙' }],
    current: { remoteBugId: 50, openedBuild: ['60'], assignedTo: 'dev' },
  })
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync')
  const update = vi.spyOn(bugsApi, 'submitBugZentaoFields').mockImplementation(async () => {
    const result = { ...existing, openedBuild: ['60', '61'], assignedTo: 'dev2', fieldUpdateStatus: 'succeeded' as const }
    vi.mocked(bugsApi.getBugZentaoPush).mockResolvedValue(result)
    return submitted(result, 'zentao_bug_fields_update')
  })
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '推送到禅道' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '确认推送' })).toBeEnabled())
  expect(screen.getByText('v1.0')).toBeInTheDocument()
  expect(screen.getByText('开发甲 (dev)')).toBeInTheDocument()
  expect(screen.queryByText('local-old-value')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('combobox', { name: '禅道影响版本' }))
  await userEvent.click(await screen.findByText('v1.1'))
  await userEvent.click(screen.getByRole('combobox', { name: '禅道指派人' }).closest('.ant-select')!)
  await userEvent.click(await screen.findByText('开发乙 (dev2)'))
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(update).toHaveBeenCalledExactlyOnceWith('b1', {
    openedBuild: ['60', '61'], assignedTo: 'dev2', expectedTarget: choices.target, requestId: expect.any(String),
    expectedRemoteBugId: 50, expectedOpenedBuild: ['60'], expectedAssignedTo: 'dev',
  }))
  expect(push).not.toHaveBeenCalled()
})

it('does not expose remote field editing to read-only users', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue({ ...ready, status: 'succeeded', remoteBugId: 50 })
  mount(false)
  expect(await screen.findByText('已推送 · 禅道 Bug #50')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '修改禅道版本和指派人' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '推送到禅道' })).not.toBeInTheDocument()
})

it('requires a readable current remote baseline before saving an existing Bug', async () => {
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue({ ...ready, status: 'succeeded', remoteBugId: 50 })
  vi.mocked(bugsApi.getBugZentaoPushOptions).mockRejectedValue(new Error('禅道当前值读取失败'))
  const update = vi.spyOn(bugsApi, 'submitBugZentaoFields')
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '推送到禅道' }))
  expect(await screen.findByText('禅道当前值读取失败')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '确认推送' })).toBeDisabled()
  expect(update).not.toHaveBeenCalled()
})

it('updates changed fields and supplements content from one confirmation in order', async () => {
  const pending = { ...ready, status: 'succeeded' as const, remoteBugId: 50,
    attachmentStatus: 'failed' as const, descriptionStatus: 'failed' as const }
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(pending)
  const updated = { ...pending, openedBuild: ['60'], fieldUpdateStatus: 'succeeded' as const }
  const update = vi.spyOn(bugsApi, 'submitBugZentaoFields').mockImplementation(async () => submitted(updated, 'zentao_bug_fields_update'))
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync').mockImplementation(async () => {
    const done = { ...updated, ready: false, attachmentStatus: 'succeeded' as const, descriptionStatus: 'succeeded' as const }
    vi.mocked(bugsApi.getBugZentaoPush).mockResolvedValue(done)
    return submitted(done)
  })
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '重试推送到禅道' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '确认推送' })).toBeEnabled())
  expect(screen.queryByRole('button', { name: '修改禅道版本和指派人' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('combobox', { name: '禅道影响版本' }))
  await userEvent.click(await screen.findByText('v1.0'))
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(push).toHaveBeenCalledExactlyOnceWith('b1', { requestId: expect.any(String) }))
  expect(update).toHaveBeenCalledOnce()
  expect(update.mock.invocationCallOrder[0]).toBeLessThan(push.mock.invocationCallOrder[0])
  expect(await screen.findByText('已推送 · 禅道 Bug #50')).toBeInTheDocument()
})

it('shows the uncertain field result and does not supplement content', async () => {
  const { message } = await import('@/shared/utils/feedback')
  const pending = { ...ready, status: 'succeeded' as const, remoteBugId: 50, attachmentStatus: 'failed' as const }
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(pending)
  const uncertain = { ...pending, fieldUpdateStatus: 'unknown' as const, fieldUpdateError: '版本和指派人结果待核对' }
  const update = vi.spyOn(bugsApi, 'submitBugZentaoFields').mockImplementation(async () => {
    vi.mocked(bugsApi.getBugZentaoPush).mockResolvedValue(uncertain)
    return submitted(uncertain, 'zentao_bug_fields_update')
  })
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync')
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '重试推送到禅道' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '确认推送' })).toBeEnabled())
  await userEvent.click(screen.getByRole('combobox', { name: '禅道影响版本' }))
  await userEvent.click(await screen.findByText('v1.0'))
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(update).toHaveBeenCalledOnce())
  await waitFor(() => expect(message.warning).toHaveBeenCalledWith('版本和指派人修改：结果待核对'))
  expect(push).not.toHaveBeenCalled()
  // JSDOM does not run AntD's exit animation; verify that the modal is closing.
  await waitFor(() => expect(screen.getByRole('dialog', { name: '推送到禅道' })).toHaveClass('ant-zoom-leave'))
})

it('does not write remotely when an already synchronized Bug has no field changes', async () => {
  const { message } = await import('@/shared/utils/feedback')
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue({ ...ready, status: 'succeeded', ready: true, remoteBugId: 50 })
  const push = vi.spyOn(bugsApi, 'submitBugZentaoSync')
  const update = vi.spyOn(bugsApi, 'submitBugZentaoFields')
  mount()
  await userEvent.click(await screen.findByRole('button', { name: '推送到禅道' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '确认推送' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: '确认推送' }))
  await waitFor(() => expect(message.success).toHaveBeenCalledWith('已关联禅道 Bug #50'))
  expect(push).not.toHaveBeenCalled()
  expect(update).not.toHaveBeenCalled()
})
