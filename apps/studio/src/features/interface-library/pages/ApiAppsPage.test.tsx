import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { seedOwnerProject } from '@/test/projectAccess'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ApiApp } from '../types'
import { ApiAppsPage } from './ApiAppsPage'

const feedback = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}))

vi.mock('@/shared/utils/feedback', () => ({ message: feedback }))
vi.mock('../api/interfaceLibrary.api', () => ({
  interfaceLibraryApi: {
    getApiApps: vi.fn(),
    createApiApp: vi.fn(),
    updateApiApp: vi.fn(),
    deleteApiApp: vi.fn(),
  },
}))
vi.mock('@/features/base-services/api/baseServices.api', () => ({
  baseServicesApi: {
    getGitlabConnections: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    getGitlabProjectBindings: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    getGitlabGroupRepositories: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  },
}))

const orderApp: ApiApp = {
  appId: 'app-1',
  projectId: 'project-1',
  name: '订单服务',
  description: '订单域接口',
  basePath: '/api/orders',
  repository: { projectId: '42', path: 'commerce/order-service', name: 'order-service', instanceUrl: 'https://gitlab.example.com' },
  enabled: true,
  interfaceCount: 2,
  enabledInterfaceCount: 1,
  version: 1,
  updatedAt: '2026-11-12T10:00:00',
}

const userApp: ApiApp = {
  ...orderApp,
  appId: 'app-2',
  name: '用户服务',
  description: '',
  basePath: '',
  repository: null,
  enabled: false,
  interfaceCount: 0,
  enabledInterfaceCount: 0,
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
      <MemoryRouter initialEntries={['/asset-library?tab=apps']}>
        <ApiAppsPage />
        <LocationOutput />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ApiAppsPage', () => {
  beforeEach(() => {
    vi.mocked(interfaceLibraryApi.getApiApps).mockResolvedValue(listResponse([orderApp, userApp]))
    vi.mocked(interfaceLibraryApi.createApiApp).mockResolvedValue({
      ...orderApp,
      appId: 'app-3',
      name: '库存服务',
      interfaceCount: 0,
      enabledInterfaceCount: 0,
    })
    vi.mocked(interfaceLibraryApi.updateApiApp).mockResolvedValue({} as never)
    vi.mocked(interfaceLibraryApi.deleteApiApp).mockResolvedValue({})
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('lists apps and opens the selected app interface library', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('commerce/order-service')).toBeInTheDocument()
    expect(screen.getByText('/api/orders')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '订单服务' }))

    expect(screen.getByRole('status')).toHaveTextContent(
      '/asset-library?tab=interfaces&appId=app-1',
    )
  })

  it('creates an app from the page drawer', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('订单服务')

    await user.click(screen.getByRole('button', { name: /新建应用/ }))
    await user.type(await screen.findByPlaceholderText('例如：订单服务'), '库存服务')
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() =>
      expect(interfaceLibraryApi.createApiApp).toHaveBeenCalledWith(
        'project-1',
        expect.objectContaining({ name: '库存服务' }),
      ),
    )
  })

  it('blocks deleting apps that still contain interfaces', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('订单服务')

    const deleteButton = screen.getByRole('button', { name: '删除订单服务' })
    expect(deleteButton).toBeDisabled()
    await user.click(deleteButton)

    expect(interfaceLibraryApi.deleteApiApp).not.toHaveBeenCalled()
  })

  it('hides app management actions from viewers', async () => {
    renderPage('viewer')

    await screen.findByText('订单服务')
    expect(screen.getByRole('button', { name: /新建应用/ })).toBeDisabled()
    expect(screen.queryByRole('button', { name: '编辑订单服务' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除订单服务' })).not.toBeInTheDocument()
  })
})
