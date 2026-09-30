import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { BugSubmitPage } from './BugSubmitPage'
vi.mock('@/shared/components/RichTextEditor', () => ({ RichTextEditor: () => <div>富文本编辑器</div> }))
vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
function list<T>(items: T[]) { return Object.assign([...items], { items, total: items.length }) }
afterEach(() => { cleanup(); vi.restoreAllMocks() })
it('从执行记录提交成功后留在详情，不触发取消返回', async () => {
  useWorkbenchStore.setState({ activeProjectId: 'other-project' })
  const project = { projectId: 'source-project', name: '来源项目', permissions: ['write' as const] }
  vi.spyOn(api, 'getProjects').mockResolvedValue(list([project]))
  vi.spyOn(api, 'getSprints').mockResolvedValue(list([{ sprintId: 's1', name: '迭代一', status: 'running' as const }]))
  vi.spyOn(api, 'getRequirements').mockResolvedValue(list([]))
  vi.spyOn(api, 'getProjectMembers').mockResolvedValue(list([{ userId: 'u1', name: '小明', role: 'owner' as const }]))
  const create = vi.spyOn(api, 'createBug').mockResolvedValue({ bugId: 'created-bug' } as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const source = new URLSearchParams({ projectId: 'source-project', orderId: 'o1', entryId: 'e1',
    sprintId: 's1', title: '执行失败', description: '<p>复现问题</p>' })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/origin', `/bugs/new?${source}`]} initialIndex={1}>
    <Routes><Route path="/origin" element={<div>不应返回的来源页</div>} />
      <Route path="/bugs/new" element={<BugSubmitPage />} />
      <Route path="/bugs/:bugId" element={<div>新建 Bug 详情</div>} /></Routes>
  </MemoryRouter></QueryClientProvider>)
  await waitFor(() => expect(screen.getByLabelText('归属项目（只读）')).toHaveTextContent('来源项目'))
  await userEvent.click(await screen.findByLabelText('责任人'))
  await userEvent.click(await screen.findByText('小明'))
  await userEvent.click(screen.getByRole('button', { name: '立即提交缺陷' }))
  expect(await screen.findByText('新建 Bug 详情')).toBeInTheDocument()
  expect(screen.queryByText('不应返回的来源页')).not.toBeInTheDocument()
  expect(create).toHaveBeenCalledWith('source-project', expect.objectContaining({ sourceOrderId: 'o1', sourceEntryId: 'e1', foundSprintId: 's1', plannedFixSprintId: 's1' }))
  client.clear()
})
