import { Popconfirm } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ProjectMembersModal } from './ProjectMembersModal'
import { ProjectActionButton } from './ProjectActionButton'
import { ProjectAccessScope } from './ProjectAccessScope'
import type { ProjectRole } from '../types'

const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.splice(0).forEach(c => c.clear()); vi.restoreAllMocks() })
function response(data: unknown, status = 200) { return new Response(JSON.stringify({ code: status === 200 ? 0 : status, message: status === 200 ? 'ok' : '用户名不存在', data }), { status }) }
const permissions = { owner: ['read', 'write', 'execute', 'review', 'manage'], member: ['read', 'write', 'execute', 'review'], viewer: ['read'] }
function harness(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(<QueryClientProvider client={client}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider>)
  return client
}
it.each(['owner', 'member', 'viewer'] as const)('%s 按服务器能力控制操作；其他项目的权限互不影响', async role => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => response({ projectId: String(input).endsWith('/other') ? 'other' : 'p', role, permissions: String(input).endsWith('/other') ? [] : permissions[role] }))
  harness(<><ProjectActionButton projectId="p" action="write">保存</ProjectActionButton><ProjectActionButton projectId="p" action="manage">管理绑定</ProjectActionButton><ProjectActionButton projectId="other" action="write">其他项目保存</ProjectActionButton></>)
  await waitFor(() => expect(screen.getByRole('button', { name: /^保\s*存$/ }).hasAttribute('disabled')).toBe(role === 'viewer'))
  await waitFor(() => expect(screen.getByText('管理绑定').closest('button')?.disabled).toBe(role !== 'owner'))
  expect(screen.getByText('其他项目保存').closest('button')).toBeDisabled()
})
it('所有者直接添加已注册用户，并在转移后失去管理入口', async () => {
  let role: ProjectRole = 'owner'
  const members = [{ userId: 'owner', name: '自己', role: 'owner' }, { userId: 'u2', name: '同事', role: 'member' }]
  const requests: { path: string; method?: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input)
    requests.push({ path, method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : null })
    if (path.endsWith('/transfer-ownership')) { role = 'member'; return response({}) }
    if (path.endsWith('/members')) {
      if (init?.method === 'POST') return response({})
      return response({ items: members, total: members.length })
    }
    return response({ projectId: 'p', name: '协作项目', role, permissions: permissions[role] })
  })
  harness(<ProjectMembersModal projectId="p" onClose={() => {}} />)
  await screen.findByText('同事')
  fireEvent.change(screen.getByRole('textbox', { name: '成员用户名' }), { target: { value: '新同事' } })
  await userEvent.click(screen.getByRole('button', { name: '添加成员' }))
  await waitFor(() => expect(requests).toContainEqual({ path: '/v1/projects/p/members', method: 'POST', body: { name: '新同事', role: 'member' } }))
  await userEvent.click(screen.getByRole('button', { name: '转移所有权' }))
  await userEvent.click(await screen.findByRole('button', { name: /OK|确\s*定/ }))
  await waitFor(() => expect(screen.getByRole('button', { name: '添加成员' })).toBeDisabled())
  expect(await screen.findByRole('button', { name: '退出项目' })).toBeInTheDocument()
})
it('权限撤销后隐藏已缓存的项目内容', async () => {
  let denied = false
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => denied ? response({}, 403) : response({ name: '项目', role: 'viewer', permissions: ['read'] }))
  const client = harness(<ProjectAccessScope projectId="p"><div>已保存报告</div></ProjectAccessScope>)
  await screen.findByText('已保存报告')
  denied = true
  await client.invalidateQueries({ queryKey: ['projectAccess', 'p'] })
  await screen.findByText('无法访问此项目')
  expect(screen.queryByText('已保存报告')).toBeNull()
})

it('无权限按钮置灰，点击不打开确认框，只在悬停时说明原因', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => response({ projectId: 'p', role: 'member', permissions: permissions.member }))
  const click = vi.fn()
  const parentClick = vi.fn()
  harness(<div onClick={parentClick}><Popconfirm title="不能打开的确认框"><ProjectActionButton projectId="p" action="manage" onClick={click}>禅道绑定</ProjectActionButton></Popconfirm></div>)
  const button = screen.getByRole('button', { name: '禅道绑定' })
  await waitFor(() => expect(button).toBeDisabled())
  fireEvent.click(button)
  fireEvent.click(button.parentElement!)
  expect(click).not.toHaveBeenCalled()
  expect(parentClick).not.toHaveBeenCalled()
  expect(screen.queryByText('不能打开的确认框')).not.toBeInTheDocument()
  await userEvent.hover(button.parentElement!)
  expect(await screen.findByRole('tooltip')).toHaveTextContent('仅项目所有者可以操作')
})
