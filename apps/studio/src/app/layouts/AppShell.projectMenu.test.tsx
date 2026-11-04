import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { AppShell } from './AppShell'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { UNSAVED_NAVIGATION_EVENT } from '@/shared/utils/unsavedChanges'

const clients: QueryClient[] = []
afterEach(() => {
  cleanup()
  clients.splice(0).forEach(client => client.clear())
  vi.restoreAllMocks()
  useAuthStore.setState({ token: null, user: null })
  useWorkbenchStore.getState().setActiveProjectId(undefined)
})

function mount(role = 'owner', path = '/projects?board=requirements', extraProject = false) {
  useAuthStore.setState({ token: 'test', user: { userId: 'u', name: '用户' } })
  useWorkbenchStore.setState({ activeProjectId: 'p', projectModalOpen: false, editingProject: null })
  const project = { projectId: 'p', name: '示例项目', role, permissions: role === 'owner' ? ['read', 'write', 'manage'] : ['read'] }
  const projects = extraProject ? [project, { ...project, projectId: 'p2', name: '另一项目' }] : [project]
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = new URL(String(input), 'http://localhost')
    const data = url.pathname === '/v1/user' ? { userId: 'u', name: '用户' }
      : url.pathname === '/v1/projects' ? { items: projects, total: projects.length }
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

it('取消未保存确认时保持当前项目', async () => {
  mount('owner', '/projects?board=requirements', true)
  const user = userEvent.setup()
  await screen.findByText('请先创建迭代，再添加需求')
  const preventLeave = (event: Event) => event.preventDefault()
  window.addEventListener(UNSAVED_NAVIGATION_EVENT, preventLeave)
  try {
    await user.click(screen.getByRole('combobox', { name: '当前项目' }))
    await user.click(await screen.findByText('另一项目'))
    expect(useWorkbenchStore.getState().activeProjectId).toBe('p')
  } finally {
    window.removeEventListener(UNSAVED_NAVIGATION_EVENT, preventLeave)
  }
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

it('把缺少问号的 board 地址重定向到需求页', async () => {
  mount('owner', '/projects/board=requirements')
  await screen.findByText('请先创建迭代，再添加需求')
  expect(screen.getByRole('link', { name: '需求' })).toHaveAttribute('aria-current', 'page')
})

it('未知地址回到项目页', async () => {
  mount('owner', '/unknown-page')
  await screen.findByText('暂无迭代，创建后即可开始管理需求与测试')
  expect(screen.getByRole('link', { name: '迭代' })).toHaveAttribute('aria-current', 'page')
})

it('取消未保存确认时不打开项目菜单或新建项目', async () => {
  mount()
  const user = userEvent.setup()
  await screen.findByText('请先创建迭代，再添加需求')
  const preventLeave = vi.fn((event: Event) => event.preventDefault())
  window.addEventListener(UNSAVED_NAVIGATION_EVENT, preventLeave)
  try {
    await user.click(screen.getByRole('combobox', { name: '当前项目' }))
    await user.click(await screen.findByRole('menuitem', { name: /项目成员/ }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '新建项目' }))
    expect(useWorkbenchStore.getState().projectModalOpen).toBe(false)
    expect(preventLeave).toHaveBeenCalledTimes(2)
  } finally {
    window.removeEventListener(UNSAVED_NAVIGATION_EVENT, preventLeave)
  }
})
