import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { seedOwnerProject } from '@/test/projectAccess'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ApiApp, ApiInterface, ApiInterfaceListItem } from '../types'
import { InterfaceDetailPage } from './InterfaceDetailPage'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))
vi.mock('../api/interfaceLibrary.api', () => ({
  interfaceLibraryApi: {
    getApiInterface: vi.fn(),
    getApiApps: vi.fn(),
    getAppApiInterfaces: vi.fn(),
    createApiInterface: vi.fn(),
    updateApiInterface: vi.fn(),
    deleteApiInterface: vi.fn(),
  },
}))
vi.mock('@/features/projects/hooks/useProjectRequirementOptions', () => ({
  useProjectRequirementOptions: () => ({
    allRequirements: [
      { requirementId: 'req-1', name: '下单流程', sprintId: 'sprint-1', sprintName: 'V1.0.0' },
    ],
  }),
}))

const app: ApiApp = {
  appId: 'app-1',
  projectId: 'project-1',
  name: '订单服务',
  description: '',
  basePath: '/api/orders',
  repository: null,
  enabled: true,
  interfaceCount: 1,
  enabledInterfaceCount: 1,
  version: 1,
}

const apiInterface: ApiInterface = {
  interfaceId: 'api-1',
  appId: 'app-1',
  appName: '订单服务',
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
  enabled: true,
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
    vi.mocked(interfaceLibraryApi.getApiApps).mockResolvedValue(Object.assign([app], { items: [app], total: 1 }))
    vi.mocked(interfaceLibraryApi.getApiInterface).mockResolvedValue(apiInterface)
    vi.mocked(interfaceLibraryApi.getAppApiInterfaces).mockResolvedValue(list)
    vi.mocked(interfaceLibraryApi.updateApiInterface).mockResolvedValue(apiInterface)
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

    const nameInput = await screen.findByLabelText('接口名称')
    expect(nameInput).toHaveValue('查询订单')
    expect(screen.getByLabelText('接口路径')).toHaveValue('/orders/{orderId}')
    expect(screen.getByText('/api/orders')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '接口库' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: '应用' })).toBeInTheDocument()
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

  it('loads the rest of an app interfaces inside the tree instead of leaving the workspace', async () => {
    const user = userEvent.setup()
    const treeItems = Array.from({ length: 11 }, (_, index) => ({
      interfaceId: `api-${index + 1}`,
      appId: 'app-1',
      appName: '订单服务',
      name: `接口 ${index + 1}`,
      method: 'GET',
      path: `/orders/${index + 1}`,
      description: '',
      tags: [],
      requirements: [],
      enabled: true,
      sourceType: 'manual',
      updatedAt: '2026-11-12T10:00:00',
    })) as ApiInterfaceListItem[]
    vi.mocked(interfaceLibraryApi.getApiApps).mockResolvedValue(
      Object.assign([{ ...app, interfaceCount: 11 }], {
        items: [{ ...app, interfaceCount: 11 }],
        total: 1,
      }),
    )
    vi.mocked(interfaceLibraryApi.getAppApiInterfaces).mockImplementation(
      async (_appId, options) => {
        const limit = (options?.pageSize ?? 100) > 100 ? treeItems.length : 10
        const items = treeItems.slice(0, limit)
        return Object.assign([...items], { items, total: treeItems.length })
      },
    )
    renderPage('/asset-library/interfaces/api-1')

    await user.click(await screen.findByRole('button', { name: '查看其余 1 个接口' }))

    expect(
      await screen.findByRole('button', { name: /GET.*接口 11/ }),
    ).toBeInTheDocument()
    expect(interfaceLibraryApi.getAppApiInterfaces).toHaveBeenCalledWith(
      'app-1',
      expect.objectContaining({ page: 1, pageSize: 200 }),
    )
  })

  it('creates an interface and derives path parameter rows from the path', async () => {
    const user = userEvent.setup()
    renderPage('/asset-library/interfaces/new?appId=app-1')

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
        enabled: true,
      }),
    )
  })

  it('renders viewer access as read-only without save or delete actions', async () => {
    renderPage('/asset-library/interfaces/api-1', 'viewer')

    expect(await screen.findByLabelText('接口名称')).toBeDisabled()
    expect(screen.queryByRole('button', { name: /保\s*存/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /删\s*除/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '新建应用' })).not.toBeInTheDocument()
  })
})
