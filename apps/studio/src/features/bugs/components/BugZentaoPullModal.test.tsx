import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { bugsApi } from '../api/bugs.api'
import type { ZentaoRemoteGroup, ZentaoRemotePreview } from '../types'
import { BugZentaoPullModal } from './BugZentaoPullModal'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); clients.length = 0; vi.restoreAllMocks(); vi.clearAllMocks() })

function group(overrides: Partial<ZentaoRemoteGroup>): ZentaoRemoteGroup {
  return { group: 'profile', state: 'remote_changed', local: {}, remote: {}, baseline: null, reason: '', ...overrides }
}

function previewData(overrides: Partial<ZentaoRemotePreview> = {}): ZentaoRemotePreview {
  return {
    remoteBugId: 50,
    remoteDigest: 'digest-abcdef',
    linkedSource: 'push',
    groups: [
      group({ group: 'profile', state: 'conflict', local: { title: '本地标题', severity: 'serious', priority: 'medium' }, remote: { title: '远端标题', severity: 'serious', priority: 'low' }, reason: '两端都已修改且内容不同，请选择保留哪一侧' }),
      group({ group: 'status', state: 'synced', local: { status: 'active', confirmed: false }, remote: { status: 'active', confirmed: false } }),
      group({ group: 'description', state: 'pending_files', local: { digest: 'a' }, remote: { digest: 'b', hasImages: true, hasContent: true }, reason: '远端正文包含图片，需等待文件管线反向导入后一起应用（R30）' }),
      group({ group: 'assignee', state: 'manual', local: { userId: 'u1' }, remote: { account: 'dev' }, reason: '禅道责任人为账号体系，需要人工映射为平台成员后应用（Q05）' }),
    ],
    ...overrides,
  }
}

beforeEach(() => {
  vi.spyOn(bugsApi, 'getBugZentaoRemote').mockResolvedValue(previewData())
  vi.spyOn(bugsApi, 'getBugOptions').mockResolvedValue({
    members: [{ userId: 'u1', name: '开发甲' }],
    sprints: [],
  })
})

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(
    <QueryClientProvider client={client}>
      <BugZentaoPullModal open bugId="b1" projectId="p1" onClose={vi.fn()} />
    </QueryClientProvider>,
  )
}

it('shows per-group two-side comparison with states and no-op defaults', async () => {
  mount()
  await screen.findByText(/远端标题/)
  expect(screen.getByText('两端冲突')).toBeInTheDocument()
  expect(screen.getByText('图片待文件管线')).toBeInTheDocument()
  expect(screen.getByText('需人工映射')).toBeInTheDocument()
  // 无差异的组不提供方向选择。
  expect(screen.queryByLabelText('同步方向-状态')).not.toBeInTheDocument()
})

it('rejects applying assignee without choosing a platform member (Q05)', async () => {
  const pull = vi.spyOn(bugsApi, 'pullBugZentao')
  mount()
  await screen.findByText(/远端标题/)
  const profileChoice = screen.getByLabelText('同步方向-基本信息')
  await userEvent.click(within(profileChoice).getByText('应用禅道'))
  const assigneeChoice = screen.getByLabelText('同步方向-责任人')
  await userEvent.click(within(assigneeChoice).getByText('应用禅道'))
  await userEvent.click(screen.getByRole('button', { name: '确认同步' }))
  expect(pull).not.toHaveBeenCalled()
  await userEvent.click(screen.getByLabelText('映射平台责任人'))
  await userEvent.click(await screen.findByText('开发甲'))
  await userEvent.click(screen.getByRole('button', { name: '确认同步' }))
  await waitFor(() => expect(pull).toHaveBeenCalledWith('b1', {
    remoteDigest: 'digest-abcdef',
    groups: [
      { group: 'profile', action: 'apply_remote' },
      { group: 'status', action: 'keep_local' },
      { group: 'description', action: 'keep_local' },
      { group: 'assignee', action: 'apply_remote', assigneeUserId: 'u1' },
    ],
  }))
})
