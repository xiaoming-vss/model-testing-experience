import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { bugsApi } from '../api/bugs.api'
import type { ZentaoBugCandidate, ZentaoBugImportPreview, ZentaoBugImportResult } from '../types'
import { BugZentaoImportModal } from './BugZentaoImportModal'

vi.mock('@/shared/utils/feedback', () => ({ bindFeedbackMessage: vi.fn(), message: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
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
  vi.spyOn(bugsApi, 'listZentaoBugCandidates').mockResolvedValue({
    scope: 'execution', executionId: 20, total: candidates.length, items: candidates,
  } as never)
  vi.spyOn(bugsApi, 'getBugOptions').mockResolvedValue({
    members: [{ userId: 'u1', name: '开发甲' }],
    sprints: [{ sprintId: 'sprint-1', name: '迭代一' }],
  })
  vi.spyOn(bugsApi, 'previewZentaoBugImport').mockResolvedValue({ items: [preview()] })
})

function mount(defaultSprintId?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(
    <QueryClientProvider client={client}><TestThemeProvider>
      <BugZentaoImportModal open projectId="p1" defaultSprintId={defaultSprintId} onClose={vi.fn()} />
    </TestThemeProvider></QueryClientProvider>,
  )
}

it('lists candidates with linked rows unselectable', async () => {
  mount()
  expect(await screen.findByText('登录失败')).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: '每页条数' })).toBeInTheDocument()
  // 禅道原始值带平台标签展示，便于核对（R23）。
  expect(await screen.findByText('致命 (1)')).toBeInTheDocument()
  expect(screen.getByText('中 (3)')).toBeInTheDocument()
  expect(screen.getByText('低 (4)')).toBeInTheDocument()
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
  await userEvent.click(screen.getByRole('button', { name: '下一步' }))
  expect(await screen.findByText('批量设置')).toBeInTheDocument()
  // 未选择责任人/迭代时导入按钮保持禁用（Q05/Q06），按钮旁提示未分配责任人。
  expect(screen.getByRole('button', { name: /导入/ })).toBeDisabled()
  expect(await screen.findByText('未分配责任人')).toBeInTheDocument()
  // 预览 pending 不再展示：责任人提示随选择更新，含图说明放到导入结果里（R41）。
  expect(screen.queryByText(/请选择平台责任人/)).not.toBeInTheDocument()
  // 发现迭代由绑定解析预填；责任人必须人工选择。
  expect(screen.getByTitle('迭代一')).toBeInTheDocument()
  await userEvent.click(screen.getByLabelText('责任人-50'))
  await userEvent.click(await screen.findByText('开发甲'))
  await waitFor(() => expect(screen.queryByText('未分配责任人')).not.toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: /导入/ }))
  await waitFor(() => expect(importSpy).toHaveBeenCalledWith('p1', {
    requestId: expect.any(String),
    items: [{ remoteBugId: 50, assigneeUserId: 'u1', foundSprintId: 'sprint-1' }],
  }))
  expect(await screen.findByText(/导入成功/)).toBeInTheDocument()
})

it('prefills the found sprint with the current iteration when binding is unresolved', async () => {
  vi.spyOn(bugsApi, 'previewZentaoBugImport').mockResolvedValue({
    items: [preview({ converted: { severity: 'fatal', priority: 'medium', status: 'active' } })],
  })
  mount('sprint-1')
  const row = ((await screen.findByText('登录失败')) as HTMLElement).closest('tr') as HTMLElement
  await userEvent.click(within(row).getByRole('checkbox'))
  await userEvent.click(screen.getByRole('button', { name: '下一步' }))
  expect(await screen.findByText('批量设置')).toBeInTheDocument()

  expect(screen.getByTitle('迭代一')).toBeInTheDocument()
  const importSpy = vi.spyOn(bugsApi, 'importZentaoBugs')
  await userEvent.click(screen.getByLabelText('责任人-50'))
  await userEvent.click(await screen.findByText('开发甲'))
  await userEvent.click(screen.getByRole('button', { name: /导入/ }))
  await waitFor(() => expect(importSpy).toHaveBeenCalledWith('p1', {
    requestId: expect.any(String),
    items: [{ remoteBugId: 50, assigneeUserId: 'u1', foundSprintId: 'sprint-1' }],
  }))
})

it('blocks items whose preview is not ready', async () => {
  vi.spyOn(bugsApi, 'previewZentaoBugImport').mockResolvedValue({
    items: [preview({ state: 'pending_files', pending: [{ field: 'description', reason: '正文包含图片，需等待文件管线反向导入后一起应用' }] })],
  })
  const importSpy = vi.spyOn(bugsApi, 'importZentaoBugs')
  mount()
  const row = ((await screen.findByText('登录失败')) as HTMLElement).closest('tr') as HTMLElement
  await userEvent.click(within(row).getByRole('checkbox'))
  await userEvent.click(screen.getByRole('button', { name: '下一步' }))
  expect(await screen.findByText(/正文包含图片/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /导入/ })).toBeDisabled()
  expect(importSpy).not.toHaveBeenCalled()
})


it('每页条数始终可选，切换后从第一页请求并保留已选候选', async () => {
  vi.mocked(bugsApi.listZentaoBugCandidates).mockResolvedValue({
    scope: 'execution', executionId: 20, total: 100, items: candidates,
  })
  mount('sprint-1')
  const user = userEvent.setup()
  const row = (await screen.findByText('登录失败')).closest('tr')!
  await user.click(within(row).getByRole('checkbox'))
  expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled()
  await user.click(screen.getByTitle('2'))
  await waitFor(() => expect(bugsApi.listZentaoBugCandidates).toHaveBeenLastCalledWith('p1', expect.objectContaining({ page: 2, pageSize: 10 })))
  const sizeSelect = screen.getByRole('combobox', { name: '每页条数' })
  await waitFor(() => expect(sizeSelect).toBeEnabled())
  await user.click(sizeSelect)
  await user.click(await screen.findByText('50 条/页', { selector: '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content' }))
  await waitFor(() => expect(bugsApi.listZentaoBugCandidates).toHaveBeenLastCalledWith('p1', expect.objectContaining({ page: 1, pageSize: 50 })))
  expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled()
  expect(within(screen.getByText('登录失败').closest('tr')!).getByRole('checkbox')).toBeChecked()
})


it('显示100条时全选也不超过20条，并允许取消后重新选择', async () => {
  const rows = Array.from({ length: 100 }, (_, i) => ({ ...candidates[0], remoteBugId: i + 1, title: `候选 ${i + 1}` }))
  vi.mocked(bugsApi.listZentaoBugCandidates).mockResolvedValue({ scope: 'execution', executionId: 20, total: 100, items: rows })
  mount()
  const user = userEvent.setup()
  await screen.findByText('候选 1')
  await user.click(screen.getByRole('combobox', { name: '每页条数' }))
  await user.click(await screen.findByText('100 条/页', { selector: '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content' }))
  await waitFor(() => expect(bugsApi.listZentaoBugCandidates).toHaveBeenLastCalledWith('p1', expect.objectContaining({ pageSize: 100 })))
  await user.click(screen.getAllByRole('checkbox')[0])
  await waitFor(() => expect(bugsApi.previewZentaoBugImport).toHaveBeenLastCalledWith('p1', Array.from({ length: 20 }, (_, i) => i + 1)))
  const checkbox = (title: string) => within(screen.getByText(title).closest('tr')!).getByRole('checkbox')
  expect(checkbox('候选 21')).toBeDisabled()
  await user.click(checkbox('候选 1'))
  expect(checkbox('候选 21')).toBeEnabled()
  await user.click(checkbox('候选 21'))
  await waitFor(() => expect(bugsApi.previewZentaoBugImport).toHaveBeenLastCalledWith('p1', Array.from({ length: 20 }, (_, i) => i + 2)))
  expect(vi.mocked(bugsApi.previewZentaoBugImport).mock.calls.every(([, ids]) => ids.length <= 20)).toBe(true)
})

it('预览请求失败仅显示一条集中错误', async () => {
  vi.mocked(bugsApi.listZentaoBugCandidates).mockResolvedValue({ scope: 'execution', executionId: 20, total: 2, items: candidates.map(row => ({ ...row, linked: false })) })
  vi.mocked(bugsApi.previewZentaoBugImport).mockRejectedValue(new Error('预览服务暂不可用'))
  mount()
  await screen.findByText('登录失败')
  await userEvent.click(screen.getAllByRole('checkbox')[0])
  await userEvent.click(screen.getByRole('button', { name: '下一步' }))
  await screen.findByText('预览服务暂不可用')
  expect(screen.getAllByText('预览服务暂不可用')).toHaveLength(1)
  expect(screen.getByRole('button', { name: '重试预览' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /导入/ })).toBeDisabled()
})


it('批量设置后允许逐条修改，返回选择步骤仍保留配置', async () => {
  vi.mocked(bugsApi.listZentaoBugCandidates).mockResolvedValue({ scope: 'execution', executionId: 20, total: 2,
    items: candidates.map(row => ({ ...row, linked: false })) })
  vi.mocked(bugsApi.previewZentaoBugImport).mockResolvedValue({ items: [preview(), preview({remoteBugId: 51, title: '重复推送'})] })
  vi.mocked(bugsApi.getBugOptions).mockResolvedValue({ members: [{userId: 'u1', name: '开发甲'}, {userId: 'u2', name: '开发乙'}],
    sprints: [{sprintId: 'sprint-1', name: '迭代一'}, {sprintId: 'sprint-2', name: '迭代二'}] })
  const importSpy = vi.spyOn(bugsApi, 'importZentaoBugs').mockResolvedValue({items: []})
  mount('sprint-1')
  const user = userEvent.setup()
  await screen.findByText('登录失败')
  await user.click(screen.getAllByRole('checkbox')[0])
  await user.click(screen.getByRole('button', {name: '下一步'}))
  expect(screen.queryByLabelText('候选标题搜索')).not.toBeInTheDocument()
  await user.click(screen.getByLabelText('批量责任人'))
  await user.click(await screen.findByText('开发甲', {selector: '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content'}))
  await user.click(screen.getByLabelText('批量发现迭代'))
  await user.click(await screen.findByText('迭代二', {selector: '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content'}))
  await user.click(screen.getByRole('button', {name: '应用到全部 2 条'}))
  await waitFor(() => expect(screen.getByRole('button', {name: '导入 2 条'})).toBeEnabled())
  await user.click(screen.getByLabelText('责任人-51'))
  await user.click(await screen.findByText('开发乙', {selector: '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content'}))
  await user.click(screen.getByRole('button', {name: '上一步'}))
  expect(screen.getByLabelText('候选标题搜索')).toBeInTheDocument()
  await user.click(screen.getByRole('button', {name: '下一步'}))
  await user.click(screen.getByRole('button', {name: '导入 2 条'}))
  await waitFor(() => expect(importSpy).toHaveBeenCalledWith('p1', expect.objectContaining({items: [
    {remoteBugId: 50, assigneeUserId: 'u1', foundSprintId: 'sprint-2'},
    {remoteBugId: 51, assigneeUserId: 'u2', foundSprintId: 'sprint-2'},
  ]})))
})
