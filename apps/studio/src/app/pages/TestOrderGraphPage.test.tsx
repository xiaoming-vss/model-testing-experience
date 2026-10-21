import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { api } from '@/services/api'
import { TestOrderGraphPage } from './TestOrderGraphPage'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useWorkbenchStore.setState({ activeProjectId: undefined })
})

function renderPage(role: 'owner' | 'viewer' | 'developer') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useAuthStore.setState({ token: null, user: { userId: 'user-1', name: '测试用户' } })
  // A bookmarked graph must use its order's project, regardless of the workspace selection.
  useWorkbenchStore.setState({ activeProjectId: 'other-project' })
  client.setQueryData(['projectAccess', 'other-project'], { name: '另一项目', role: 'owner', permissions: ['read', 'execute'] })
  client.setQueryData(['projectAccess', 'project-1'], { name: 'Zata-Platform', role, permissions: role === 'owner' ? ['read', 'execute'] : role === 'viewer' ? ['read'] : ['project_read', 'bug_read', 'bug_handle'] })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue({ orderId: 'order-1', name: '1.2.0-b', projectId: 'project-1', sprintId: 'sprint-1', entriesTotal: 78, entriesExecuted: 1, entriesFailed: 1 })
  vi.spyOn(api, 'getSprint').mockResolvedValue({ name: 'v1.2.0', status: 'running' })
  vi.spyOn(api, 'getTestOrderGraph').mockResolvedValue({ orderId: 'order-1', run: null })
  vi.spyOn(api, 'lookupTestOrderEntries').mockResolvedValue(Object.assign([], { items: [], total: 0 }))
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/test-orders/order-1/graph']}><Routes><Route path="/test-orders/:orderId/graph" element={<TestOrderGraphPage />} /></Routes></MemoryRouter></QueryClientProvider>)
  return client
}

it('直接打开独立图谱地址时读取测试单上下文并复用现有图谱', async () => {
  const client = renderPage('owner')
  expect(await screen.findByText('这张测试单还没有生成过图谱')).toBeVisible()
  expect(screen.getByRole('heading', { name: '用例图谱' })).toBeVisible()
  expect(await screen.findByText('v1.2.0')).toBeVisible()
  expect(screen.getByText('Zata-Platform')).toBeVisible()
  expect(screen.queryByText('另一项目')).not.toBeInTheDocument()
  expect(screen.getByText('已执行 1 / 78')).toBeVisible()
  expect(screen.getByText('未执行 77')).toBeVisible()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '生成图谱' })).toBeEnabled()
  expect(api.getTestOrderGraph).toHaveBeenCalledWith('order-1')
  client.clear()
})

it('只读成员可查看独立页面但没有派发或判定权限', async () => {
  const client = renderPage('viewer')
  expect(await screen.findByText('这张测试单还没有生成过图谱')).toBeVisible()
  expect(screen.queryByRole('button', { name: '生成图谱' })).not.toBeInTheDocument()
  client.clear()
})

it('缺少项目 read 权限时不加载图谱和执行条目', async () => {
  const client = renderPage('developer')
  expect(await screen.findByText('没有查看此测试单图谱的权限')).toBeVisible()
  expect(api.getTestOrderGraph).not.toHaveBeenCalled()
  expect(api.lookupTestOrderEntries).not.toHaveBeenCalled()
  client.clear()
})
