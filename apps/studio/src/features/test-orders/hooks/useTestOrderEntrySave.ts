import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, listItems } from '@/services/api'
import type { ListResponse } from '@/shared/api/request'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import type { TestOrderEntry, UpdateTestOrderEntryPayload } from '../types'

/** Both execution surfaces save by explicit entry identity and share query state. */
export function useTestOrderEntrySave(orderId: string) {
  const client = useQueryClient()
  return useMutation({
    scope: { id: `test-order-execution:${orderId}` },
    mutationFn: ({ entryId, payload }: { entryId: string; payload: UpdateTestOrderEntryPayload }) =>
      api.updateTestOrderEntry(orderId, entryId, payload),
    onSuccess: async (updated, { entryId }) => {
      const queryKey = ['testOrderEntries', orderId]
      await client.cancelQueries({ queryKey })
      client.setQueryData<ListResponse<TestOrderEntry>>(queryKey, (previous) => {
        if (!previous) return previous
        const items = listItems(previous).map((entry) => entry.entryId === entryId ? { ...entry, ...updated } : entry)
        return Object.assign([...items], { items, total: previous.total ?? items.length })
      })
      await Promise.all([
        client.invalidateQueries({ queryKey }),
        client.invalidateQueries({ queryKey: ['testOrder', orderId] }),
        client.invalidateQueries({ queryKey: ['testOrders'] }),
      ])
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })
}
