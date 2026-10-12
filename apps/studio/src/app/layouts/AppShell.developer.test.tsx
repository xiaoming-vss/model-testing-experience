import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { AppShell } from './AppShell'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))

const permissions = ['project_read', 'bug_read', 'bug_handle']
const bug = {
  id: 1, bugId: 'b', bugNo: 1, projectId: 'p', title: '开发需要修复的问题', status: 'active', confirmed: false, resolution: '',
  descriptionHtml: '<p>问题描述</p>', severity: 'normal', priority: 'medium',
  reporterUserId: 'owner', assigneeUserId: 'dev', foundSprintId: 's', plannedFixSprintId: '',
  requirementId: 'r', requirementName: '关联需求名称', sourceOrderId: 'order',
  sourceOrderName: '关联测试单名称', sourceEntryId: 'entry', sourceCaseId: 'case',
  sourceCaseTitle: '关联用例名称', attachments: [],
}
const clients: QueryClient[] = []
let requests: Array<{ path: string; method?: string; body?: string }> = []

beforeEach(() => {
  useAuthStore.setState({ token: 'test-token', user: { userId: 'dev', name: '开发人员' } })
  useWorkbenchStore.getState().setActiveProjectId('p')
  requests = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input)
    requests.push({ path, method: init?.method, body: init?.body as string | undefined })
    let data: unknown
    if (path === '/v1/user') data = { userId: 'dev', name: '开发人员' }
    else if (path === '/v1/projects') data = { items: [{ projectId: 'p', name: '项目', role: 'developer', permissions }], total: 1 }
    else if (path === '/v1/projects/p') data = { projectId: 'p', name: '项目', role: 'developer', permissions }
    else if (path === '/v1/projects/p/bugs/options') data = {
      members: [{ userId: 'owner', name: '项目所有者' }, { userId: 'dev', name: '开发人员' }],
      sprints: [{ sprintId: 's', name: 'Bug 发现迭代' }],
    }
    else if (path.startsWith('/v1/projects/p/bugs?')) data = { items: [bug], total: 1 }
    else if (path === '/v1/bugs/b') data = bug
    else if (path === '/v1/bugs/b/activities') data = { items: [], total: 0 }
    else if (path === '/v1/bugs/b/comments') data = {}
    else if (path === '/v1/bugs/b/transfer') data = { ...bug, assigneeUserId: 'owner' }
    else if (path === '/v1/bugs/b/transition') data = { ...bug, status: 'active', confirmed: true, resolution: '' }
    else throw new Error(`开发页面不应读取 ${path}`)
    return new Response(JSON.stringify({ code: 0, message: 'ok', data }), { status: 200 })
  })
})

afterEach(() => {
  cleanup()
  clients.splice(0).forEach((client) => client.clear())
  vi.restoreAllMocks()
  useAuthStore.setState({ token: null, user: null })
  useWorkbenchStore.getState().setActiveProjectId(undefined)
})

function renderShell(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><AppShell /></MemoryRouter></QueryClientProvider>)
}

it.each(['/projects', '/testing?tab=api', '/ai-testing', '/base-services', '/requirements/r', '/bugs/new'])(
  '开发直接访问 %s 时进入 Bug 列表，且不请求其他业务资源', async (path) => {
    renderShell(path)
    await screen.findByText('开发需要修复的问题')
    expect(screen.getByRole('link', { name: 'Bug列表' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('button', { name: '项目总览' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '测试设计' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '基础服务' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建项目' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '新建 Bug' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '确认' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '解决' })).toBeEnabled()
    expect(requests.every(({ path: requested }) => requested === '/v1/user'
      || requested === '/v1/projects' || requested === '/v1/projects/p'
      || requested.startsWith('/v1/projects/p/bugs'))).toBe(true)
  },
)

it('开发可评论、转派和更新状态，详情不提供其他业务模块跳转', async () => {
  renderShell('/bugs/b')
  await screen.findByRole('heading', { name: '开发需要修复的问题' })
  const input = screen.getByRole('textbox', { name: '评论输入框' })
  await waitFor(() => expect(input).toBeEnabled())
  expect(screen.getByRole('button', { name: '编辑 Bug' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '转派 Bug' })).toBeEnabled()
  expect(screen.getByText('关联需求名称')).not.toHaveAttribute('href')
  expect(screen.getByText('关联测试单名称')).not.toHaveAttribute('href')
  expect(screen.getByText('关联用例名称')).not.toHaveAttribute('href')
  await userEvent.type(input, '已定位问题')
  await userEvent.click(screen.getByRole('button', { name: '发送评论' }))
  await waitFor(() => expect(requests).toContainEqual({ path: '/v1/bugs/b/comments', method: 'POST', body: JSON.stringify({ content: '已定位问题' }) }))
  await userEvent.click(screen.getByRole('button', { name: '转派 Bug' }))
  const select = await screen.findByRole('combobox', { name: '新责任人' })
  await userEvent.click(select)
  await userEvent.click(await screen.findByText('项目所有者', { selector: '.ant-select-item-option-content' }))
  await userEvent.click(screen.getByRole('button', { name: '确认转派' }))
  await waitFor(() => expect(requests.some(({ path }) => path === '/v1/bugs/b/transfer')).toBe(true))
  await userEvent.click(screen.getByRole('button', { name: /^确\s*认$/ }))
  // 转派弹窗离场动画期间仍在 DOM，取包含“确认”提交按钮的那个弹窗。
  const dialogs = await screen.findAllByRole('dialog')
  const transitionDialog = dialogs.find(item => within(item).queryByRole('button', { name: '确认' }))
  await userEvent.click(within(transitionDialog!).getByRole('button', { name: '确认' }))
  await waitFor(() => expect(requests.some(({ path }) => path === '/v1/bugs/b/transition')).toBe(true))
  expect(requests.some(({ path }) => path.endsWith('/members') || path.endsWith('/sprints'))).toBe(false)
})
