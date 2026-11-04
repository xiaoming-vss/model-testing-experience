import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { testOrdersApi } from '../api/testOrders.api'
import { TestOrderGraphHistoryDrawer } from './TestOrderGraphHistoryDrawer'

vi.mock('@/features/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))
vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('可查看历史并删除已结束图谱，运行中不可删除', async () => {
  const rows = [{ runId: 'old', status: 'success', createdAt: '2026-01-01T00:00:00Z' }, { runId: 'busy', status: 'running' }]
  vi.spyOn(testOrdersApi, 'getTestOrderGraphRuns').mockResolvedValue(Object.assign(rows, { items: rows, total: rows.length }))
  const remove = vi.spyOn(testOrdersApi, 'deleteTestOrderGraphRun').mockResolvedValue({})
  const select = vi.fn()
  const deleted = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><TestOrderGraphHistoryDrawer open orderId="order" projectId="project" onClose={vi.fn()} onSelect={select} onDeleted={deleted} /></QueryClientProvider>)
  expect(await screen.findByText('成功')).toBeInTheDocument()
  const tableRows = screen.getAllByRole('row')
  const done = tableRows.find(row => within(row).queryByText('成功'))!
  const busy = tableRows.find(row => within(row).queryByText('生成中'))!
  const user = userEvent.setup()
  await user.click(within(done).getByRole('button', { name: '查看' }))
  expect(select).toHaveBeenCalledWith('old')
  expect(within(busy).getByRole('button', { name: '删除' })).toBeDisabled()
  await user.click(within(done).getByRole('button', { name: '删除' }))
  const confirmation = (await screen.findByText('删除这条图谱记录？')).closest('.ant-popover')!
  await user.click(within(confirmation as HTMLElement).getByRole('button', { name: /删\s*除/ }))
  expect(remove.mock.calls[0][0]).toBe('old')
  client.clear()
})
