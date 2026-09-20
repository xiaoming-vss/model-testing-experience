import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  AddTestOrderCasesResult,
  CreateTestOrderPayload,
  TestOrder,
  TestOrderEntry,
  UpdateTestOrderEntryPayload,
  UpdateTestOrderPayload,
} from '../types'

export const testOrdersApi = {
  getProjectTestOrders: (projectId: string, filters: { sprintId?: string } = {}) =>
    request<ListResponse<TestOrder>>(
      `/v1/projects/${projectId}/test-orders${buildQuery({ ...filters })}`,
    ),
  createTestOrder: (sprintId: string, body: CreateTestOrderPayload) =>
    request<TestOrder>(`/v1/sprints/${sprintId}/test-orders`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getTestOrder: (orderId: string) => request<TestOrder>(`/v1/test-orders/${orderId}`),
  updateTestOrder: (orderId: string, body: UpdateTestOrderPayload) =>
    request<TestOrder>(`/v1/test-orders/${orderId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteTestOrder: (orderId: string) =>
    request<Record<string, never>>(`/v1/test-orders/${orderId}`, { method: 'DELETE' }),
  getTestOrderEntries: (orderId: string) =>
    request<ListResponse<TestOrderEntry>>(`/v1/test-orders/${orderId}/entries`),
  addTestOrderCases: (orderId: string, caseIds: string[]) =>
    request<AddTestOrderCasesResult>(`/v1/test-orders/${orderId}/cases`, {
      method: 'POST',
      body: JSON.stringify({ caseIds }),
    }),
  deleteTestOrderEntry: (orderId: string, entryId: string) =>
    request<Record<string, never>>(`/v1/test-orders/${orderId}/entries/${entryId}`, {
      method: 'DELETE',
    }),
  updateTestOrderEntry: (orderId: string, entryId: string, body: UpdateTestOrderEntryPayload) =>
    request<TestOrderEntry>(`/v1/test-orders/${orderId}/entries/${entryId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  batchMarkPassedEntries: (orderId: string, entryIds: string[]) =>
    request<{ markedCount: number; skippedCount: number }>(
      `/v1/test-orders/${orderId}/entries/batch-mark-passed`,
      { method: 'POST', body: JSON.stringify({ entryIds }) },
    ),
  assignTestOrderEntries: (orderId: string, entryIds: string[], assigneeUserId: string) =>
    request<ListResponse<TestOrderEntry>>(`/v1/test-orders/${orderId}/entries/assign`, {
      method: 'POST',
      body: JSON.stringify({ entryIds, assigneeUserId }),
    }),
}
