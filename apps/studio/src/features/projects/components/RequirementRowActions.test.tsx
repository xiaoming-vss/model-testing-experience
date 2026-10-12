import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { seedOwnerProject } from '@/test/projectAccess'
import { RequirementRowActions } from './RequirementRowActions'

const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.splice(0).forEach(client => client.clear()) })
function mount(manage = true, write = true) {
  const client = new QueryClient(); clients.push(client); seedOwnerProject(client)
  if (!write) client.setQueryData(['projectAccess', 'project-1'], { projectId: 'project-1', role: 'viewer', permissions: ['read'] })
  const callbacks = { onEdit: vi.fn(), onBind: vi.fn(), onCodeBind: vi.fn(), onDelete: vi.fn().mockResolvedValue(undefined) }
  render(<TestThemeProvider><QueryClientProvider client={client}><RequirementRowActions name="示例需求" canManage={manage} canWrite={write} deleting={false} {...callbacks} /></QueryClientProvider></TestThemeProvider>)
  return callbacks
}
it('删除需二次确认，取消不提交；禅道绑定仍调用原入口', async () => {
  const callbacks = mount()
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /更多/ }))
  await user.click(screen.getByRole('menuitem', { name: '禅道绑定' }))
  expect(callbacks.onBind).toHaveBeenCalledOnce()
  await user.click(screen.getByRole('button', { name: /更多/ }))
  await user.click(screen.getByRole('menuitem', { name: '删除需求' }))
  const dialog = await screen.findByRole('dialog')
  expect(dialog).toHaveTextContent('示例需求')
  expect(callbacks.onDelete).not.toHaveBeenCalled()
  await user.click(within(dialog).getByRole('button', { name: /取\s*消/ }))
  expect(callbacks.onDelete).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: /更多/ }))
  await user.click(screen.getByRole('menuitem', { name: '删除需求' }))
  await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /删\s*除/ }))
  expect(callbacks.onDelete).toHaveBeenCalledOnce()
})
it('普通成员不能从菜单绕过绑定权限', async () => {
  const callbacks = mount(false)
  await userEvent.setup().click(screen.getByRole('button', { name: /更多/ }))
  expect(screen.getByRole('menuitem', { name: '禅道绑定' })).toHaveAttribute('aria-disabled', 'true')
  expect(screen.getByRole('menuitem', { name: '代码绑定' })).toHaveAttribute('aria-disabled', 'true')
  expect(callbacks.onBind).not.toHaveBeenCalled()
})
it('只读成员不可编辑或打开写操作菜单', () => {
  mount(false, false)
  expect(screen.getByRole('button', { name: '编辑需求' })).toBeDisabled()
  expect(screen.getByRole('button', { name: /更多/ })).toBeDisabled()
})
