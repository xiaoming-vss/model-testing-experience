import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { seedOwnerProject } from '@/test/projectAccess'
import type { Bug } from '../types'
import { BugInlineEditor } from './BugInlineEditor'
vi.mock('@/shared/components/RichTextEditor', () => ({ RichTextEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => <textarea aria-label="问题描述" value={value} onChange={(event) => onChange(event.target.value)} /> }))
vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })
const bug = { bugId: 'b', bugNo: 1, projectId: 'project-1', title: '原有标题', descriptionHtml: '<p>原有描述</p>',
  severity: 'normal', priority: 'medium', status: 'pending', foundSprintId: 's', plannedFixSprintId: 's', reporterUserId: 'u', assigneeUserId: 'u', attachments: [] } as unknown as Bug
function setup(value = bug) {
  vi.spyOn(api, 'getProjects').mockResolvedValue([] as never)
  vi.spyOn(api, 'getProjectMembers').mockResolvedValue([] as never)
  vi.spyOn(api, 'getSprints').mockResolvedValue([] as never)
  const update = vi.spyOn(api, 'updateBug').mockResolvedValue(bug)
  const close = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  render(<QueryClientProvider client={client}><MemoryRouter><BugInlineEditor bug={value}
    sprintNames={new Map([['s', 'v1.2.0']])} resolveUserName={() => '小明'} onClose={close} onBack={vi.fn()} /></MemoryRouter></QueryClientProvider>)
  return { update, close, client }
}
it('页内编辑后统一保存到原 Bug，保留描述', async () => {
  const { update, close, client } = setup()
  const title = await screen.findByLabelText('标题')
  await userEvent.clear(title)
  await userEvent.type(title, '修改后标题')
  await userEvent.click(screen.getByRole('button', { name: '保存修改' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('b', expect.objectContaining({ title: '修改后标题', descriptionHtml: '<p>原有描述</p>' })))
  await waitFor(() => expect(close).toHaveBeenCalled())
  client.clear()
})
it('取消退出编辑，不发送修改请求', async () => {
  const { update, close, client } = setup()
  await userEvent.type(await screen.findByLabelText('标题'), '未保存')
  await userEvent.click(screen.getByRole('button', { name: '取 消' }))
  expect(close).toHaveBeenCalled()
  expect(update).not.toHaveBeenCalled()
  client.clear()
})

it('已有附件先从表单移除，保存时才提交移除列表', async () => {
  const { update, client } = setup({ ...bug, attachments: [{ fileId: 'file-1', filename: 'log.txt', size: 10 }] } as Bug)
  await userEvent.click(await screen.findByTitle('Remove file'))
  await waitFor(() => expect(screen.queryByText('log.txt')).not.toBeInTheDocument(), { timeout: 4000 })
  expect(update).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '保存修改' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('b', expect.objectContaining({ removedAttachmentFileIds: ['file-1'] })))
  client.clear()
})
it('移除已有附件后取消，不提交删除', async () => {
  const { update, close, client } = setup({ ...bug, attachments: [{ fileId: 'file-1', filename: 'log.txt', size: 10 }] } as Bug)
  await userEvent.click(await screen.findByTitle('Remove file'))
  await userEvent.click(screen.getByRole('button', { name: '取 消' }))
  expect(close).toHaveBeenCalled()
  expect(update).not.toHaveBeenCalled()
  client.clear()
})
