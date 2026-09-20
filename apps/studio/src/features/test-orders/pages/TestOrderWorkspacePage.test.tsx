import { useAuthStore } from '@/features/auth/store/auth.store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type User } from '@/services/api'
import { TestOrderWorkspacePage } from './TestOrderWorkspacePage'

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
  return Object.assign([...items], { items, total: items.length })
}

function renderWorkspace(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TestOrderWorkspacePage />
      </MemoryRouter>
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

  expect(await screen.findByText('预期：账号锁定')).toBeInTheDocument()
  expect(screen.getByText('已注册手机号')).toBeInTheDocument()
  // 步骤只是只读说明，没有逐步判定按钮
  expect(screen.queryByRole('button', { name: /步骤 \d 判定/ })).toBeNull()

  const user = userEvent.setup()
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

  await screen.findByText('预期：账号锁定')
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
