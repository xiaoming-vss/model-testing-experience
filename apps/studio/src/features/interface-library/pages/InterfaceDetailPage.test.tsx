import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { seedOwnerProject } from '@/test/projectAccess'
import { ApiError } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { SoftwareRepository, ApiInterface, ApiInterfaceListItem } from '../types'
import { InterfaceDetailPage } from './InterfaceDetailPage'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))
vi.mock('../api/interfaceLibrary.api', () => ({
  interfaceLibraryApi: {
    getApiInterface: vi.fn(),
    getSoftwareRepositories: vi.fn(),
    getSoftwareRepositoryApiInterfaces: vi.fn(),
    createApiInterface: vi.fn(),
    updateApiInterface: vi.fn(),
    createApiInterfaceGroup: vi.fn(),
    renameApiInterfaceGroup: vi.fn(),
    deleteApiInterfaceGroup: vi.fn(),
    moveApiInterfaceToGroup: vi.fn(),
  },
}))
vi.mock('@/features/projects/hooks/useProjectRequirementOptions', () => ({
  useProjectRequirementOptions: () => ({
    allRequirements: [
      { requirementId: 'req-1', name: '下单流程', sprintId: 'sprint-1', sprintName: 'V1.0.0' },
    ],
  }),
}))

const app: SoftwareRepository = {
  softwareRepositoryId: 'app-1',
  projectId: 'project-1',
  name: '订单服务',
  description: '',
  basePath: '/api/orders',
  repository: {
    projectId: '41',
    path: 'commerce/order-service',
    name: 'order-service',
    instanceUrl: 'https://gitlab.example.com',
  },
  interfaceGroups: [],
  interfaceCount: 1,
  version: 1,
}

const apiInterface: ApiInterface = {
  interfaceId: 'api-1',
  softwareRepositoryId: 'app-1',
  softwareRepositoryName: '订单服务',
  name: '查询订单',
  method: 'GET',
  path: '/orders/{orderId}',
  description: '按订单号查询',
  tags: ['订单'],
  headers: [
    { enabled: true, name: 'Authorization', type: 'string', required: true, example: 'Bearer token', description: '令牌' },
  ],
  pathParams: [
    { enabled: true, name: 'orderId', type: 'string', required: true, example: 'A001', description: '订单号' },
  ],
  queryParams: [
    { enabled: true, name: 'withItems', type: 'boolean', required: false, example: 'true', description: '是否带明细' },
  ],
  bodyType: 'none',
  bodySchema: null,
  bodyExample: null,
  bodyText: '',
  responseStatus: 200,
  responseDescription: '查询成功',
  responseSchema: { type: 'object' },
  responseExample: { orderId: 'A001' },
  security: null,
  securitySchemes: null,
  version: 2,
  sourceType: 'manual',
  requirements: [{ requirementId: 'req-1', name: '下单流程', sprintId: 'sprint-1', sprintName: 'V1.0.0' }],
  source: { type: 'manual', name: '', url: '', version: '', importedAt: null },
  updatedAt: '2026-11-12T10:00:00',
}

const list = Object.assign([apiInterface as ApiInterfaceListItem], {
  items: [apiInterface as ApiInterfaceListItem],
  total: 1,
})

function dialogOf(element: Element | null): HTMLElement {
  const dialog = element?.closest('[role="dialog"]')
  if (!dialog) throw new Error('dialog not found')
  return dialog as HTMLElement
}

async function expandRepository(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: '展开订单服务' }))
}

function renderPage(path: string, role: 'owner' | 'viewer' = 'owner') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  if (role === 'owner') {
    seedOwnerProject(client)
  } else {
    useWorkbenchStore.getState().setActiveProjectId('project-1')
    client.setQueryData(['projectAccess', 'project-1'], {
      projectId: 'project-1',
      name: '测试项目',
      role: 'viewer',
      permissions: ['read'],
    })
  }
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/asset-library/interfaces/new" element={<InterfaceDetailPage />} />
          <Route path="/asset-library/interfaces/:interfaceId" element={<InterfaceDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('InterfaceDetailPage', () => {
  beforeEach(() => {
    vi.mocked(interfaceLibraryApi.getSoftwareRepositories).mockResolvedValue(Object.assign([app], { items: [app], total: 1 }))
    vi.mocked(interfaceLibraryApi.getApiInterface).mockResolvedValue(apiInterface)
    vi.mocked(interfaceLibraryApi.getSoftwareRepositoryApiInterfaces).mockResolvedValue(list)
    vi.mocked(interfaceLibraryApi.updateApiInterface).mockResolvedValue(apiInterface)
    vi.mocked(interfaceLibraryApi.createApiInterfaceGroup).mockResolvedValue({
      groupName: '新分组',
      newGroupName: '新分组',
      updatedCount: 0,
    })
    vi.mocked(interfaceLibraryApi.renameApiInterfaceGroup).mockResolvedValue({
      groupName: '订单',
      newGroupName: '订单管理',
      updatedCount: 1,
    })
    vi.mocked(interfaceLibraryApi.deleteApiInterfaceGroup).mockResolvedValue({
      groupName: '订单',
      newGroupName: '',
      updatedCount: 1,
    })
    vi.mocked(interfaceLibraryApi.moveApiInterfaceToGroup).mockResolvedValue({
      ...apiInterface,
      tags: ['订单管理'],
      version: 3,
    })
    vi.mocked(interfaceLibraryApi.createApiInterface).mockResolvedValue({
      ...apiInterface,
      interfaceId: 'api-created',
      name: '创建订单',
      path: '/orders',
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('loads an interface definition and saves edited library fields', async () => {
    const user = userEvent.setup()
    renderPage('/asset-library/interfaces/api-1')
    await expandRepository(user)

    const nameInput = await screen.findByLabelText('接口名称')
    expect(nameInput).toHaveValue('查询订单')
    expect(screen.getByLabelText('接口路径')).toHaveValue('/orders/{orderId}')
    expect(screen.getByText('/api/orders')).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '接口库' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '软件仓库' })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /参数/ })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByRole('button', { name: /^订单服务/ })).toBeInTheDocument()
    expect(
      await screen.findByRole('button', { name: /GET.*查询订单/ }),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /请求头/ }))
    expect(screen.getByDisplayValue('Authorization')).toBeInTheDocument()

    await user.clear(nameInput)
    await user.type(nameInput, '订单详情')
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() => expect(interfaceLibraryApi.updateApiInterface).toHaveBeenCalled())
    expect(interfaceLibraryApi.updateApiInterface).toHaveBeenCalledWith(
      'api-1',
      expect.objectContaining({
        name: '订单详情',
        method: 'GET',
        path: '/orders/{orderId}',
        headers: [expect.objectContaining({ name: 'Authorization' })],
        pathParams: [expect.objectContaining({ name: 'orderId', required: true })],
        queryParams: [expect.objectContaining({ name: 'withItems' })],
        responseStatus: 200,
        responseSchema: { type: 'object' },
        responseExample: { orderId: 'A001' },
        requirementIds: ['req-1'],
        tags: ['订单'],
      }),
    )
  })

  it('loads all software repository interfaces and groups untagged interfaces inside the tree', async () => {
    const user = userEvent.setup()
    const treeItems = Array.from({ length: 11 }, (_, index) => ({
      interfaceId: `api-${index + 1}`,
      softwareRepositoryId: 'app-1',
      softwareRepositoryName: '订单服务',
      name: `接口 ${index + 1}`,
      method: 'GET',
      path: `/orders/${index + 1}`,
      description: '',
      tags: [],
      requirements: [],
      sourceType: 'manual',
      updatedAt: '2026-11-12T10:00:00',
    })) as ApiInterfaceListItem[]
    vi.mocked(interfaceLibraryApi.getSoftwareRepositories).mockResolvedValue(
      Object.assign([{ ...app, interfaceCount: 11 }], {
        items: [{ ...app, interfaceCount: 11 }],
        total: 1,
      }),
    )
    vi.mocked(interfaceLibraryApi.getSoftwareRepositoryApiInterfaces).mockImplementation(
      async (_softwareRepositoryId, options) => {
        const limit = (options?.pageSize ?? 100) > 100 ? treeItems.length : 10
        const items = treeItems.slice(0, limit)
        return Object.assign([...items], { items, total: treeItems.length })
      },
    )
    renderPage('/asset-library/interfaces/api-1')
    await expandRepository(user)

    expect(await screen.findByText('未分类')).toBeInTheDocument()
    expect(
      await screen.findByRole('button', { name: /GET.*接口 11/ }),
    ).toBeInTheDocument()
    expect(interfaceLibraryApi.getSoftwareRepositoryApiInterfaces).toHaveBeenCalledWith(
      'app-1',
      expect.objectContaining({ page: 1, pageSize: 200 }),
    )
  })

  it('shows the OpenAPI import entry when the library has no interfaces', async () => {
    const user = userEvent.setup()
    renderPage('/asset-library/interfaces/new?softwareRepositoryId=app-1')

    const importButton = await screen.findByRole('button', { name: /OpenAPI/ })
    expect(importButton).toBeEnabled()
    await user.click(importButton)

    expect(await screen.findByRole('dialog')).toHaveTextContent('导入 OpenAPI / Swagger')
  })

  it('creates an interface and derives path parameter rows from the path', async () => {
    const user = userEvent.setup()
    renderPage('/asset-library/interfaces/new?softwareRepositoryId=app-1')

    const nameInput = await screen.findByLabelText('接口名称')
    await user.type(nameInput, '创建订单')
    await user.type(screen.getByLabelText('接口路径'), '/orders/{{orderId}')
    await user.click(screen.getByRole('button', { name: '创建接口' }))

    await waitFor(() => expect(interfaceLibraryApi.createApiInterface).toHaveBeenCalled())
    expect(interfaceLibraryApi.createApiInterface).toHaveBeenCalledWith(
      'app-1',
      expect.objectContaining({
        name: '创建订单',
        path: '/orders/{orderId}',
        pathParams: [expect.objectContaining({ name: 'orderId', required: true })],
        bodyType: 'none',
      }),
    )
  })

  it('creates a persisted group from the tree entry', async () => {
    const user = userEvent.setup()
    renderPage('/asset-library/interfaces/api-1')
    await expandRepository(user)

    await screen.findByRole('button', { name: /GET.*查询订单/ })
    await user.click(screen.getByRole('button', { name: /新建分组/ }))
    const dialog = dialogOf(
      await screen.findByText(/分组会保存在软件仓库中，即使暂时没有接口也会保留/),
    )
    await user.type(within(dialog).getByLabelText('分组名称'), '新分组')
    await user.click(within(dialog).getByRole('button', { name: /^创\s*建$/ }))

    await waitFor(() =>
      expect(interfaceLibraryApi.createApiInterfaceGroup).toHaveBeenCalledWith('app-1', {
        groupName: '新分组',
      }),
    )
  })

  it('renames a group from the tree and syncs the open interface draft', async () => {
    const user = userEvent.setup()
    renderPage('/asset-library/interfaces/api-1')
    await expandRepository(user)

    await screen.findByRole('button', { name: /GET.*查询订单/ })
    await user.click(screen.getByRole('button', { name: '分组「订单」更多操作' }))
    await user.click(await screen.findByText('重命名分组'))
    const dialog = dialogOf(await screen.findByText(/将修改该分组下接口的首个标签/))
    const input = within(dialog).getByLabelText('新分组名称')
    expect(input).toHaveValue('订单')
    await user.clear(input)
    await user.type(input, '订单管理')
    await user.click(within(dialog).getByRole('button', { name: /^保\s*存$/ }))

    await waitFor(() =>
      expect(interfaceLibraryApi.renameApiInterfaceGroup).toHaveBeenCalledWith('app-1', {
        currentGroupName: '订单',
        newGroupName: '订单管理',
      }),
    )
    await user.click(screen.getByRole('tab', { name: '设置' }))
    expect(screen.getByLabelText('接口标签')).toHaveValue('订单管理')
  })

  it('keeps the rename dialog open and reports an existing target group', async () => {
    const user = userEvent.setup()
    vi.mocked(interfaceLibraryApi.renameApiInterfaceGroup).mockRejectedValue(
      new ApiError('目标接口分组已存在', 3819, 409),
    )
    renderPage('/asset-library/interfaces/api-1')
    await expandRepository(user)

    await screen.findByRole('button', { name: /GET.*查询订单/ })
    await user.click(screen.getByRole('button', { name: '分组「订单」更多操作' }))
    await user.click(await screen.findByText('重命名分组'))
    const dialog = dialogOf(await screen.findByText(/将修改该分组下接口的首个标签/))
    const input = within(dialog).getByLabelText('新分组名称')
    await user.clear(input)
    await user.type(input, '账户')
    await user.click(within(dialog).getByRole('button', { name: /^保\s*存$/ }))

    await waitFor(() =>
      expect(message.error).toHaveBeenCalledWith('目标接口分组已存在'),
    )
    expect(within(dialog).getByLabelText('新分组名称')).toHaveValue('账户')
  })

  it('removes a group into unclassified and clears the open interface tags', async () => {
    const user = userEvent.setup()
    renderPage('/asset-library/interfaces/api-1')
    await expandRepository(user)

    await screen.findByRole('button', { name: /GET.*查询订单/ })
    await user.click(screen.getByRole('button', { name: '分组「订单」更多操作' }))
    await user.click(await screen.findByText('移除分组'))
    const content = await screen.findByText(
      /该组 1 个接口将清除全部标签并归入「未分类」，接口不会被删除，次要标签也会被清除。/,
    )
    expect(content).toBeInTheDocument()
    const dialog = dialogOf(content)
    await user.click(within(dialog).getByRole('button', { name: /^移\s*除\s*分\s*组$/ }))

    await waitFor(() =>
      expect(interfaceLibraryApi.deleteApiInterfaceGroup).toHaveBeenCalledWith('app-1', {
        groupName: '订单',
      }),
    )
    await user.click(screen.getByRole('tab', { name: '设置' }))
    expect(screen.getByLabelText('接口标签')).toHaveValue('')
  })

  it('moves an interface to a new group and applies the returned tags', async () => {
    const user = userEvent.setup()
    renderPage('/asset-library/interfaces/api-1')
    await expandRepository(user)

    await screen.findByRole('button', { name: /GET.*查询订单/ })
    await user.click(screen.getByRole('button', { name: '查询订单 更多操作' }))
    await user.click(await screen.findByText('移动到分组…'))
    const dialog = dialogOf(await screen.findByText(/移动到已有或新分组会将该标签置顶/))
    await user.type(within(dialog).getByLabelText('目标分组'), '订单管理')
    await user.click(within(dialog).getByRole('button', { name: /^移\s*动$/ }))

    await waitFor(() =>
      expect(interfaceLibraryApi.moveApiInterfaceToGroup).toHaveBeenCalledWith('api-1', {
        groupName: '订单管理',
      }),
    )
    await user.click(screen.getByRole('tab', { name: '设置' }))
    expect(screen.getByLabelText('接口标签')).toHaveValue('订单管理')
  })

  it('does not expose software repository maintenance in the interface library', async () => {
    const user = userEvent.setup()
    renderPage('/asset-library/interfaces/api-1')
    await expandRepository(user)

    await screen.findByRole('button', { name: /GET.*查询订单/ })
    expect(screen.queryByRole('button', { name: '新建软件仓库' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑订单服务' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除订单服务' })).not.toBeInTheDocument()
  })

  it('points to the software repositories page when the project has none', async () => {
    vi.mocked(interfaceLibraryApi.getSoftwareRepositories).mockResolvedValue(
      Object.assign([], { items: [], total: 0 }),
    )
    renderPage('/asset-library/interfaces/new')

    expect(
      await screen.findByText('当前项目还没有软件仓库，请先在「软件仓库」页创建。'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建软件仓库' })).not.toBeInTheDocument()
  })

  it('renders viewer access as read-only without save or delete actions', async () => {
    const user = userEvent.setup()
    renderPage('/asset-library/interfaces/api-1', 'viewer')

    expect(await screen.findByLabelText('接口名称')).toBeDisabled()
    expect(screen.queryByRole('button', { name: /保\s*存/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /删\s*除/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建软件仓库' })).not.toBeInTheDocument()
    await expandRepository(user)
    await screen.findByRole('button', { name: /GET.*查询订单/ })
    expect(
      screen.queryByRole('button', { name: '分组「订单」更多操作' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '查询订单 更多操作' }),
    ).not.toBeInTheDocument()
  })
})
