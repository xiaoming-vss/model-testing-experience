import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { seedOwnerProject } from '@/test/projectAccess'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { SoftwareRepository } from '../types'
import { SoftwareRepositoriesPage } from './SoftwareRepositoriesPage'

const feedback = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}))

const baseServicesMocks = vi.hoisted(() => ({
  getGitlabConnections: vi.fn(),
  getGitlabGroups: vi.fn(),
  getGitlabGroupRepositories: vi.fn(),
}))

vi.mock('@/shared/utils/feedback', () => ({ message: feedback }))
vi.mock('../api/interfaceLibrary.api', () => ({
  interfaceLibraryApi: {
    getSoftwareRepositories: vi.fn(),
    createSoftwareRepository: vi.fn(),
    deleteSoftwareRepository: vi.fn(),
  },
}))
vi.mock('@/features/base-services/api/baseServices.api', () => ({
  baseServicesApi: baseServicesMocks,
}))

const orderRepository: SoftwareRepository = {
  softwareRepositoryId: 'repository-1',
  projectId: 'project-1',
  name: '订单服务',
  description: '订单域接口',
  basePath: '/api/orders',
  repository: {
    projectId: '42',
    path: 'commerce/order-service',
    name: 'order-service',
    instanceUrl: 'https://gitlab.example.com',
  },
  interfaceGroups: [],
  interfaceCount: 2,
  version: 1,
  updatedAt: '2026-11-12T10:00:00',
}

const userRepository: SoftwareRepository = {
  ...orderRepository,
  softwareRepositoryId: 'repository-2',
  name: '用户服务',
  description: '',
  basePath: '',
  repository: {
    projectId: '43',
    path: 'commerce/user-service',
    name: 'user-service',
    instanceUrl: 'https://gitlab.example.com',
  },
  interfaceGroups: [],
  interfaceCount: 0,
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function LocationOutput() {
  const location = useLocation()
  return <output>{`${location.pathname}${location.search}`}</output>
}

function renderPage(role: 'owner' | 'viewer' = 'owner') {
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
      <MemoryRouter initialEntries={['/asset-library?tab=repositories']}>
        <SoftwareRepositoriesPage />
        <LocationOutput />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SoftwareRepositoriesPage', () => {
  beforeEach(() => {
    vi.mocked(interfaceLibraryApi.getSoftwareRepositories).mockResolvedValue(
      listResponse([orderRepository, userRepository]),
    )
    vi.mocked(interfaceLibraryApi.createSoftwareRepository).mockResolvedValue({
      ...orderRepository,
      softwareRepositoryId: 'repository-3',
      name: '库存服务',
      interfaceGroups: [],
  interfaceCount: 0,
    })
    vi.mocked(interfaceLibraryApi.deleteSoftwareRepository).mockResolvedValue({})
    baseServicesMocks.getGitlabConnections.mockResolvedValue(
      listResponse([
        {
          connectionId: 'connection-1',
          provider: 'gitlab',
          name: 'GitLab',
          baseUrl: 'https://gitlab.example.com',
          status: 'active',
          authType: 'personal_access_token',
          account: 'tester',
          hasAccessToken: true,
        },
      ]),
    )
    baseServicesMocks.getGitlabGroups.mockResolvedValue({
      items: [{ id: 'team', name: 'commerce', fullPath: 'commerce' }],
      total: 1,
    })
    baseServicesMocks.getGitlabGroupRepositories.mockResolvedValue(
      listResponse([
        {
          id: 44,
          name: 'stock-service',
          path: 'commerce/stock-service',
          pathWithNamespace: 'commerce/stock-service',
        },
      ]),
    )
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('lists software repositories and opens the selected repository interfaces', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('commerce/order-service')).toBeInTheDocument()
    expect(screen.getByText('/api/orders')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '订单服务' }))

    expect(screen.getByRole('status')).toHaveTextContent(
      '/asset-library?tab=interfaces&softwareRepositoryId=repository-1',
    )
  })

  it('creates a software repository from the page drawer', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('订单服务')

    await user.click(screen.getByRole('button', { name: /新建软件仓库/ }))
    await user.type(await screen.findByPlaceholderText('例如：订单服务'), '库存服务')
    await user.click(screen.getByLabelText('选择 GitLab 连接'))
    await user.click(await screen.findByText('GitLab'))
    await user.click(screen.getByLabelText('选择 GitLab 群组'))
    await user.click(await screen.findByText('commerce'))
    await user.click(screen.getByLabelText('选择代码仓库'))
    await user.click(await screen.findByText('commerce/stock-service'))
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() =>
      expect(interfaceLibraryApi.createSoftwareRepository).toHaveBeenCalledWith(
        'project-1',
        expect.objectContaining({
          name: '库存服务',
          repository: {
            connectionId: 'connection-1',
            groupId: 'team',
            repositoryId: '44',
          },
        }),
      ),
    )
  })

  it('blocks deleting repositories that still contain interfaces', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('订单服务')

    const deleteButton = screen.getByRole('button', { name: '删除订单服务' })
    expect(deleteButton).toBeDisabled()
    await user.click(deleteButton)

    expect(interfaceLibraryApi.deleteSoftwareRepository).not.toHaveBeenCalled()
  })

  it('hides repository management actions from viewers', async () => {
    renderPage('viewer')

    await screen.findByText('订单服务')
    expect(screen.getByRole('button', { name: /新建软件仓库/ })).toBeDisabled()
    expect(screen.queryByRole('button', { name: '编辑订单服务' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除订单服务' })).not.toBeInTheDocument()
  })
})
