import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { useBugDetail } from './useBugDetail'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

function Permissions() {
  const { canRead, canWrite, canHandle } = useBugDetail()
  return <div>
    <button disabled={!canRead}>读取</button>
    <button disabled={!canWrite}>编辑</button>
    <button disabled={!canHandle}>处理</button>
  </div>
}

it('权限重新加载失败时关闭 Bug 操作，即使查询仍保留旧能力', async () => {
  let denied = false
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const path = String(input)
    const projectRequest = path.endsWith('/projects/p')
    const status = projectRequest && denied ? 403 : 200
    const data = projectRequest
      ? { projectId: 'p', name: '项目', role: 'member', permissions: ['read', 'write', 'bug_handle'] }
      : path.endsWith('/bugs/b')
        ? { bugId: 'b', projectId: 'p' }
        : { items: [], total: 0 }
    return new Response(JSON.stringify({ code: status === 200 ? 0 : 403, message: 'forbidden', data }), { status })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  try {
    render(<QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/bugs/b']}>
        <Routes><Route path="/bugs/:bugId" element={<Permissions />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>)
    await waitFor(() => expect(screen.getByRole('button', { name: '编辑' })).toBeEnabled())
    denied = true
    await act(async () => { await client.invalidateQueries({ queryKey: ['projectAccess', 'p'] }) })
    await waitFor(() => expect(screen.getByRole('button', { name: '编辑' })).toBeDisabled())
    expect(screen.getByRole('button', { name: '处理' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '读取' })).toBeDisabled()
    expect(client.getQueryData(['projectAccess', 'p'])).toBeDefined()
  } finally {
    cleanup()
    client.clear()
  }
})
