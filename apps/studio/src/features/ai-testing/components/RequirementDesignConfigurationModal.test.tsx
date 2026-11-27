import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { RequirementDesignConfigurationModal } from './RequirementDesignConfigurationModal'
import { requirementDesignApi } from '../api/requirementDesign.api'

vi.mock('../api/requirementDesign.api', async importOriginal => {
  const actual = await importOriginal<typeof import('../api/requirementDesign.api')>()
  return { ...actual, requirementDesignApi: { ...actual.requirementDesignApi, overview: vi.fn() } }
})

vi.mock('@/features/interface-library/api/interfaceLibrary.api', () => ({
  interfaceLibraryApi: {
    getRequirementSoftwareRepositories: vi.fn(),
    getProjectApiInterfaces: vi.fn(),
  },
}))

const clients: QueryClient[] = []
afterEach(() => {
  cleanup()
  clients.forEach(client => client.clear())
  clients.length = 0
  vi.restoreAllMocks()
})

function response(data: unknown, status = 200) {
  return new Response(
    JSON.stringify({
      code: status === 200 ? 0 : status,
      message: status === 200 ? 'ok' : '上传失败',
      data,
    }),
    { status, headers: { 'Content-Type': 'application/json' } },
  )
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function mount(kind: 'ui' | 'api', onSaved = vi.fn(), initialTaskId?: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  clients.push(client)
  const rendered = render(
    <TestThemeProvider>
      <QueryClientProvider client={client}>
        <RequirementDesignConfigurationModal
          requirementId="req"
          projectId="project-1"
          kind={kind}
          initialTaskId={initialTaskId}
          onClose={vi.fn()}
          onSaved={onSaved}
        />
      </QueryClientProvider>
    </TestThemeProvider>,
  )
  return { ...rendered, onSaved }
}

beforeEach(() => {
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({
    tasks: [],
    runCounts: { requirement_analysis: 0, function: 0, api: 0, ui: 0 },
  })
  vi.mocked(
    interfaceLibraryApi.getRequirementSoftwareRepositories,
  ).mockResolvedValue(listResponse([]))
  vi.mocked(interfaceLibraryApi.getProjectApiInterfaces).mockResolvedValue(
    listResponse([
      {
        interfaceId: 'interface-1',
        softwareRepositoryId: 'repository-1',
        softwareRepositoryName: '订单服务',
        name: '创建订单',
        method: 'POST',
        path: '/orders',
        description: '',
        tags: [],
        requirements: [],
        sourceType: 'manual',
        updatedAt: '2026-11-12T10:00:00',
      },
    ]),
  )
})

it('UI 生成设置不再接受源码 ZIP，保存后直接完成配置', async () => {
  const configurations: Record<string, unknown>[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://localhost').pathname
    if (path.endsWith('/configuration')) {
      configurations.push(JSON.parse(String(init?.body)))
      return response({
        taskId: 'saved-task',
        name: 'UI 测试',
        projectId: 'project',
        instruction: '覆盖失败状态',
      })
    }
    return response({ taskId: 'saved-task', projectId: 'project' })
  })
  const user = userEvent.setup()
  const { onSaved } = mount('ui')
  expect(document.querySelector('input[type="file"]')).toBeNull()
  expect(screen.queryByText(/源码 ZIP/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '保存设置' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('saved-task'))
  expect(configurations).toHaveLength(1)
  expect(configurations[0]).toMatchObject({ newConfiguration: false })
  expect(configurations[0].requestId).toEqual(expect.any(String))
})

it('首次 API 配置选择接口后保存，自动使用当前需求', async () => {
  const submitted = vi.fn()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    submitted(JSON.parse(String(init?.body)))
    return response({ taskId: 'api-task' })
  })
  const user = userEvent.setup()
  const { onSaved } = mount('api')
  await user.click(screen.getByLabelText('选择接口'))
  await user.click(await screen.findByText('POST /orders · 订单服务'))
  await user.click(screen.getByRole('button', { name: '保存设置' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('api-task'))
  expect(submitted).toHaveBeenCalledWith(
    expect.objectContaining({
      interfaceIds: ['interface-1'],
      requestId: expect.any(String),
    }),
  )
})

it('未选择接口时禁用保存', async () => {
  mount('api')
  expect(screen.getByRole('button', { name: '保存设置' })).toBeDisabled()
})

it('已有任务回显已选接口', async () => {
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({
    tasks: [{
      taskId: 'api-task',
      kind: 'api',
      name: '任务',
      sourceType: 'interface_library',
      hasSource: true,
      sourceFilename: '',
      interfaceIds: ['interface-1'],
    }],
    runCounts: { requirement_analysis: 0, function: 0, api: 1, ui: 0 },
  })
  mount('api', vi.fn(), 'api-task')
  expect(await screen.findByText('POST /orders · 订单服务')).toBeInTheDocument()
})
