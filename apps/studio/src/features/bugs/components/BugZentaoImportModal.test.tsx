import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { bugsApi } from '../api/bugs.api'
import type { ZentaoBugCandidate, ZentaoBugImportPreview, ZentaoBugImportResult } from '../types'
import { BugZentaoImportModal } from './BugZentaoImportModal'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); clients.length = 0; vi.restoreAllMocks(); vi.clearAllMocks() })

const candidates: ZentaoBugCandidate[] = [
  { remoteBugId: 50, title: '登录失败', status: 'active', severity: '1', priority: '3', assignedTo: 'dev', openedBy: 'tester', openedDate: '', execution: 20, story: 30, linked: false },
  { remoteBugId: 51, title: '重复推送', status: 'active', severity: '3', priority: '4', assignedTo: '', openedBy: 'tester', openedDate: '', execution: 20, story: 0, linked: true },
]

function preview(overrides: Partial<ZentaoBugImportPreview> = {}): ZentaoBugImportPreview {
  return {
    remoteBugId: 50, state: 'ready', title: '登录失败',
    snapshot: {}, converted: { severity: 'fatal', priority: 'medium', status: 'active', foundSprintId: 'sprint-1', requirementId: '' },
    description: { hasImages: false, hasContent: true },
    pending: [{ field: 'assigneeUserId', reason: '请选择平台责任人（Q05：不按账号自动映射）' }],
    errorMessage: '', ...overrides,
  }
}

beforeEach(() => {
  vi.spyOn(bugsApi, 'listZentaoBugCandidates').mockResolvedValue({ total: candidates.length, items: candidates } as never)
  vi.spyOn(bugsApi, 'getBugOptions').mockResolvedValue({
    members: [{ userId: 'u1', name: '开发甲' }],
    sprints: [{ sprintId: 'sprint-1', name: '迭代一' }],
  })
  vi.spyOn(bugsApi, 'previewZentaoBugImport').mockResolvedValue({ items: [preview()] })
})

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(
    <QueryClientProvider client={client}>
      <BugZentaoImportModal open projectId="p1" onClose={vi.fn()} />
    </QueryClientProvider>,
  )
}

it('lists candidates with linked rows unselectable', async () => {
  mount()
  expect(await screen.findByText('登录失败')).toBeInTheDocument()
  const linkedRow = screen.getByText('重复推送').closest('tr') as HTMLElement
  expect(within(linkedRow).getByRole('checkbox')).toBeDisabled()
  const freeRow = screen.getByText('登录失败').closest('tr') as HTMLElement
  expect(within(freeRow).getByRole('checkbox')).toBeEnabled()
})

it('requires assignee and sprint before importing and reports per-item results', async () => {
  const results: ZentaoBugImportResult[] = [
    { remoteBugId: 50, status: 'success', bugId: 'b1', bugNo: 7, title: '登录失败', errorMessage: '', pending: [] },
  ]
  const importSpy = vi.spyOn(bugsApi, 'importZentaoBugs').mockResolvedValue({ items: results })
  mount()
  const row = ((await screen.findByText('登录失败')) as HTMLElement).closest('tr') as HTMLElement
  await userEvent.click(within(row).getByRole('checkbox'))
  expect(await screen.findByText('导入确认')).toBeInTheDocument()
  // 未选择责任人/迭代时导入按钮保持禁用（Q05/Q06）。
  expect(screen.getByRole('button', { name: /导入/ })).toBeDisabled()
  // 发现迭代由绑定解析预填；责任人必须人工选择。
  expect(screen.getByTitle('迭代一')).toBeInTheDocument()
  await userEvent.click(screen.getByLabelText('责任人-50'))
  await userEvent.click(await screen.findByText('开发甲'))
  await userEvent.click(screen.getByRole('button', { name: /导入/ }))
  await waitFor(() => expect(importSpy).toHaveBeenCalledWith('p1', {
    requestId: expect.any(String),
    items: [{ remoteBugId: 50, assigneeUserId: 'u1', foundSprintId: 'sprint-1' }],
  }))
  expect(await screen.findByText(/导入成功/)).toBeInTheDocument()
})

it('blocks items whose preview is not ready', async () => {
  vi.spyOn(bugsApi, 'previewZentaoBugImport').mockResolvedValue({
    items: [preview({ state: 'pending_files', pending: [{ field: 'description', reason: '正文包含图片，需等待文件管线反向导入后一起应用' }] })],
  })
  const importSpy = vi.spyOn(bugsApi, 'importZentaoBugs')
  mount()
  const row = ((await screen.findByText('登录失败')) as HTMLElement).closest('tr') as HTMLElement
  await userEvent.click(within(row).getByRole('checkbox'))
  expect(await screen.findByText(/正文包含图片/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /导入/ })).toBeDisabled()
  expect(importSpy).not.toHaveBeenCalled()
})
