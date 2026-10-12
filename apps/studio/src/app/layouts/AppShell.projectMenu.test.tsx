import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { AppShell } from './AppShell'
import { TestThemeProvider } from '@/test/TestThemeProvider'

const clients: QueryClient[] = []
afterEach(() => {
  cleanup()
  clients.splice(0).forEach(client => client.clear())
  vi.restoreAllMocks()
  useAuthStore.setState({ token: null, user: null })
  useWorkbenchStore.getState().setActiveProjectId(undefined)
})

function mount(role = 'owner', path = '/projects?board=requirements') {
  useAuthStore.setState({ token: 'test', user: { userId: 'u', name: '用户' } })
  useWorkbenchStore.setState({ activeProjectId: 'p', projectModalOpen: false, editingProject: null })
  const project = { projectId: 'p', name: '示例项目', role, permissions: role === 'owner' ? ['read', 'write', 'manage'] : ['read'] }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = new URL(String(input), 'http://localhost')
    const data = url.pathname === '/v1/user' ? { userId: 'u', name: '用户' }
      : url.pathname === '/v1/projects' ? { items: [project], total: 1 }
        : url.pathname === '/v1/projects/p' ? project : { items: [], total: 0 }
    return new Response(JSON.stringify({ code: 0, message: 'ok', data }))
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><TestThemeProvider><AppShell /></TestThemeProvider></MemoryRouter></QueryClientProvider>)
}

it.each(['项目成员', '项目设置'])('从顶部当前项目菜单打开%s并关闭', async label => {
  mount()
  const user = userEvent.setup()
  await screen.findByText('请先创建迭代，再添加需求')
  expect(screen.queryByRole('button', { name: label })).not.toBeInTheDocument()
  await user.click(screen.getByRole('combobox', { name: '当前项目' }))
  await user.click(await screen.findByRole('menuitem', { name: new RegExp(label) }))
  const dialog = await screen.findByRole('dialog')
  await waitFor(() => expect(dialog).toBeVisible())
  expect(within(dialog).getByText(new RegExp(label))).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Close' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.getByRole('link', { name: '需求' })).toHaveAttribute('aria-current', 'page')
})

it('只读成员不能打开项目设置', async () => {
  mount('viewer', '/projects?projectPanel=settings&panelProjectId=p')
  const user = userEvent.setup()
  await screen.findByText('暂无迭代，创建后即可开始管理需求与测试')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(screen.getByRole('combobox', { name: '当前项目' }))
  expect(await screen.findByRole('menuitem', { name: /项目设置/ })).toHaveAttribute('aria-disabled', 'true')
})

it('旧项目的菜单参数不会打开当前项目的设置', async () => {
  mount('owner', '/projects?projectPanel=settings&panelProjectId=other')
  await screen.findByText('暂无迭代，创建后即可开始管理需求与测试')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
