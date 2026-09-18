import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { SprintDetailPage } from './SprintDetailPage'

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
