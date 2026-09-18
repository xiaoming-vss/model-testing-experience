import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { act, cleanup, render } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { QueryProvider } from './QueryProvider'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('重复挂载不会重复注册权限监听，卸载后停止处理权限与身份变化', () => {
  let client: QueryClient | undefined
  function Probe() { client = useQueryClient(); return null }
  const previousToken = useAuthStore.getState().token
  const view = render(<StrictMode><QueryProvider><Probe /></QueryProvider></StrictMode>)
  const invalidate = vi.spyOn(client!, 'invalidateQueries')
  const clear = vi.spyOn(client!, 'clear')
  act(() => { window.dispatchEvent(new Event('project-permission-denied')) })
  expect(invalidate).toHaveBeenCalledTimes(2)
  act(() => { useAuthStore.setState({ token: 'provider-test-token' }) })
  expect(clear).toHaveBeenCalledTimes(1)
  view.unmount()
  invalidate.mockClear()
  clear.mockClear()
  act(() => {
    window.dispatchEvent(new Event('project-permission-denied'))
    useAuthStore.setState({ token: previousToken })
  })
  expect(invalidate).not.toHaveBeenCalled()
  expect(clear).not.toHaveBeenCalled()
})
