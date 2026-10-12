import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { seedOwnerProject } from '@/test/projectAccess'
import { SprintBoard } from './SprintBoard'
import type { Sprint } from '../types'

const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.splice(0).forEach(client => client.clear()) })
function mount(sprints: Sprint[], viewer = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  seedOwnerProject(client)
  if (viewer) client.setQueryData(['projectAccess', 'project-1'], { projectId: 'project-1', role: 'viewer', permissions: ['read'] })
  const onDelete = vi.fn()
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter><SprintBoard projectId="project-1"
    sprints={sprints} loading={false} refreshing={false} error={null} renderBinding={() => '未绑定'}
    onRefresh={vi.fn()} onEdit={vi.fn()} onBind={vi.fn()} onDelete={onDelete} /></MemoryRouter></QueryClientProvider></TestThemeProvider>)
  return { onDelete }
}
it('全量状态排序先于分页，历史接口排在最后的进行中迭代仍在首页', async () => {
  const completed: Sprint[] = Array.from({ length: 21 }, (_, index) => ({ sprintId: `done-${index}`, name: `历史${index}`, status: 'completed' }))
  mount([...completed, { sprintId: 'active', name: '当前迭代', status: 'running' }, { sprintId: 'next', name: '下个迭代', status: 'planned' }])
  expect(screen.getAllByRole('link')[0]).toHaveTextContent('当前迭代')
  expect(screen.getAllByRole('link')[1]).toHaveTextContent('下个迭代')
  expect(screen.getAllByRole('link')).toHaveLength(20)
  expect(screen.queryByRole('combobox', { name: '迭代状态' })).not.toBeInTheDocument()
  fireEvent.click(document.querySelector('.ant-pagination-item-2')!)
  expect(screen.queryByRole('link', { name: '当前迭代' })).not.toBeInTheDocument()
  expect(screen.getAllByRole('link')).toHaveLength(3)

})
it('未知状态不丢失，删除仍须确认', async () => {
  const { onDelete } = mount([{ sprintId: 'odd', name: '待迁移迭代', status: 'unknown' as Sprint['status'] }])
  expect(screen.getByRole('link', { name: '待迁移迭代' })).toBeInTheDocument()
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '删除' }))
  expect(onDelete).not.toHaveBeenCalled()
  // The icon's hover tooltip can coexist with the confirmation popup.
  const confirmation = (await screen.findByText('确认删除该迭代？')).closest('[role="tooltip"]')!
  await user.click(within(confirmation as HTMLElement).getByRole('button', { name: /删\s*除/ }))
  await waitFor(() => expect(onDelete).toHaveBeenCalledWith('odd'))
})
it('只读成员保留详情链接但不能编辑、绑定或删除', () => {
  mount([{ sprintId: 'active', name: '当前迭代', status: 'running' }], true)
  expect(screen.getByRole('link', { name: '当前迭代' })).toBeInTheDocument()
  for (const name of ['编辑', '禅道绑定', '删除']) expect(screen.getByRole('button', { name })).toBeDisabled()
})
