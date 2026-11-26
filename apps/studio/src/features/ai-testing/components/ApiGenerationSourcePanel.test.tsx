import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { requirementDesignApi } from '../api/requirementDesign.api'
import type { RepositoryProfileCandidateView } from '../types'
import { ApiGenerationSourcePanel } from './ApiGenerationSourcePanel'

vi.mock('../api/requirementDesign.api', async importOriginal => {
  const actual = await importOriginal<typeof import('../api/requirementDesign.api')>()
  return { ...actual, requirementDesignApi: { ...actual.requirementDesignApi, overview: vi.fn() } }
})

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

function profileCandidate(): RepositoryProfileCandidateView {
  return {
    candidateId: 'profile-v1',
    label: 'v1',
    resultYaml: '',
    createdAt: '2026-11-15T10:00:00Z',
    profile: {
      overallSummary: '',
      repositories: [
        {
          repositoryId: 'repo-api',
          pathWithNamespace: 'team/order-service',
          role: 'backend',
          responsibilitySummary: '订单接口服务',
          techStack: ['Java'],
          keyPaths: ['src/main'],
          confidence: 0.91,
          evidence: [],
        },
        {
          repositoryId: 'repo-web',
          pathWithNamespace: 'team/web',
          role: 'frontend',
          responsibilitySummary: '管理端页面',
          techStack: ['React'],
          keyPaths: ['src'],
          confidence: 0.8,
          evidence: [],
        },
      ],
    },
  }
}

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  clients.push(client)
  render(
    <TestThemeProvider>
      <QueryClientProvider client={client}>
        <ApiGenerationSourcePanel
          requirementId="req"
          projectId="project-1"
          canWrite
          busy={false}
          profileCandidate={profileCandidate()}
          onSaved={vi.fn()}
        />
      </QueryClientProvider>
    </TestThemeProvider>,
  )
}

beforeEach(() => {
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({
    tasks: [],
    runCounts: { requirement_analysis: 0, function: 0, api: 0, ui: 0 },
  })
  vi.mocked(
    interfaceLibraryApi.getRequirementSoftwareRepositories,
  ).mockResolvedValue(
    listResponse([
      {
        requirementId: 'req',
        softwareRepositoryId: 'software-repo-api',
        softwareRepositoryName: '订单服务',
        basePath: '/api',
        repository: {
          projectId: 'repo-api',
          path: 'team/order-service',
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
      {
        interfaceId: 'interface-1',
        softwareRepositoryId: 'software-repo-api',
        softwareRepositoryName: '订单服务',
        name: '创建订单',
        method: 'POST',
        path: '/orders',
        description: '',
        tags: [],
        requirements: [],
        sourceType: 'manual',
      },
    ]),
  )
})

it('展示仓库画像建议的后端仓库，并在接口选择器中作为默认范围', async () => {
  mount()
  const user = userEvent.setup()

  const suggestions = await screen.findByRole('region', {
    name: 'API 测试建议后端仓库',
  })
  expect(within(suggestions).getByText('team/order-service')).toBeInTheDocument()
  expect(within(suggestions).getByText('后端')).toBeInTheDocument()
  expect(within(suggestions).getByText('推荐')).toBeInTheDocument()
  expect(within(suggestions).getByText(/来自仓库画像 v1/)).toBeInTheDocument()
  expect(within(suggestions).queryByText('team/web')).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '选择接口' }))
  expect(
    await screen.findByText(/默认展示仓库画像建议的后端仓库/),
  ).toBeInTheDocument()
  expect(await screen.findByText('画像建议仓库（1）')).toBeInTheDocument()
  await waitFor(() =>
    expect(
      interfaceLibraryApi.getSoftwareRepositoryApiInterfaces,
    ).toHaveBeenCalledWith('software-repo-api', {
      keyword: '',
      page: 1,
      pageSize: 100,
    }),
  )
})
