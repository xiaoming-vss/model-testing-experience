import { QueryClient } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { request, type ListResponse } from './request'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('列表响应规范化', () => {
  it('兼容 items 访问时不会创建自引用列表', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () => new Response(
        JSON.stringify({
          code: 0,
          message: 'ok',
          data: { items: [{ id: 'case-1' }], total: 1 },
        }),
      ),
    )

    const response = await request<ListResponse<{ id: string }>>('/v1/test-cases')
    const refetchedResponse = await request<ListResponse<{ id: string }>>('/v1/test-cases')
    const queryClient = new QueryClient()

    queryClient.setQueryData(['testCases'], response)
    queryClient.setQueryData(['testCases'], refetchedResponse)

    expect(Array.from(response)).toEqual([{ id: 'case-1' }])
    expect(response.items).toEqual([{ id: 'case-1' }])
    expect(response.items).not.toBe(response)
    expect(response.total).toBe(1)
  })
})
