import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { SoftwareRepository, ApiInterfaceListItem } from '../types'
import { InterfaceLibraryPage } from './InterfaceLibraryPage'

vi.mock('../api/interfaceLibrary.api', () => ({
  interfaceLibraryApi: {
    getSoftwareRepositories: vi.fn(),
    getProjectApiInterfaces: vi.fn(),
  },
}))

const orderApp: SoftwareRepository = {
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
  interfaceCount: 2,
  version: 1,
}

const userApp: SoftwareRepository = {
  ...orderApp,
  softwareRepositoryId: 'app-2',
  name: '用户服务',
  basePath: '/api/users',
  repository: {
    projectId: '42',
    path: 'commerce/user-service',
    name: 'user-service',
    instanceUrl: 'https://gitlab.example.com',
  },
  interfaceGroups: [],
  interfaceCount: 1,
}

const interfaceItem: ApiInterfaceListItem = {
  interfaceId: 'api-9',
  softwareRepositoryId: 'app-2',
  softwareRepositoryName: '用户服务',
  name: '查询用户',
  method: 'GET',
  path: '/users/{userId}',
  description: '',
  tags: [],
  requirements: [],
  sourceType: 'manual',
  updatedAt: '2026-11-12T10:00:00',
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function LocationOutput() {
  const location = useLocation()
  return <output>{`${location.pathname}${location.search}`}</output>
}

function InterfaceDetailProbe() {
  const { interfaceId } = useParams<{ interfaceId: string }>()
  return <p>接口详情 {interfaceId}</p>
}

function renderPage(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useWorkbenchStore.getState().setActiveProjectId('project-1')
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/asset-library" element={<InterfaceLibraryPage />} />
          <Route path="/asset-library/interfaces/new" element={<p>新建接口页</p>} />
          <Route path="/asset-library/interfaces/:interfaceId" element={<InterfaceDetailProbe />} />
        </Routes>
        <LocationOutput />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('InterfaceLibraryPage', () => {
  beforeEach(() => {
    vi.mocked(interfaceLibraryApi.getSoftwareRepositories).mockResolvedValue(
      listResponse([orderApp, userApp]),
    )
    vi.mocked(interfaceLibraryApi.getProjectApiInterfaces).mockResolvedValue(
      listResponse([interfaceItem]),
    )
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('opens the most recently updated interface directly', async () => {
    renderPage('/asset-library?tab=interfaces')

    expect(await screen.findByText('接口详情 api-9')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('/asset-library/interfaces/api-9')
    expect(interfaceLibraryApi.getProjectApiInterfaces).toHaveBeenCalledWith(
      'project-1',
      { softwareRepositoryId: '', page: 1, pageSize: 1 },
    )
  })

  it('opens the requested software repository interface when softwareRepositoryId is present', async () => {
    renderPage('/asset-library?tab=interfaces&softwareRepositoryId=app-2')

    expect(await screen.findByText('接口详情 api-9')).toBeInTheDocument()
    expect(interfaceLibraryApi.getProjectApiInterfaces).toHaveBeenCalledWith(
      'project-1',
      { softwareRepositoryId: 'app-2', page: 1, pageSize: 1 },
    )
  })

  it('falls back to creating an interface in the first software repository', async () => {
    vi.mocked(interfaceLibraryApi.getProjectApiInterfaces).mockResolvedValue(listResponse([]))
    renderPage('/asset-library?tab=interfaces')

    expect(await screen.findByText('新建接口页')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      '/asset-library/interfaces/new?softwareRepositoryId=app-1',
    )
  })

  it('keeps the requested repository when creating the first interface', async () => {
    vi.mocked(interfaceLibraryApi.getProjectApiInterfaces).mockResolvedValue(listResponse([]))
    renderPage('/asset-library?tab=interfaces&softwareRepositoryId=app-1')

    expect(await screen.findByText('新建接口页')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      '/asset-library/interfaces/new?softwareRepositoryId=app-1',
    )
  })
})
