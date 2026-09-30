import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { SprintDetailPage } from './SprintDetailPage'
import { message } from '@/shared/utils/feedback'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('拒绝使用路径中其他项目的权限展示迭代', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input)
    const data = path.endsWith('/sprints/sprint-b')
      ? { sprintId: 'sprint-b', projectId: 'project-b', name: '另一个项目的迭代', status: 'running' }
      : path.endsWith('/projects/project-a')
        ? { projectId: 'project-a', name: '项目A', permissions: ['read', 'manage', 'execute'] }
        : { items: [], total: 0 }
    return new Response(JSON.stringify({ code: 0, message: 'ok', data }))
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/projects/project-a/sprints/sprint-b']}>
    <Routes><Route path="/projects/:projectId/sprints/:sprintId" element={<SprintDetailPage />} /></Routes>
  </MemoryRouter></QueryClientProvider>)
  expect(await screen.findByText('迭代所属项目与访问路径不一致')).toBeInTheDocument()
  expect(screen.queryByText('另一个项目的迭代')).not.toBeInTheDocument()
})


it.each([false, true])('缺陷未采集时仍可更新本地统计（授权接口失败：%s）', async (connectionFailure) => {
  const local = { total: 2, executed: 1, pending: 1, success: 1, failed: 0 }
  const snapshot = { snapshotDate: '2026-09-24', function: local, bug: null, bugs: [] }
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input)
    if (connectionFailure && path.includes('/zentao/connections')) throw new TypeError('Failed to fetch')
    const data = path.endsWith('/sprints/s1')
      ? { sprintId: 's1', projectId: 'p1', name: '当前迭代', status: 'running' }
      : path.endsWith('/projects/p1')
        ? { projectId: 'p1', name: '项目', permissions: ['read', 'manage', 'execute', 'write'] }
        : path.endsWith('/sprints/s1/bindings') ? { items: [{ provider: 'zentao', status: 'active', instanceUrl: 'http://zentao.local' }] }
          : path.includes('/daily-metrics/') ? snapshot
          : path.includes('/daily-metrics?') ? { items: [snapshot], total: 1 }
            : path.includes('/code-overview') ? { repositories: [] }
              : { items: [], total: 0 }
    return new Response(JSON.stringify({ code: 0, message: 'ok', data }))
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/projects/p1/sprints/s1']}>
    <Routes><Route path="/projects/:projectId/sprints/:sprintId" element={<SprintDetailPage />} /></Routes>
  </MemoryRouter></QueryClientProvider>)
  expect(await screen.findByText('2 个用例，缺陷未采集')).toBeInTheDocument()
  expect(screen.getByText('缺陷数据未采集，暂不统计')).toBeInTheDocument()
  expect(screen.queryByText(/0 个缺陷/)).not.toBeInTheDocument()
  expect(screen.getByText('解决率').querySelector('strong')).toHaveTextContent('—')
  fireEvent.click(screen.getByRole('button', { name: /更新数据/ }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) =>
    String(input).includes('/daily-metrics/') && init?.method === 'PUT')).toBe(true))
  await waitFor(() => expect(message.success).toHaveBeenCalled())
  expect(message.error).not.toHaveBeenCalled()
  expect(screen.queryByText(/选择本人禅道授权/)).not.toBeInTheDocument()
  client.clear()
})
