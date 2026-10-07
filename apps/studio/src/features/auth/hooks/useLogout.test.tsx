import type { ReactNode } from 'react'
import { act, cleanup, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TOKEN_KEY, useAuthStore } from '../store/auth.store'
import { useLogout } from './useLogout'

vi.mock('@/shared/utils/feedback', () => ({ message: { error: vi.fn() } }))

afterEach(() => {
  cleanup()
  useAuthStore.getState().logout()
  vi.restoreAllMocks()
})

function setup() {
  useAuthStore.getState().setToken('current-token')
  useAuthStore.getState().setUser({ userId: 'u1', name: 'alice' })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(['private-data'], { secret: 'cached' })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, ...renderHook(() => useLogout(), { wrapper }) }
}

describe('服务端注销', () => {
  it('服务端撤销成功后清除 Token、用户与查询缓存', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ code: 0, message: 'ok', data: {} })),
    )
    const { result, client } = setup()
    await act(async () => { await result.current.mutateAsync() })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [path, options] = fetchMock.mock.calls[0]
    expect(path).toBe('/v1/logout')
    expect(options?.method).toBe('POST')
    expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer current-token')
    expect(useAuthStore.getState().token).toBeNull()
    expect(useAuthStore.getState().user).toBeNull()
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(client.getQueryCache().getAll()).toHaveLength(0)
  })

  it('网络失败时保留登录状态，允许用户重试', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network failed'))
    const { result, client } = setup()
    await act(async () => {
      await expect(result.current.mutateAsync()).rejects.toThrow('network failed')
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().token).toBe('current-token')
    expect(localStorage.getItem(TOKEN_KEY)).toBe('current-token')
    expect(client.getQueryData(['private-data'])).toEqual({ secret: 'cached' })
  })

  it('已过期或已撤销的 Token 也可正常退出，且不会循环调用注销接口', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ code: 401, message: 'unauthorized', data: {} }), { status: 401 }),
    )
    const { result, client } = setup()
    await act(async () => { await result.current.mutateAsync() })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().token).toBeNull()
    expect(client.getQueryCache().getAll()).toHaveLength(0)
  })
})
