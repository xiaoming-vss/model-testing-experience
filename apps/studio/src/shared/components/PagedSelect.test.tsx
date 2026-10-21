import { ConfigProvider } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { PagedSelect } from './PagedSelect'

afterEach(cleanup)

it('loads options only on open and can search and select beyond the first page', async () => {
  const items = Array.from({ length: 25 }, (_, index) => ({ label: `option ${index + 1}`, value: `${index + 1}` }))
  const load = vi.fn(async (page: number, keyword: string) => {
    const matching = items.filter((item) => item.label.includes(keyword))
    return { items: matching.slice((page - 1) * 20, page * 20), total: matching.length, page }
  })
  const change = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><ConfigProvider theme={{ token: { motion: false } }}><PagedSelect scopeKey="one" queryKey={['options']} loadPage={load} onChange={change} /></ConfigProvider></QueryClientProvider>)
  expect(load).not.toHaveBeenCalled()
  const user = userEvent.setup()
  await user.click(screen.getByRole('combobox'))
  await screen.findByText('option 1')
  expect(screen.queryByText('option 21')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '下一页' }))
  await user.click(await screen.findByText('option 21'))
  expect(change).toHaveBeenCalledWith('21')
  await user.click(screen.getByRole('combobox'))
  await user.type(screen.getByRole('combobox'), 'option 25')
  await waitFor(() => expect(load).toHaveBeenLastCalledWith(1, 'option 25'))
  await waitFor(() => expect(screen.getByText('option 25')).toBeVisible())
  client.clear()
})

it('reports and retries a failed option page', async () => {
  const load = vi.fn().mockRejectedValueOnce(new Error('读取失败')).mockResolvedValue({ items: [{ label: 'recovered', value: 'r' }], total: 1, page: 1 })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><ConfigProvider theme={{ token: { motion: false } }}><PagedSelect scopeKey="one" queryKey={['options']} loadPage={load} /></ConfigProvider></QueryClientProvider>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('combobox'))
  await user.click(await screen.findByRole('button', { name: /重\s*试/ }))
  await waitFor(() => expect(screen.getByText('recovered')).toBeVisible())
  client.clear()
})
