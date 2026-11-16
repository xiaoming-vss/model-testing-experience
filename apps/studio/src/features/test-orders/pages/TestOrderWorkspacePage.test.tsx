import type { TestOrderEntry } from '../types'
import type { ReactNode } from 'react'
import { ConfigProvider } from 'antd'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type User } from '@/services/api'
import { TestOrderWorkspacePage } from './TestOrderWorkspacePage'

vi.mock('../components/TestOrderGraphViewer', () => ({
  TestOrderGraphViewer: ({ orderId, toolbar }: { orderId: string; toolbar?: ReactNode }) =>
    <div data-testid="inline-graph">{toolbar}内嵌用例图谱 {orderId}</div>,
}))

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useParams: () => ({ orderId: 'order-1' }) }
})

const order = {
  orderId: 'order-1',
  projectId: 'project-1',
  sprintId: 'sprint-1',
  name: 'V2.3 回归测试单',
  testedVersion: 'V2.3.1-rc2',
  entriesTotal: 2,
  entriesExecuted: 0,
  status: 'pending',
}

const entry = {
  entryId: 'entry-1',
  orderId: 'order-1',
  caseType: 'function',
  caseId: 'case-1',
  caseTitle: '验证码错误 5 次锁定账号',
  caseModule: '登录',
  casePriority: 'P1',
  orderNo: 1,
  status: 'pending',
  assigneeUserId: '',
  snapshot: {
    preconditions: ['已注册手机号'],
    steps: [
      { action: '输入错误验证码', expected: '提示可重试' },
      { action: '连续第 5 次', expected: '账号锁定' },
    ],
  },
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length, page: 1, pageSize: 20,
    matchedTotal: items.length, orderTotal: items.length, mineCount: 0,
    preferredEntryId: (items.find((item) => (item as typeof entry).status === 'pending') as typeof entry)?.entryId ?? (items[0] as typeof entry)?.entryId ?? '',
    statusCounts: Object.fromEntries(['pending', 'passed', 'failed', 'blocked', 'skipped'].map((status) => [status, items.filter((item) => (item as typeof entry).status === status).length])),
  })
}

function renderWorkspace(client: QueryClient, initialEntry = '/') {
  return render(
    <QueryClientProvider client={client}>
      <ConfigProvider theme={{ token: { motion: false } }}><MemoryRouter initialEntries={[initialEntry]}>
        <TestOrderWorkspacePage />
      </MemoryRouter></ConfigProvider>
    </QueryClientProvider>,
  )
}

function seedAccess(client: QueryClient, role: 'owner' | 'member') {
  client.setQueryData(['projectAccess', 'project-1'], {
    projectId: 'project-1',
    role,
    permissions:
      role === 'owner'
        ? ['read', 'write', 'execute', 'review', 'manage']
        : ['read', 'write', 'execute', 'review'],
  })
}

function entryList() {
  return document.querySelector('.test-order-entry-list-panel') as HTMLElement
}

function detailPanel() {
  return document.querySelector('.test-order-detail-panel') as HTMLElement
}

async function openEntry(user: ReturnType<typeof userEvent.setup>, title: string) {
  const titleNode = within(entryList()).getByText(title, { exact: true })
  await user.click(titleNode)
  await waitFor(() => expect(detailPanel()).not.toBeNull())
}

async function openEntryFilters(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /筛选执行用例/ }))
  return screen.getByPlaceholderText('搜索用例 ID 或关键字')
}

beforeEach(() => {
  vi.spyOn(api, 'getTestOrderEntry').mockImplementation(async (_, id) => {
    const response = await vi.mocked(api.getTestOrderEntries).mock.results.at(-1)?.value
    return response?.items.find((item: typeof entry) => item.entryId === id) ?? entry
  })
  vi.spyOn(api, 'lookupTestOrderEntries').mockResolvedValue(listResponse([]))
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
  Reflect.deleteProperty(navigator, 'clipboard')
})

it('进入测试单先展示执行条目列表，点击条目才进入详情', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([entry]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  expect(await within(entryList()).findByText('验证码错误 5 次锁定账号')).toBeInTheDocument()
  expect(screen.queryByText('阅读方式')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /返回用例列表/ })).not.toBeInTheDocument()

  const user = userEvent.setup()
  await openEntry(user, '验证码错误 5 次锁定账号')

  expect(await screen.findByText('阅读方式')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /返回用例列表/ })).toBeInTheDocument()
  const breadcrumb = screen.getByRole('navigation', { name: '面包屑' })
  expect(within(breadcrumb).getByText('验证码错误 5 次锁定账号')).toBeInTheDocument()
  expect(screen.queryByText('用例详情')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /筛选执行用例/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '用例图谱' })).not.toBeInTheDocument()
  client.clear()
})

it('列表以单行展示用例 ID 和标题，点击 ID 复制且不进入详情', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([entry]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  const idButton = await screen.findByRole('button', { name: `复制用例 ID ${entry.caseId}` })
  const headers = screen.getAllByRole('columnheader').map((header) => header.textContent?.trim())
  expect(headers.indexOf('用例 ID')).toBeGreaterThan(-1)
  expect(headers.indexOf('用例 ID')).toBeLessThan(headers.indexOf('用例名称'))
  expect(idButton.closest('td')?.nextElementSibling).toHaveTextContent('验证码错误 5 次锁定账号')

  const user = userEvent.setup()
  // user-event 会安装自己的 clipboard stub，必须在 setup 之后再替换。
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  await user.click(idButton)

  expect(writeText).toHaveBeenCalledWith(entry.caseId)
  expect(screen.queryByRole('button', { name: /返回用例列表/ })).not.toBeInTheDocument()
  client.clear()
})

it('列表可批量勾选，判定整条用例即时保存并显示已保存', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([entry]))
  const update = vi
    .spyOn(api, 'updateTestOrderEntry')
    .mockImplementation(async () => ({ ...entry, status: 'pending' }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  await within(entryList()).findByText('验证码错误 5 次锁定账号')
  const user = userEvent.setup()
  expect(screen.getByRole('button', { name: '未执行 1' })).toBeInTheDocument()

  await user.click(screen.getByRole('checkbox', { name: '选择第 1 条执行条目' }))
  expect(screen.getByText('已选 1 条')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /批量标记通过/ })).toBeEnabled()
  expect(screen.getByRole('button', { name: '生成所选图解（1）' })).toHaveTextContent('图解')
  expect(screen.getByRole('button', { name: '分配执行人（1）' })).toBeInTheDocument()
  await user.click(screen.getByRole('checkbox', { name: '选择第 1 条执行条目' }))
  expect(screen.queryByRole('button', { name: /批量标记通过/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /生成所选图解/ })).not.toBeInTheDocument()

  await openEntry(user, '验证码错误 5 次锁定账号')
  expect(await screen.findByText('账号锁定')).toBeInTheDocument()
  expect(screen.getByText('已注册手机号')).toBeInTheDocument()
  // 步骤只是只读说明，没有逐步判定按钮
  expect(screen.queryByRole('button', { name: /步骤 \d 判定/ })).toBeNull()

  await user.click(screen.getByRole('button', { name: '判定该用例为通过' }))

  await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
  expect(update.mock.calls[0][0]).toBe('order-1')
  expect(update.mock.calls[0][1]).toBe('entry-1')
  expect(update.mock.calls[0][2]).toEqual({ status: 'passed' })
  expect(await screen.findByText(/已保存/)).toBeInTheDocument()
  client.clear()
})

it('条目已分配给其他执行人时，非所有者不能判定', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(
    listResponse([{ ...entry, assigneeUserId: 'user-9' }]),
  )
  const update = vi.spyOn(api, 'updateTestOrderEntry').mockImplementation(async () => entry)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'member')
  renderWorkspace(client)

  const user = userEvent.setup()
  await within(entryList()).findByText('验证码错误 5 次锁定账号')
  await openEntry(user, '验证码错误 5 次锁定账号')

  expect(await screen.findByText('该条已分配给其他执行人')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '判定该用例为通过' })).toBeDisabled()
  expect(update).not.toHaveBeenCalled()
  client.clear()
})

it('项目所有者不受分配限制', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(
    listResponse([{ ...entry, assigneeUserId: 'user-9' }]),
  )
  vi.spyOn(api, 'updateTestOrderEntry').mockImplementation(async () => entry)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  const user = userEvent.setup()
  await within(entryList()).findByText('验证码错误 5 次锁定账号')
  await openEntry(user, '验证码错误 5 次锁定账号')
  await screen.findByText('账号锁定')
  expect(screen.getByRole('button', { name: '判定该用例为通过' })).toBeEnabled()
  client.clear()
})

it('可以在列表里移除执行条目', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([entry]))
  const remove = vi.spyOn(api, 'deleteTestOrderEntry').mockImplementation(async () => ({}))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '移除第 1 条执行条目' }))
  await user.click(await screen.findByRole('button', { name: /OK|确\s*定|确认移除/ }))

  await waitFor(() => expect(remove).toHaveBeenCalledTimes(1))
  expect(remove.mock.calls[0]).toEqual(['order-1', 'entry-1'])
  client.clear()
})

it('可以从用例库挑用例加入测试单', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () =>
    listResponse([
      {
        caseId: 'case-9',
        title: '库存不足时下单拦截提示',
        priority: 'P1',
        caseType: '功能测试',
        suiteName: '库存与履约',
      },
    ]),
  )
  const add = vi
    .spyOn(api, 'addTestOrderCases')
    .mockImplementation(async () => ({ addedCount: 1, skippedCount: 0 }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  const user = userEvent.setup()
  // 测试单没加载完时入口是禁用的，先等单子出来
  await screen.findByText('V2.3 回归测试单')
  // 空态与顶部各有一个入口，点哪个都打开同一个挑选用例的弹窗
  const addButtons = screen.getAllByRole('button', { name: '加入用例' })
  expect(addButtons).toHaveLength(2)
  await user.click(addButtons[0])

  // 按 aria-label 取勾选框：这个环境里 getByRole 每次都要遍历整棵 DOM
  const checkbox = await waitFor(() => {
    const node = document.querySelector('[aria-label="选择用例：库存不足时下单拦截提示"]')
    if (!node) throw new Error('挑选用例弹窗里还没有这条用例')
    return node as HTMLInputElement
  })
  await user.click(checkbox)
  await user.click(screen.getByRole('button', { name: /^加\s*入$/ }))

  await waitFor(() => expect(add).toHaveBeenCalledTimes(1))
  expect(add.mock.calls[0]).toEqual(['order-1', ['case-9']])
  client.clear()
})

it('在当前页面切换图谱并保留执行页筛选', async () => {
  useAuthStore.setState({ user: { userId: 'user-1' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([entry]))
  const graph = vi.spyOn(api, 'getTestOrderGraph')
  const open = vi.spyOn(window, 'open').mockReturnValue(null)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)
  await within(entryList()).findByText('验证码错误 5 次锁定账号')
  const user = userEvent.setup()
  const searchInput = await openEntryFilters(user)
  await user.type(searchInput, '锁定')
  await waitFor(() => expect(api.getTestOrderEntries).toHaveBeenLastCalledWith(
    'order-1', expect.objectContaining({ keyword: '锁定' }),
  ))
  await waitFor(() => expect(screen.getByText('验证码错误 5 次锁定账号')).toBeVisible())
  const graphToggle = screen.getByRole('button', { name: '用例图谱' })
  expect(graphToggle).toHaveAttribute('aria-pressed', 'false')
  await user.click(graphToggle)
  expect(open).not.toHaveBeenCalled()
  const graphViewToggle = screen.getByRole('button', { name: '用例图谱' })
  expect(graphViewToggle).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByTestId('inline-graph')).toHaveTextContent('order-1')
  expect(screen.getByText('验证码错误 5 次锁定账号')).not.toBeVisible()
  await user.click(graphViewToggle)
  await waitFor(() => expect(screen.getByRole('button', { name: '用例图谱' })).toHaveAttribute('aria-pressed', 'false'))
  await waitFor(() => expect(screen.getByRole('button', { name: /筛选执行用例，已启用 1 项/ })).toBeInTheDocument())
  await waitFor(() => expect(screen.getByText('验证码错误 5 次锁定账号')).toBeVisible())
  // 图谱首次打开后保持挂载，切回来只是隐藏，不会重新请求和全量布局。
  expect(screen.getByTestId('inline-graph')).not.toBeVisible()
  expect(screen.queryByRole('dialog', { name: '用例图谱' })).not.toBeInTheDocument()
  expect(graph).not.toHaveBeenCalled()
  client.clear()
})

it('快捷键说明按需显示，键盘切换详情时步骤与预期保持对应', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([
    entry,
    { ...entry, entryId: 'entry-2', orderNo: 2, caseTitle: '第二条用例', snapshot: { preconditions: [], steps: [{ action: '第二条操作', expected: '第二条预期' }] } },
  ]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)
  const user = userEvent.setup()
  await within(entryList()).findByText('验证码错误 5 次锁定账号')
  await openEntry(user, '验证码错误 5 次锁定账号')
  await screen.findByText('账号锁定')

  expect(screen.getByRole('button', { name: '上一条' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '下一条' })).toBeEnabled()
  expect(screen.queryByText(/快捷键：1 通过/)).not.toBeInTheDocument()
  const help = screen.getByRole('button', { name: '快捷键说明' })
  await user.hover(help)
  expect(await screen.findByText('快捷键：1 通过 · 2 失败 · 3 阻塞 · 4 跳过；↑ 上一条，↓ 下一条')).toBeInTheDocument()
  await user.unhover(help)
  expect(screen.getAllByRole('checkbox', { name: '判定后自动前进' })).toHaveLength(1)
  expect(screen.getByRole('checkbox', { name: '判定后自动前进' })).not.toBeChecked()

  await user.keyboard('{ArrowDown}')
  expect(await screen.findByText('第二条操作')).toBeInTheDocument()
  expect(screen.getByText('第二条预期')).toBeInTheDocument()
  expect(screen.getByText(/全单第 2 条 · 筛选共 2 条/)).toBeInTheDocument()
  await user.keyboard('{ArrowDown}')
  expect(screen.getByText('第二条操作')).toBeInTheDocument()
  await user.keyboard('{ArrowUp}')
  expect(await screen.findByText('账号锁定')).toBeInTheDocument()
  client.clear()
})

it('切换条目时详情面板常驻，pending 条目不查关联 Bug', async () => {
  useAuthStore.setState({ user: { userId: 'user-1' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([
    entry,
    { ...entry, entryId: 'entry-2', orderNo: 2, caseTitle: '第二条用例' },
  ]))
  // 第二条的详情一直不返回，模拟慢接口。
  vi.mocked(api.getTestOrderEntry).mockImplementation(async (_orderId, id) => {
    if (id === 'entry-2') return new Promise<never>(() => {})
    return entry
  })
  const bugs = vi.spyOn(api, 'getProjectBugs').mockResolvedValue(listResponse([]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  const { container } = renderWorkspace(client)

  const user = userEvent.setup()
  await within(entryList()).findByText('验证码错误 5 次锁定账号')
  await openEntry(user, '验证码错误 5 次锁定账号')
  await screen.findByText('账号锁定')
  // pending 条目不会有关联 Bug，键盘逐条审查时不再逐条发请求。
  expect(bugs).not.toHaveBeenCalled()

  await user.click(screen.getByRole('button', { name: '下一条' }))

  // 摘要和判定条用列表里的数据先撑住，只有步骤内容区等待详情。
  expect(container.querySelector('.test-order-case-summary')).toHaveTextContent('第二条用例')
  expect(screen.getByText('加载执行详情…')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '判定该用例为通过' })).toBeDisabled()
  expect(bugs).not.toHaveBeenCalled()
  client.clear()
})

it('图谱视图停用隐藏执行页快捷键，切回后恢复', async () => {
  useAuthStore.setState({ user: { userId: 'user-1' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([entry]))
  vi.spyOn(window, 'open').mockReturnValue(null)
  const update = vi.spyOn(api, 'updateTestOrderEntry').mockResolvedValue({ ...entry, status: 'passed' })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)
  const user = userEvent.setup()
  await within(entryList()).findByText('验证码错误 5 次锁定账号')
  const graphToggle = screen.getByRole('button', { name: '用例图谱' })
  await user.click(graphToggle)
  await user.keyboard('1')
  expect(update).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: '用例图谱' }))
  await openEntry(user, '验证码错误 5 次锁定账号')
  await user.keyboard('1')
  await waitFor(() => expect(update).toHaveBeenCalledWith('order-1', 'entry-1', { status: 'passed' }))
  client.clear()
})

it('从 Bug 详情跳转时选中指定执行条目', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', name: '小明' } })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue(order)
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([
    entry, { ...entry, entryId: 'entry-2', caseTitle: '第二条用例', orderNo: 2,
      snapshot: { ...entry.snapshot, preconditions: ['指定来源的执行前置条件'] } },
  ]))
  vi.spyOn(api, 'getProjectMembers').mockResolvedValue(listResponse([]))
  vi.spyOn(api, 'getProjectBugs').mockResolvedValue(listResponse([]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client, '/test-orders/order-1?entryId=entry-2')
  expect(await screen.findByText('指定来源的执行前置条件')).toBeInTheDocument()
  expect(screen.queryByText('已注册手机号')).not.toBeInTheDocument()
  client.clear()
})

it('深链定位第二页详情，详情上下条支持跨页并保留列表筛选', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  const all = Array.from({ length: 25 }, (_, index) => ({ ...entry, entryId: `entry-${index + 1}`, caseId: `case-${index + 1}`, caseTitle: `page case ${index + 1}`, orderNo: index + 1 }))
  vi.spyOn(api, 'getTestOrder').mockResolvedValue({ ...order, entriesTotal: 25 })
  const lists = vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async (_, filters = {}) => {
    const focus = all.findIndex((item) => item.entryId === filters.focusEntryId)
    const page = focus >= 0 ? Math.floor(focus / 20) + 1 : filters.page ?? 1
    const items = all.slice((page - 1) * 20, page * 20).map((item) => { const summary: TestOrderEntry = { ...item }; delete summary.snapshot; return summary })
    return { ...listResponse(items), items, page, total: 25, orderTotal: 25, matchedTotal: 25, preferredEntryId: focus >= 0 ? all[focus].entryId : items[0]?.entryId ?? '' }
  })
  const details = vi.spyOn(api, 'getTestOrderEntry').mockImplementation(async (_, id) => all.find((item) => item.entryId === id)!)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client, '/?entryId=entry-24')
  expect(await screen.findByText(/全单第 24 条 · 筛选共 25 条/)).toBeInTheDocument()
  expect(details).toHaveBeenCalledWith('order-1', 'entry-24')
  expect(lists).toHaveBeenCalledWith('order-1', expect.objectContaining({ focusEntryId: 'entry-24' }))

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '下一条' }))
  expect(await screen.findByText(/全单第 25 条 · 筛选共 25 条/)).toBeInTheDocument()
  expect(details).toHaveBeenCalledWith('order-1', 'entry-25')
  expect(screen.getByRole('button', { name: '下一条' })).toBeDisabled()

  await user.click(screen.getByRole('button', { name: '上一条' }))
  await user.click(screen.getByRole('button', { name: '上一条' }))
  await user.click(screen.getByRole('button', { name: '上一条' }))
  await user.click(screen.getByRole('button', { name: '上一条' }))
  expect(await screen.findByText(/全单第 21 条 · 筛选共 25 条/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '上一条' }))
  expect(await screen.findByText(/全单第 20 条 · 筛选共 25 条/)).toBeInTheDocument()
  expect(details).toHaveBeenCalledWith('order-1', 'entry-20')
  expect(lists).toHaveBeenLastCalledWith('order-1', expect.objectContaining({ page: 1 }))

  await user.click(screen.getByRole('button', { name: /返回用例列表/ }))
  expect(await screen.findByText('page case 20')).toBeVisible()
  await user.click(screen.getByRole('checkbox', { name: '选择第 20 条执行条目' }))
  await user.click(screen.getByTitle('2'))
  await user.click(await screen.findByRole('checkbox', { name: '选择第 24 条执行条目' }))
  expect(screen.getByText('已选 2 条')).toBeVisible()
  client.clear()
})

it('列表按接口顺序展示，键盘按同一顺序切换详情', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue({ ...order, entriesTotal: 3, entriesExecuted: 2 })
  const passed = {
    ...entry, entryId: 'entry-passed', orderNo: 1, caseTitle: '已通过用例', status: 'passed',
    snapshot: { preconditions: ['通过用例前置'], steps: [{ action: '通过操作', expected: '通过预期' }] },
  }
  const failed = {
    ...entry, entryId: 'entry-failed', orderNo: 2, caseTitle: '失败用例', status: 'failed',
    snapshot: { preconditions: ['失败用例前置'], steps: [{ action: '失败操作', expected: '失败预期' }] },
  }
  const pending = {
    ...entry, entryId: 'entry-pending', orderNo: 3, caseTitle: '未执行用例', status: 'pending',
    snapshot: { preconditions: ['未执行用例前置'], steps: [{ action: '未执行操作', expected: '未执行预期' }] },
  }
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([passed, failed, pending]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  await within(entryList()).findByText('已通过用例')
  const user = userEvent.setup()
  await openEntry(user, '已通过用例')
  await screen.findByText('通过预期')
  await user.keyboard('{ArrowDown}')
  expect(await screen.findByText('失败预期')).toBeInTheDocument()
  await user.keyboard('{ArrowDown}')
  expect(await screen.findByText('未执行预期')).toBeInTheDocument()
  client.clear()
})

it('状态进度条按执行结论查询，清除筛选恢复列表', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue({ ...order, entriesTotal: 3, entriesExecuted: 1 })
  const pending = { ...entry, entryId: 'entry-pending', orderNo: 1, caseTitle: '待执行筛选用例' }
  const failed = { ...entry, entryId: 'entry-failed', orderNo: 2, caseTitle: '失败筛选用例', status: 'failed' }
  const passed = { ...entry, entryId: 'entry-passed', orderNo: 3, caseTitle: '通过筛选用例', status: 'passed' }
  const all = [pending, failed, passed]
  const allCounts = { pending: 1, passed: 1, failed: 1, blocked: 0, skipped: 0 }
  const lists = vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async (_, filters = {}) => {
    const items = filters.status ? all.filter((item) => item.status === filters.status) : all
    // 与后端一致：statusCounts / matchedTotal 是状态筛选前的口径，total 才是当前结果数。
    return { ...listResponse(items), total: items.length, matchedTotal: all.length, statusCounts: allCounts }
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  await within(entryList()).findByText('待执行筛选用例')
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '失败 1' }))

  await waitFor(() => expect(lists).toHaveBeenLastCalledWith(
    'order-1', expect.objectContaining({ status: 'failed' }),
  ))
  expect(screen.getByRole('button', { name: '失败 1' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: '通过 1' })).toHaveClass('is-dim')
  expect(await within(entryList()).findByText('失败筛选用例')).toBeInTheDocument()
  expect(within(entryList()).queryByText('待执行筛选用例')).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '失败 1' }))
  await waitFor(() => expect(lists).toHaveBeenLastCalledWith(
    'order-1', expect.objectContaining({ status: '' }),
  ))
  expect(await within(entryList()).findByText('待执行筛选用例')).toBeInTheDocument()
  client.clear()
})

it('筛选无结果时提供清除筛选并恢复列表', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue({ ...order, entriesTotal: 1, entriesExecuted: 0 })
  const pending = { ...entry, entryId: 'entry-pending', orderNo: 1, caseTitle: '待执行筛选用例' }
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async (_, filters = {}) => {
    return listResponse(filters.keyword === '不存在' ? [] : [pending])
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  await within(entryList()).findByText('待执行筛选用例')
  const user = userEvent.setup()
  const searchInput = await openEntryFilters(user)
  await user.type(searchInput, '不存在')
  expect(await screen.findByText('没有符合筛选条件的执行条目')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '清除筛选' }))
  expect(await within(entryList()).findByText('待执行筛选用例')).toBeInTheDocument()
  client.clear()
})

it('返回用例列表保留筛选条件', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue({ ...order, entriesTotal: 2, entriesExecuted: 1 })
  const pending = { ...entry, entryId: 'entry-pending', orderNo: 1, caseTitle: '待执行筛选用例' }
  const failed = { ...entry, entryId: 'entry-failed', orderNo: 2, caseTitle: '失败筛选用例', status: 'failed' }
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async (_, filters = {}) => {
    const items = filters.status ? [pending, failed].filter((item) => item.status === filters.status) : [pending, failed]
    return listResponse(items)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  await within(entryList()).findByText('待执行筛选用例')
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '失败 1' }))
  await within(entryList()).findByText('失败筛选用例')
  await openEntry(user, '失败筛选用例')
  await user.click(screen.getByRole('button', { name: /返回用例列表/ }))
  expect(screen.getByRole('button', { name: '失败 1' })).toHaveAttribute('aria-pressed', 'true')
  expect(within(entryList()).getByText('失败筛选用例')).toBeVisible()
  expect(within(entryList()).queryByText('待执行筛选用例')).not.toBeInTheDocument()
  client.clear()
})
