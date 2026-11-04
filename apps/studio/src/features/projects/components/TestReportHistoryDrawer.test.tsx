import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { projectsApi } from '../api/projects.api'
import { TestReportHistoryDrawer } from './TestReportHistoryDrawer'

vi.mock('../hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))
vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('显示每次历史、失败原因，并确认后删除已完成记录', async () => {
  const runs = [
    { runId: 'done', status: 'success', createdAt: '2026-01-01T00:00:00Z' },
    { runId: 'failed', status: 'failed', errorMessage: '连接失败', createdAt: '2026-01-02T00:00:00Z' },
    { runId: 'busy', status: 'running', createdAt: '2026-01-03T00:00:00Z' },
  ]
  vi.spyOn(projectsApi, 'getTestReportGenerateRuns').mockResolvedValue(Object.assign(runs, { items: runs, total: runs.length }))
  const remove = vi.spyOn(projectsApi, 'deleteTestReportGenerateRun').mockResolvedValue({})
  const onView = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><TestReportHistoryDrawer open projectId="project" sprintId="sprint" onClose={vi.fn()} onView={onView} /></QueryClientProvider>)
  expect(await screen.findByText('连接失败')).toBeInTheDocument()
  const rows = screen.getAllByRole('row')
  const done = rows.find(row => within(row).queryByText('成功'))!
  const busy = rows.find(row => within(row).queryByText('生成中'))!
  await userEvent.setup().click(within(done).getByRole('button', { name: '查看' }))
  expect(onView).toHaveBeenCalledWith(expect.objectContaining({ runId: 'done' }))
  expect(within(busy).getByRole('button', { name: '删除' })).toBeDisabled()
  await userEvent.setup().click(within(done).getByRole('button', { name: '删除' }))
  const confirmation = (await screen.findByText('删除这条报告记录？')).closest('.ant-popover')!
  await userEvent.setup().click(within(confirmation as HTMLElement).getByRole('button', { name: /删\s*除/ }))
  expect(remove.mock.calls[0][0]).toBe('done')
  client.clear()
})
