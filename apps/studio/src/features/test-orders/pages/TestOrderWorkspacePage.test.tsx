import type { TestOrderEntry } from '../types'
import { ConfigProvider } from 'antd'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type User } from '@/services/api'
import { TestOrderWorkspacePage } from './TestOrderWorkspacePage'

vi.mock('../components/TestOrderGraphViewer', () => ({ TestOrderGraphViewer: ({ orderId }: { orderId: string }) => <div data-testid="inline-graph">内嵌用例图谱 {orderId}</div> }))

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
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
})

it('判定整条用例即时保存并显示已保存', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockImplementation(async () => order)
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async () => listResponse([entry]))
  const update = vi
    .spyOn(api, 'updateTestOrderEntry')
    .mockImplementation(async () => ({ ...entry, status: 'pending' }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  expect(await screen.findByText('账号锁定')).toBeInTheDocument()
  expect(screen.getByText('已注册手机号')).toBeInTheDocument()
  // 步骤只是只读说明，没有逐步判定按钮
  expect(screen.queryByRole('button', { name: /步骤 \d 判定/ })).toBeNull()

  const user = userEvent.setup()
  const panel = document.querySelector('.test-order-side-panel')
  expect(panel).not.toBeNull()
  expect(screen.getByRole('button', { name: '未执行 1' })).toBeInTheDocument()
  expect(panel?.querySelector('.test-order-list-head')).toContainElement(screen.getByTitle('1'))
  expect(panel?.querySelector('.table-footer')).toBeNull()
  expect(screen.queryByRole('button', { name: /批量标记通过/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /生成所选图解/ })).not.toBeInTheDocument()
  await user.click(screen.getByRole('checkbox', { name: '选择第 1 条执行条目' }))
  expect(screen.getByText('已选 1 条')).toBeInTheDocument()
  const selectionBar = panel?.querySelector('.test-order-selection-bar')
  expect(selectionBar).not.toBeNull()
  expect(panel?.lastElementChild).toBe(selectionBar)
  expect(screen.getByRole('button', { name: /批量标记通过/ })).toBeEnabled()
  expect(screen.getByRole('button', { name: '生成所选图解（1）' })).toHaveTextContent('图解')
  expect(screen.getByRole('button', { name: '分配执行人（1）' })).toBeInTheDocument()
  await user.click(screen.getByRole('checkbox', { name: '选择第 1 条执行条目' }))
  expect(screen.queryByRole('button', { name: /批量标记通过/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /生成所选图解/ })).not.toBeInTheDocument()
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
  vi.spyOn(api, 'getTestOrder').mockImplementation(async () => order)
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async () =>
    listResponse([{ ...entry, assigneeUserId: 'user-9' }]),
  )
  const update = vi.spyOn(api, 'updateTestOrderEntry').mockImplementation(async () => entry)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'member')
  renderWorkspace(client)

  expect(await screen.findByText('该条已分配给其他执行人')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '判定该用例为通过' })).toBeDisabled()
  expect(update).not.toHaveBeenCalled()
  client.clear()
})

it('项目所有者不受分配限制', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockImplementation(async () => order)
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async () =>
    listResponse([{ ...entry, assigneeUserId: 'user-9' }]),
  )
  vi.spyOn(api, 'updateTestOrderEntry').mockImplementation(async () => entry)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  await screen.findByText('账号锁定')
  expect(screen.getByRole('button', { name: '判定该用例为通过' })).toBeEnabled()
  client.clear()
})

it('可以在工作台里移除执行条目', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockImplementation(async () => order)
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async () => listResponse([entry]))
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

it('可以在工作台里从用例库挑用例加入测试单', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockImplementation(async () => order)
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async () => listResponse([]))
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
  await screen.findByText('账号锁定')
  const user = userEvent.setup()
  await user.type(screen.getByPlaceholderText('搜索用例 ID 或关键字'), '锁定')
  await waitFor(() => expect(api.getTestOrderEntries).toHaveBeenLastCalledWith(
    'order-1', expect.objectContaining({ keyword: '锁定' }),
  ))
  await waitFor(() => expect(screen.getByText('账号锁定')).toBeVisible())
  await user.click(screen.getByText('用例图谱', { exact: true }))
  expect(open).not.toHaveBeenCalled()
  expect(screen.getByTestId('inline-graph')).toHaveTextContent('order-1')
  expect(screen.getByText('账号锁定')).not.toBeVisible()
  await user.click(screen.getByText('用例执行', { exact: true }))
  expect(screen.getByPlaceholderText('搜索用例 ID 或关键字')).toHaveValue('锁定')
  await waitFor(() => expect(screen.getByText('账号锁定')).toBeVisible())
  // 图谱首次打开后保持挂载，切回来只是隐藏，不会重新请求和全量布局。
  expect(screen.getByTestId('inline-graph')).not.toBeVisible()
  expect(screen.queryByRole('dialog', { name: '用例图谱' })).not.toBeInTheDocument()
  expect(graph).not.toHaveBeenCalled()
  client.clear()
})

it('快捷键说明按需显示，键盘切换详情时步骤与预期保持对应', async () => {
  useAuthStore.setState({ user: { userId: 'user-1' } as User })
  vi.spyOn(api, 'getTestOrder').mockImplementation(async () => order)
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async () => listResponse([
    entry,
    { ...entry, entryId: 'entry-2', orderNo: 2, caseTitle: '第二条用例', snapshot: { preconditions: [], steps: [{ action: '第二条操作', expected: '第二条预期' }] } },
  ]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)
  const user = userEvent.setup()
  await screen.findByText('账号锁定')
  expect(screen.queryByRole('button', { name: '上一条' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '下一条' })).not.toBeInTheDocument()
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  const help = screen.getByRole('button', { name: '快捷键说明' })
  await user.hover(help)
  expect(await screen.findByRole('tooltip')).toHaveTextContent('1 通过 · 2 失败 · 3 阻塞 · 4 跳过；↑ 上一条，↓ 下一条')
  await user.unhover(help)
  expect(screen.getAllByRole('checkbox', { name: '判定后自动前进' })).toHaveLength(1)
  expect(screen.getByRole('checkbox', { name: '判定后自动前进' })).not.toBeChecked()
  const firstItem = screen.getByRole('button', { name: /验证码错误 5 次锁定账号/ })
  const secondItem = screen.getByRole('button', { name: /第二条用例/ })
  await user.click(firstItem)
  await user.keyboard('{ArrowDown}')
  expect(secondItem).toHaveFocus()
  expect(await screen.findByText('第二条操作')).toBeInTheDocument()
  expect(screen.getByText('第二条预期')).toBeInTheDocument()
  expect(screen.getByText(/本页第 2 \/ 2 条/)).toBeInTheDocument()
  await user.keyboard('{ArrowDown}')
  expect(screen.getByText('第二条操作')).toBeInTheDocument()
  await user.keyboard('{ArrowUp}')
  expect(firstItem).toHaveFocus()
  expect(await screen.findByText('账号锁定')).toBeInTheDocument()
  client.clear()
})

it('切换条目时详情面板常驻，pending 条目不查关联 Bug', async () => {
  useAuthStore.setState({ user: { userId: 'user-1' } as User })
  vi.spyOn(api, 'getTestOrder').mockImplementation(async () => order)
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async () => listResponse([
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

  await screen.findByText('账号锁定')
  // pending 条目不会有关联 Bug，键盘逐条审查时不再逐条发请求。
  expect(bugs).not.toHaveBeenCalled()

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /第二条用例/ }))

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
  await screen.findByText('账号锁定')
  await user.click(screen.getByText('用例图谱', { exact: true }))
  await user.keyboard('1')
  expect(update).not.toHaveBeenCalled()
  await user.click(screen.getByText('用例执行', { exact: true }))
  await user.click(screen.getByText('账号锁定'))
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

it('定位第二页详情，保留跨页选择，并支持键盘跨页', async () => {
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
  await screen.findByText(/本页第 4 \/ 5 条/)
  expect(details).toHaveBeenCalledWith('order-1', 'entry-24')
  expect(lists).toHaveBeenCalledWith('order-1', expect.objectContaining({ focusEntryId: 'entry-24' }))
  const user = userEvent.setup()
  await user.click(screen.getByRole('checkbox', { name: '选择第 24 条执行条目' }))
  await user.click(screen.getByTitle('1'))
  await user.click(await screen.findByRole('checkbox', { name: '选择第 1 条执行条目' }))
  expect(screen.getByText('已选 2 条')).toBeVisible()
  await user.click(screen.getByRole('button', { name: /page case 20/ }))
  await user.keyboard('{ArrowDown}')
  const next = await screen.findByRole('button', { name: /page case 21/ })
  await waitFor(() => expect(next).toHaveFocus())
  expect(details).toHaveBeenCalledWith('order-1', 'entry-21')
  client.clear()
})

it('清单按通过、失败、未执行分组，键盘按分组顺序切换', async () => {
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
  // API order differs from the grouped order, so the assertion proves keyboard navigation
  // follows the visible grouped list rather than the raw response.
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([pending, failed, passed]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  const { container } = renderWorkspace(client)

  await screen.findByRole('button', { name: /已通过用例/ })
  expect(screen.getByRole('img', { name: /执行结果分布/ })).toHaveAccessibleName(
    '执行结果分布：通过 1 条，失败 1 条，未执行 1 条',
  )
  expect([...container.querySelectorAll('.test-order-group-head')]
    .map((node) => node.getAttribute('aria-label'))).toEqual(['通过 1', '失败 1', '未执行 1'])

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /已通过用例/ }))
  await user.keyboard('{ArrowDown}')
  const failedItem = screen.getByRole('button', { name: /失败用例/ })
  await waitFor(() => expect(failedItem).toHaveFocus())
  expect(await screen.findByText('失败用例前置')).toBeInTheDocument()
  client.clear()
})

it('筛选浮层选择执行结论后按状态查询，并显示可移除条件', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue({ ...order, entriesTotal: 3, entriesExecuted: 1 })
  const pending = { ...entry, entryId: 'entry-pending', orderNo: 1, caseTitle: '待执行筛选用例' }
  const failed = { ...entry, entryId: 'entry-failed', orderNo: 2, caseTitle: '失败筛选用例', status: 'failed' }
  const passed = { ...entry, entryId: 'entry-passed', orderNo: 3, caseTitle: '通过筛选用例', status: 'passed' }
  const all = [pending, failed, passed]
  const lists = vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async (_, filters = {}) => {
    const items = filters.status ? all.filter((item) => item.status === filters.status) : all
    return listResponse(items)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  await screen.findByRole('button', { name: /待执行筛选用例/ })
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '筛选执行条目' }))
  await user.click(await screen.findByRole('menuitemradio', { name: '失败 1' }))

  await waitFor(() => expect(lists).toHaveBeenLastCalledWith(
    'order-1', expect.objectContaining({ status: 'failed' }),
  ))
  expect(await screen.findByRole('button', { name: '清除状态筛选' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /失败筛选用例/ })).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '清除状态筛选' }))
  await waitFor(() => expect(lists).toHaveBeenLastCalledWith(
    'order-1', expect.objectContaining({ status: '' }),
  ))
  await waitFor(() => expect(screen.queryByRole('button', { name: '清除状态筛选' })).not.toBeInTheDocument())
  client.clear()
})

it('分组可以折叠，折叠后条目从清单中移除', async () => {
  useAuthStore.setState({ user: { userId: 'user-1', nickname: '张三' } as User })
  vi.spyOn(api, 'getTestOrder').mockResolvedValue({ ...order, entriesTotal: 2, entriesExecuted: 1 })
  const passed = { ...entry, entryId: 'entry-passed', orderNo: 1, caseTitle: '已通过可折叠用例', status: 'passed' }
  const pending = { ...entry, entryId: 'entry-pending', orderNo: 2, caseTitle: '待执行可折叠用例' }
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([passed, pending]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedAccess(client, 'owner')
  renderWorkspace(client)

  await screen.findByRole('button', { name: /待执行可折叠用例/ })
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '未执行 1' }))

  expect(screen.getByRole('button', { name: '未执行 1' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('button', { name: /待执行可折叠用例/ })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /已通过可折叠用例/ })).toBeInTheDocument()
  client.clear()
})
