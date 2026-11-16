import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { RequirementCodeBindingModal } from './RequirementCodeBindingModal'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function renderModal(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  seedOwnerProject(client)
  return { ...render(<QueryClientProvider client={client}>{children}</QueryClientProvider>), client }
}

it('只读权限下禁用已关联软件仓库的分支与基线修改', async () => {
  vi.spyOn(api, 'getGitlabConnections').mockResolvedValue(
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
  vi.spyOn(api, 'getGitlabRepositoryBranches').mockResolvedValue(
    listResponse([
      { name: 'dev', isDefault: false },
      { name: 'main', isDefault: true },
    ]),
  )
  vi.spyOn(interfaceLibraryApi, 'getRequirementSoftwareRepositories').mockResolvedValue(
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
  const update = vi.spyOn(
    interfaceLibraryApi,
    'updateRequirementSoftwareRepository',
  )
  const { client } = renderModal(
    <RequirementCodeBindingModal
      open
      projectId="project-1"
      requirementId="requirement-1"
      onClose={() => {}}
    />,
  )
  await screen.findByText('订单服务')
  const row = screen.getByText('订单服务').closest('.requirement-code-binding-row')!
  const selectors = row.querySelectorAll('input[role="combobox"]')
  expect(selectors).toHaveLength(2)
  expect(selectors[0]).toBeEnabled()
  await act(async () => {
    client.setQueryData(['projectAccess', 'project-1'], {
      projectId: 'project-1',
      permissions: ['read'],
    })
  })
  // Query cache notifications reach the component asynchronously.
  await waitFor(() => {
    expect(selectors[0]).toBeDisabled()
    expect(selectors[1]).toBeDisabled()
  })
  expect(update).not.toHaveBeenCalled()
})

it('显示已关联软件仓库的工作分支和基线分支', async () => {
  vi.spyOn(api, 'getGitlabConnections').mockResolvedValue(listResponse([]))
  vi.spyOn(interfaceLibraryApi, 'getRequirementSoftwareRepositories').mockResolvedValue(
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
  renderModal(
    <RequirementCodeBindingModal
      open
      projectId="project-1"
      requirementId="requirement-1"
      onClose={() => {}}
    />,
  )

  await screen.findByText('订单服务')
  expect(screen.getAllByText('dev').length).toBeGreaterThan(0)
  expect(screen.getByText('基线：main')).toBeInTheDocument()
})
