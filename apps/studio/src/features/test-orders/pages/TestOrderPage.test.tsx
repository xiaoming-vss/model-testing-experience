import { seedOwnerProject } from '@/test/projectAccess'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { TestOrderPage } from './TestOrderPage'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/features/projects/hooks/useActiveSprint', () => ({
  useActiveSprint: () => ({
    activeSprintId: 'sprint-1',
    sprints: [{ sprintId: 'sprint-1', name: 'V2.3 迭代' }],
    sprintsQuery: { isLoading: false, error: null },
    selectSprint: vi.fn(),
    sprintSelectorOptions: [
      { label: '全部迭代', value: 'all' },
      { label: 'V2.3 迭代', value: 'sprint-1' },
    ],
  }),
}))

const order = {
  orderId: 'order-1',
  projectId: 'project-1',
  sprintId: 'sprint-1',
  name: 'V2.3 回归测试单',
  testedVersion: 'V2.3.1-rc2',
  entriesTotal: 4,
  entriesExecuted: 2,
  entriesPassed: 1,
  entriesFailed: 1,
  status: 'in_progress',
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TestOrderPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useWorkbenchStore.setState({ activeProjectId: 'project-1', activeSprintId: 'sprint-1' })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('按项目与迭代列出测试单并展示进度与状态', async () => {
  const orders = vi.spyOn(api, 'getProjectTestOrders').mockImplementation(async () => listResponse([order]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByText('V2.3 回归测试单')
  expect(screen.getAllByText('V2.3 迭代').length).toBeGreaterThan(0)
  expect(screen.getByText('V2.3.1-rc2')).toBeInTheDocument()
  // 进度条是图形，完整进度文案挂在它的无障碍名上（与抽屉 / 工作台同一套说法）
  expect(screen.getByRole('img', { name: '已执行 2/4 · 通过 1 · 失败 1' })).toBeInTheDocument()
  expect(screen.getByText('2/4')).toBeInTheDocument()
  expect(screen.getByText('通过 1')).toBeInTheDocument()
  expect(screen.getByText('失败 1')).toBeInTheDocument()
  // 执行率与状态胶囊（快速过滤条上也有「执行中」，所以状态胶囊限定在表格里取）
  expect(screen.getByText('50%')).toBeInTheDocument()
  const table = within(document.querySelector('.test-orders-table-scroll') as HTMLElement)
  expect(table.getByText('执行中')).toBeInTheDocument()
  expect(orders.mock.calls[0][0]).toBe('project-1')
  expect(orders.mock.calls[0][1]).toMatchObject({ sprintId: 'sprint-1' })
  client.clear()
})

it('快速过滤条按状态筛选，计数来自全部测试单', async () => {
  const inProgress = { ...order, orderId: 'order-1', name: '进行中的测试单' }
  const completed = { ...order, orderId: 'order-2', name: '已完成的测试单', status: 'completed' }
  vi.spyOn(api, 'getProjectTestOrders').mockImplementation(async () =>
    listResponse([inProgress, completed]),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  // 「已完成」在状态胶囊里也有，所以快速过滤条上的按钮要在条子里取
  // 计数来自列表本身，得等接口回来的那一帧再断言
  await screen.findByText('已完成的测试单')
  const quickbar = within(document.querySelector('.test-orders-quickbar') as HTMLElement)
  const allChip = quickbar.getByText('全部').closest('button') as HTMLElement
  const completedChip = quickbar.getByText('已完成').closest('button') as HTMLElement
  // 计数是「这个状态下有多少张」，不受当前筛选影响
  expect(allChip).toHaveTextContent('2')
  expect(completedChip).toHaveTextContent('1')

  const user = userEvent.setup()
  await user.click(completedChip)
  await waitFor(() => expect(screen.queryByText('进行中的测试单')).toBeNull())
  expect(screen.getByText('已完成的测试单')).toBeInTheDocument()
  expect(completedChip).toHaveAttribute('aria-pressed', 'true')

  // 同一档再点一次就是取消
  await user.click(completedChip)
  await waitFor(() => expect(screen.getByText('进行中的测试单')).toBeInTheDocument())
  client.clear()
})

it('刷新按钮重新拉取测试单列表', async () => {
  const orders = vi.spyOn(api, 'getProjectTestOrders').mockImplementation(async () => listResponse([order]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByText('V2.3 回归测试单')
  const callsBefore = orders.mock.calls.length
  await userEvent.setup().click(screen.getByLabelText('刷新测试单列表'))

  await waitFor(() => expect(orders.mock.calls.length).toBeGreaterThan(callsBefore))
  client.clear()
})

it('新建测试单提交后调用接口并刷新列表', async () => {
  vi.spyOn(api, 'getProjectTestOrders').mockImplementation(async () => listResponse([]))
  const created = vi.spyOn(api, 'createTestOrder').mockImplementation(async () => order)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  const { container } = renderPage(client)

  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '新建测试单' }))
  await user.type(await screen.findByLabelText('测试单名称'), '冒烟测试单')
  await user.type(screen.getByLabelText('被测版本'), 'V2.3.1')
  const saveButton = container.ownerDocument.querySelector('.action-btn-save')
  expect(saveButton).not.toBeNull()
  await user.click(saveButton as HTMLElement)

  await waitFor(() => expect(created).toHaveBeenCalledTimes(1))
  expect(created.mock.calls[0][0]).toBe('sprint-1')
  expect(created.mock.calls[0][1]).toMatchObject({
    name: '冒烟测试单',
    testedVersion: 'V2.3.1',
  })
  client.clear()
})
