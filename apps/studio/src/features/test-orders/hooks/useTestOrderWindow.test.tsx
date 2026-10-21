import type { PropsWithChildren } from 'react'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { useTestOrderWindow } from './useTestOrderWindow'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('删除末页唯一条目后回到有效页，后续新增不会跳回旧页', async () => {
  let count = 21
  const list = vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async (_, filters = {}) => {
    const page = Math.min(filters.page ?? 1, Math.ceil(count / 20))
    const items = Array.from({ length: Math.min(20, count - (page - 1) * 20) }, (_, i) => ({ entryId: `e${(page - 1) * 20 + i + 1}` }))
    return { items, page, pageSize: 20, total: count, matchedTotal: count, orderTotal: count, mineCount: 0, statusCounts: {}, preferredEntryId: items[0]?.entryId ?? '' }
  })
  vi.spyOn(api, 'getTestOrderEntry').mockImplementation(async (_, id) => ({ entryId: id }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(() => useTestOrderWindow('order', null, { keyword: '', status: '', onlyMine: false }), { wrapper })
  await waitFor(() => expect(result.current.selectedEntryId).toBe('e1'))
  act(() => result.current.changePage(2))
  await waitFor(() => expect(result.current.selectedEntryId).toBe('e21'))
  count = 20
  await act(async () => { await client.invalidateQueries({ queryKey: ['testOrderEntries', 'order'] }) })
  act(() => result.current.clearDeletedSelection('e21'))
  await waitFor(() => expect(result.current.selectedEntryId).toBe('e1'))
  await waitFor(() => expect(list.mock.lastCall?.[1]?.page).toBe(1))
  count = 21
  await act(async () => { await client.invalidateQueries({ queryKey: ['testOrderEntries', 'order'] }) })
  expect(result.current.currentPage).toBe(1)
  expect(result.current.selectedEntryId).toBe('e1')
  act(() => result.current.selectEntry('e2'))
  act(() => result.current.clearDeletedSelection('e1'))
  expect(result.current.selectedEntryId).toBe('e2')
  client.clear()
})
