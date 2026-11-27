import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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


it('缺陷未采集时仍可更新本地统计', async () => {
  const local = { total: 2, executed: 1, pending: 1, success: 1, failed: 0 }
  const snapshot = { snapshotDate: '2026-09-24', function: local, bug: null, bugs: [] }
  const updatedSnapshot = { ...snapshot, bug: { total: 4, resolved: 1, closed: 1, unresolved: 2, fatal: 1, serious: 1, normal: 1, suggestion: 1 } }
  let refreshed = false
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (init?.method === 'PUT') refreshed = true
    const path = String(input)
    const data = path.endsWith('/sprints/s1')
      ? { sprintId: 's1', projectId: 'p1', name: '当前迭代', status: 'completed' }
      : path.endsWith('/projects/p1')
        ? { projectId: 'p1', name: '项目', permissions: ['read', 'manage', 'execute', 'write'] }
        : path.endsWith('/sprints/s1/bindings') ? { items: [{ provider: 'zentao', status: 'active', instanceUrl: 'http://zentao.local' }] }
          : path.includes('/daily-metrics/') ? (refreshed ? updatedSnapshot : snapshot)
          : path.includes('/daily-metrics?') ? { items: [refreshed ? updatedSnapshot : snapshot], total: 1 }
            : { items: [], total: 0 }
    return new Response(JSON.stringify({ code: 0, message: 'ok', data }))
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/projects/p1/sprints/s1']}>
    <Routes><Route path="/projects/:projectId/sprints/:sprintId" element={<SprintDetailPage />} /></Routes>
  </MemoryRouter></QueryClientProvider>)
  expect(await screen.findByText('2 个用例，缺陷未采集')).toBeInTheDocument()
  expect(screen.getByText('已完成')).toBeInTheDocument()
  expect(screen.queryByText('进行中')).not.toBeInTheDocument()
  expect(screen.getByText('缺陷数据未采集，暂不统计')).toBeInTheDocument()
  expect(screen.queryByText(/0 个缺陷/)).not.toBeInTheDocument()
  expect(screen.getByText('解决率').querySelector('strong')).toHaveTextContent('—')
  fireEvent.click(screen.getByRole('button', { name: /更新数据/ }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) =>
    String(input).includes('/daily-metrics/') && init?.method === 'PUT')).toBe(true))
  await waitFor(() => expect(message.success).toHaveBeenCalled())
  expect(await screen.findByText('2 个用例，4 个缺陷')).toBeInTheDocument()
  expect(screen.queryByText('缺陷数据未采集，暂不统计')).not.toBeInTheDocument()
  expect(screen.getByText('解决率').querySelector('strong')).toHaveTextContent('25%')
  expect(message.error).not.toHaveBeenCalled()
  expect(screen.queryByText(/选择本人禅道授权/)).not.toBeInTheDocument()
  client.clear()
})

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/projects/p1/sprints/s1']}>
    <Routes><Route path="/projects/:projectId/sprints/:sprintId" element={<SprintDetailPage />} /></Routes>
  </MemoryRouter></QueryClientProvider>)
  return client
}

function mockSprintFetch(reportRuns: unknown[], runDetail?: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input)
    const data = path.endsWith('/sprints/s1')
      ? { sprintId: 's1', projectId: 'p1', name: '当前迭代', status: 'running' }
      : path.endsWith('/projects/p1')
        ? { projectId: 'p1', name: '项目', permissions: ['read', 'manage', 'execute', 'write'] }
        : path.includes('/daily-metrics/') ? { snapshotDate: '2026-11-20', function: { total: 2, executed: 2, pending: 0, success: 2, failed: 0 }, bug: null }
          : path.includes('/daily-metrics?') ? { items: [{ snapshotDate: '2026-11-20', function: { total: 2, executed: 2, pending: 0, success: 2, failed: 0 }, bug: null }], total: 1 }
            : path.includes('/test-report-generate-runs') && !path.includes('/v1/test-report-generate-runs/')
              ? { items: reportRuns, total: reportRuns.length }
              : path.includes('/v1/test-report-generate-runs/') && runDetail
                ? runDetail
                : { items: [], total: 0 }
    return new Response(JSON.stringify({ code: 0, message: 'ok', data }))
  })
}

it('报告历史打开后展示当前迭代的运行记录', async () => {
  mockSprintFetch([{ runId: 'run-1', status: 'success', createdAt: '2026-11-20T10:00:00Z' }])
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '报告历史' }))
  const drawer = await screen.findByRole('dialog')
  expect(within(drawer).getByText('测试报告历史')).toBeInTheDocument()
  expect(await within(drawer).findByText('成功')).toBeInTheDocument()
})

it('查看最近一次成功报告并导出 PDF', async () => {
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const fetchMock = mockSprintFetch(
    [{ runId: 'run-1', status: 'success', createdAt: '2026-11-20T10:00:00Z' }],
    { runId: 'run-1', status: 'success', resultYaml: '# 迭代报告\n\n正文内容' },
  )
  renderPage()
  const viewButton = await screen.findByRole('button', { name: /查看报告/ })
  await waitFor(() => expect(viewButton).toBeEnabled())
  fireEvent.click(viewButton)
  expect(await screen.findByText('迭代报告')).toBeInTheDocument()
  expect(screen.getByText('正文内容')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /导出 PDF/ }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/run-1/pdf'))).toBe(true))
})

