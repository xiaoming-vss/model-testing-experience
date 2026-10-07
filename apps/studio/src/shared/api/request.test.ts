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

it('renews the raw requirement ticket after expiry and keeps bearer tokens on the platform', async () => {
  const { requestBlob } = await import('./request')
  const { useAuthStore } = await import('@/features/auth/store/auth.store')
  useAuthStore.setState({ token: 'platform-token' })
  const fetcher = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(JSON.stringify({ url: 'https://s3.test/expired', filename: '需求.docx' }), { headers: { 'Content-Type': 'application/json' } }))
    .mockResolvedValueOnce(new Response('<Code>RequestExpired</Code>', { status: 403 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ url: 'https://s3.test/fresh', filename: '需求.docx' }), { headers: { 'Content-Type': 'application/json' } }))
    .mockResolvedValueOnce(new Response('file contents'))
  const result = await requestBlob('/v1/requirements/r/download', {}, true)
  expect(result.filename).toBe('需求.docx')
  expect(result.blob.size).toBe(13)
  for (const index of [0, 2]) {
    expect(new Headers(fetcher.mock.calls[index][1]?.headers).get('Authorization')).toBe('Bearer platform-token')
  }
  for (const index of [1, 3]) {
    expect(fetcher.mock.calls[index][1]).toEqual({ credentials: 'omit' })
  }
  useAuthStore.setState({ token: null })
})


it('保留服务端分页的全局统计和最新摘要，反复缓存不产生自引用', async () => {
  const metadata = { statusCounts: { running: 1, success: 20 }, latestRun: { id: 'newest', status: 'running' } }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify({ code: 0,
    data: { items: [{ id: 'older' }], total: 21, ...metadata } })))
  const client = new QueryClient()
  const response = await request<ListResponse<{ id: string }> & typeof metadata>('/v1/runs?page=2')
  client.setQueryData(['runs', 2], response)
  client.setQueryData(['runs', 2], await request('/v1/runs?page=2'))
  expect(response.total).toBe(21)
  expect(response.statusCounts).toEqual(metadata.statusCounts)
  expect(response.latestRun).toEqual(metadata.latestRun)
  expect(response.items).not.toBe(response)
})
