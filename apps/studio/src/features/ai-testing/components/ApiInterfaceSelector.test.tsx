import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { ApiInterfaceSelector } from './ApiInterfaceSelector'

vi.mock('@/features/interface-library/api/interfaceLibrary.api', () => ({
  interfaceLibraryApi: {
    getRequirementSoftwareRepositories: vi.fn(),
    getSoftwareRepositoryApiInterfaces: vi.fn(),
    getProjectApiInterfaces: vi.fn(),
  },
}))

const clients: QueryClient[] = []
afterEach(() => {
  cleanup()
  clients.forEach(client => client.clear())
  clients.length = 0
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function renderSelector(
  onChange = vi.fn(),
  suggestedRepositories?: { gitRepositoryId: string; pathWithNamespace?: string }[],
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  clients.push(client)
  render(
    <TestThemeProvider>
      <QueryClientProvider client={client}>
        <ApiInterfaceSelector
          projectId="project-1"
          requirementId="requirement-1"
          value={[]}
          onChange={onChange}
          suggestedRepositories={suggestedRepositories}
        />
      </QueryClientProvider>
    </TestThemeProvider>,
  )
  return onChange
}

function interfaceItem(
  interfaceId: string,
  method: string,
  path: string,
  softwareRepositoryId = 'repository-1',
  softwareRepositoryName = '订单服务',
  tags: string[] = [],
) {
  return {
    interfaceId,
    softwareRepositoryId,
    softwareRepositoryName,
    name: `${method} ${path}`,
    method,
    path,
    description: '',
    tags,
    requirements: [],
    sourceType: 'manual',
  }
}

/** 150 条接口、每页 100 条的两页响应。 */
function pagedInterfaces(page = 1) {
  const start = (page - 1) * 100
  const items = Array.from({ length: page === 1 ? 100 : 50 }, (_, index) =>
    interfaceItem(`interface-${start + index + 1}`, 'GET', `/items/${start + index + 1}`),
  )
  return Object.assign(items, { items, total: 150 })
}

async function selectAllVisible(user: ReturnType<typeof userEvent.setup>) {
  // 筛选工具条要等接口加载完才出现。
  await user.click(await screen.findByLabelText('按软件仓库筛选'))
  await user.click(await screen.findByTitle('订单服务'))
  const button = screen.getByRole('button', { name: '全选筛选结果' })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
}

it('项目接口超过一页时取完剩余页，「全选」覆盖全部结果', async () => {
  vi.mocked(interfaceLibraryApi.getRequirementSoftwareRepositories).mockResolvedValue(listResponse([]))
  const list = vi.mocked(interfaceLibraryApi.getProjectApiInterfaces).mockImplementation(async (_projectId, filters = {}) =>
    pagedInterfaces(filters.page ?? 1))
  const onChange = renderSelector()

  await screen.findByText('项目全部软件仓库')
  await selectAllVisible(userEvent.setup())

  expect(onChange).toHaveBeenCalledTimes(1)
  expect(onChange.mock.calls[0][0]).toHaveLength(150)
  expect(list.mock.calls.map(([, filters]) => filters?.page)).toEqual([1, 2])
})

it('仓库接口超过一页时同样取完剩余页', async () => {
  vi.mocked(interfaceLibraryApi.getRequirementSoftwareRepositories).mockResolvedValue(
    listResponse([
      {
        requirementId: 'requirement-1',
        softwareRepositoryId: 'repository-1',
        softwareRepositoryName: '订单服务',
        basePath: '/api',
        repository: null,
        branch: 'main',
        baselineBranch: 'main',
      },
    ]),
  )
  const list = vi.mocked(interfaceLibraryApi.getSoftwareRepositoryApiInterfaces).mockImplementation(async (_id, filters = {}) =>
    pagedInterfaces(filters.page ?? 1))
  const onChange = renderSelector()

  await screen.findByText('需求关联软件仓库（1）')
  await selectAllVisible(userEvent.setup())

  expect(onChange.mock.calls[0][0]).toHaveLength(150)
  expect(list.mock.calls.map(([, filters]) => filters?.page)).toEqual([1, 2])
})

it('按软件仓库筛选后可全选筛选结果', async () => {
  vi.mocked(
    interfaceLibraryApi.getRequirementSoftwareRepositories,
  ).mockResolvedValue(
    listResponse([
      {
        requirementId: 'requirement-1',
        softwareRepositoryId: 'repository-1',
        softwareRepositoryName: '订单服务',
        basePath: '/api',
        repository: {
          projectId: 'repo-1',
          path: 'commerce/order-service',
          name: 'order-service',
          instanceUrl: 'https://gitlab.example.com',
        },
        branch: 'dev',
        baselineBranch: 'main',
      },
    ]),
  )
  vi.mocked(
    interfaceLibraryApi.getSoftwareRepositoryApiInterfaces,
  ).mockResolvedValue(
    listResponse([
      interfaceItem('interface-1', 'POST', '/orders'),
      interfaceItem('interface-2', 'GET', '/orders/{id}'),
    ]),
  )
  const user = userEvent.setup()
  const onChange = renderSelector()

  expect(
    await screen.findByText('需求关联软件仓库（1）'),
  ).toBeInTheDocument()
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: '全选筛选结果' }),
    ).toBeDisabled(),
  )
  await user.click(screen.getByLabelText('按软件仓库筛选'))
  await user.click(await screen.findByTitle('订单服务'))
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: '全选筛选结果' }),
    ).toBeEnabled(),
  )
  await user.click(screen.getByRole('button', { name: '全选筛选结果' }))

  expect(onChange).toHaveBeenCalledWith(['interface-1', 'interface-2'])
})

it('按标签筛选后只显示并全选匹配接口', async () => {
  vi.mocked(
    interfaceLibraryApi.getRequirementSoftwareRepositories,
  ).mockResolvedValue(
    listResponse([
      {
        requirementId: 'requirement-1',
        softwareRepositoryId: 'repository-1',
        softwareRepositoryName: '订单服务',
        basePath: '/api',
        repository: {
          projectId: 'repo-1',
          path: 'commerce/order-service',
          name: 'order-service',
          instanceUrl: 'https://gitlab.example.com',
        },
        branch: 'dev',
        baselineBranch: 'main',
      },
    ]),
  )
  vi.mocked(
    interfaceLibraryApi.getSoftwareRepositoryApiInterfaces,
  ).mockResolvedValue(
    listResponse([
      interfaceItem('interface-1', 'POST', '/orders', 'repository-1', '订单服务', ['订单']),
      interfaceItem('interface-2', 'GET', '/health', 'repository-1', '订单服务', ['支付']),
      interfaceItem('interface-3', 'GET', '/untagged', 'repository-1', '订单服务'),
    ]),
  )
  const user = userEvent.setup()
  const onChange = renderSelector()

  expect(
    await screen.findByText('需求关联软件仓库（1）'),
  ).toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: '全选筛选结果' }),
  ).toBeDisabled()
  await user.click(await screen.findByLabelText('按标签筛选'))
  await user.click(await screen.findByTitle('订单'))
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: '全选筛选结果' }),
    ).toBeEnabled(),
  )

  await user.click(screen.getByLabelText('选择接口'))
  expect(await screen.findByText('POST /orders · 订单服务')).toBeInTheDocument()
  expect(screen.queryByText('GET /health · 订单服务')).not.toBeInTheDocument()
  expect(screen.queryByText('GET /untagged · 订单服务')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '全选筛选结果' }))

  expect(onChange).toHaveBeenCalledWith(['interface-1'])
})

it('需求未关联软件仓库时回退到项目全部接口并提示', async () => {
  vi.mocked(
    interfaceLibraryApi.getRequirementSoftwareRepositories,
  ).mockResolvedValue(listResponse([]))
  vi.mocked(interfaceLibraryApi.getProjectApiInterfaces).mockResolvedValue(
    listResponse([interfaceItem('interface-1', 'POST', '/orders')]),
  )

  renderSelector()

  expect(
    await screen.findByText('该需求尚未关联软件仓库，已展示项目全部接口。'),
  ).toBeInTheDocument()
  expect(interfaceLibraryApi.getProjectApiInterfaces).toHaveBeenCalledWith(
    'project-1',
    { keyword: '', page: 1, pageSize: 100 },
  )
})

it('仓库画像建议的后端仓库作为默认范围，仍可切换其他软件仓库', async () => {
  vi.mocked(
    interfaceLibraryApi.getRequirementSoftwareRepositories,
  ).mockResolvedValue(
    listResponse([
      {
        requirementId: 'requirement-1',
        softwareRepositoryId: 'repository-1',
        softwareRepositoryName: '订单服务',
        basePath: '/api',
        repository: {
          projectId: 'repo-1',
          path: 'commerce/order-service',
          name: 'order-service',
          instanceUrl: 'https://gitlab.example.com',
        },
        branch: 'dev',
        baselineBranch: 'main',
      },
      {
        requirementId: 'requirement-1',
        softwareRepositoryId: 'repository-2',
        softwareRepositoryName: '支付服务',
        basePath: '/api',
        repository: {
          projectId: 'gitlab-repo-2',
          path: 'commerce/payment-service',
          name: 'payment-service',
          instanceUrl: 'https://gitlab.example.com',
        },
        branch: 'dev',
        baselineBranch: 'main',
      },
    ]),
  )
  vi.mocked(
    interfaceLibraryApi.getSoftwareRepositoryApiInterfaces,
  ).mockResolvedValue(
    listResponse([
      interfaceItem('interface-2', 'GET', '/health', 'repository-2', '支付服务'),
    ]),
  )
  vi.mocked(interfaceLibraryApi.getProjectApiInterfaces).mockResolvedValue(
    listResponse([
      interfaceItem('interface-1', 'POST', '/orders'),
      interfaceItem('interface-2', 'GET', '/health', 'repository-2', '支付服务'),
    ]),
  )
  const user = userEvent.setup()
  renderSelector(vi.fn(), [
    { gitRepositoryId: 'gitlab-repo-2', pathWithNamespace: 'team/payment' },
  ])

  expect(await screen.findByText('画像建议仓库（1）')).toBeInTheDocument()
  expect(
    screen.getByText(/建议来自仓库画像，仅用于缩小接口范围/),
  ).toBeInTheDocument()
  await waitFor(() =>
    expect(
      interfaceLibraryApi.getSoftwareRepositoryApiInterfaces,
    ).toHaveBeenCalledWith('repository-2', {
      keyword: '',
      page: 1,
      pageSize: 100,
    }),
  )
  expect(
    interfaceLibraryApi.getSoftwareRepositoryApiInterfaces,
  ).not.toHaveBeenCalledWith('repository-1', expect.anything())

  await user.click(screen.getByRole('button', { name: '仅看需求关联仓库' }))
  expect(
    await screen.findByText('需求关联软件仓库（2）'),
  ).toBeInTheDocument()
  await waitFor(() =>
    expect(
      interfaceLibraryApi.getSoftwareRepositoryApiInterfaces,
    ).toHaveBeenCalledWith('repository-1', {
      keyword: '',
      page: 1,
      pageSize: 100,
    }),
  )
  await waitFor(() =>
    expect(
      interfaceLibraryApi.getSoftwareRepositoryApiInterfaces,
    ).toHaveBeenCalledWith('repository-2', {
      keyword: '',
      page: 1,
      pageSize: 100,
    }),
  )

  await user.click(screen.getByRole('button', { name: '按画像建议' }))
  expect(await screen.findByText('画像建议仓库（1）')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '显示项目全部接口' }))
  expect(await screen.findByText('项目全部软件仓库')).toBeInTheDocument()
  await waitFor(() =>
    expect(interfaceLibraryApi.getProjectApiInterfaces).toHaveBeenCalledWith(
      'project-1',
      { keyword: '', page: 1, pageSize: 100 },
    ),
  )
})
