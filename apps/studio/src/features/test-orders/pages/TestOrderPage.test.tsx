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
  const panel = document.querySelector('.test-orders-page .tp-list-panel')!
  expect(panel.querySelector('.tp-list-body .tp-list-scroll')).not.toBeNull()
  expect(panel.querySelector('.tp-list-body > .table-footer')).not.toBeNull()
  expect(panel.querySelector('.tp-list-scroll .table-footer')).toBeNull()
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

it('分页展示真实测试单并在搜索后回到第一页', async () => {
  const rows = Array.from({ length: 25 }, (_, index) => ({ ...order, orderId: `order-${index}`, name: `分页测试单 ${index + 1}` }))
  vi.spyOn(api, 'getProjectTestOrders').mockResolvedValue(listResponse(rows))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)
  const user = userEvent.setup()
  await screen.findByText('分页测试单 1')
  expect(screen.queryByText('分页测试单 21')).not.toBeInTheDocument()
  await user.click(screen.getByTitle('2'))
  expect(await screen.findByText('分页测试单 21')).toBeInTheDocument()
  expect(screen.queryByText('分页测试单 1')).not.toBeInTheDocument()
  await user.type(screen.getByPlaceholderText('搜索测试单名称 / 被测版本'), '分页测试单 1')
  expect(await screen.findByText('分页测试单 1')).toBeInTheDocument()
  expect(screen.queryByText('分页测试单 21')).not.toBeInTheDocument()
  expect(screen.getByText('显示第 1 条 - 第 11 条，共 11 条')).toBeInTheDocument()
  client.clear()
})
