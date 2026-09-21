import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { Form } from 'antd'
import { useRef, useState, type ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type ApiCase } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import type { ApiCaseFormValues } from '../utils/apiCaseEditor'
import { useApiCaseEditing } from './useApiCaseEditing'
import { useApiExecution } from './useApiExecution'

vi.mock('@/shared/utils/feedback', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

const clients: QueryClient[] = []

afterEach(() => {
  cleanup()
  clients.forEach(client => client.clear())
  clients.length = 0
  vi.restoreAllMocks()
})

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  return {
    client,
    wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  }
}

it('API 执行从运行中收敛为成功，并刷新本次环境变量', async () => {
  const { client, wrapper } = setup()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  vi.spyOn(api, 'runApiCase').mockResolvedValue({ runId: 'run-1', status: 'running' })
  const fetchRun = vi.spyOn(api, 'getApiCaseRun').mockResolvedValue({ runId: 'run-1', status: 'success', environmentId: 'env-1' })
  const { result } = renderHook(() => useApiExecution({ collectionId: '' }), { wrapper })

  await act(async () => {
    await result.current.runApiCaseMutation.mutateAsync({ caseId: 'case-1', environmentId: 'env-1' })
  })

  await waitFor(() => expect(result.current.runResult?.status).toBe('success'))
  expect(fetchRun).toHaveBeenCalledWith('run-1')
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['apiEnvironmentVars', 'env-1'] })
  await waitFor(() => expect(client.getQueryCache().find({ queryKey: ['apiCaseRun', 'run-1'] })?.isActive()).toBe(false))
})

it('运行详情请求失败时保留运行身份并停止轮询', async () => {
  const { client, wrapper } = setup()
  vi.spyOn(api, 'runApiCase').mockResolvedValue({ runId: 'run-failed', status: 'running' })
  vi.spyOn(api, 'getApiCaseRun').mockRejectedValue(new Error('运行详情暂不可用'))
  const { result } = renderHook(() => useApiExecution({ collectionId: '' }), { wrapper })

  await act(async () => {
    await result.current.runApiCaseMutation.mutateAsync({ caseId: 'case-1', environmentId: 'env-1' })
  })

  await waitFor(() => expect(result.current.runResult?.status).toBe('error'))
  expect(result.current.runResult?.runId).toBe('run-failed')
  expect(message.error).toHaveBeenCalledWith('运行详情暂不可用')
  expect(client.getQueryCache().find({ queryKey: ['apiCaseRun', 'run-failed'] })?.isActive()).toBe(false)
})

it('用例排序保存失败时恢复拖拽前的顺序并清除拖拽状态', async () => {
  const { wrapper } = setup()
  vi.spyOn(api, 'updateApiCase').mockRejectedValue(new Error('保存失败'))
  const cases: ApiCase[] = [
    { caseId: 'a', name: 'A', method: 'GET', urlTemplate: '/ping', orderNo: 1 },
    { caseId: 'b', name: 'B', method: 'GET', urlTemplate: '/ping', orderNo: 2 },
  ]
  const { result } = renderHook(() => {
    const [caseForm] = Form.useForm<ApiCaseFormValues>()
    const [order, setOrder] = useState(['b', 'a'])
    const [dragging, setDragging] = useState<string | null>('b')
    const [, setEditingCase] = useState<ApiCase | null>(null)
    const [, setSelectedCaseId] = useState('')
    const [, setDraftCaseValues] = useState<ApiCaseFormValues | null>(null)
    const rollback = useRef(['a', 'b'])
    const editing = useApiCaseEditing({
      caseForm, collectionId: 'collection-1', cases, caseOrderIds: order,
      caseOrderRollbackRef: rollback, setCaseOrderIds: setOrder, setDraggingCaseId: setDragging,
      editingCase: null, setEditingCase, setSelectedCaseId, setDraftCaseValues,
    })
    return { ...editing, order, dragging, rollback }
  }, { wrapper })

  await act(async () => {
    await expect(result.current.reorderCasesMutation.mutateAsync(['b', 'a'])).rejects.toThrow('保存失败')
  })

  expect(result.current.order).toEqual(['a', 'b'])
  expect(result.current.dragging).toBeNull()
  expect(result.current.rollback.current).toEqual([])
})
