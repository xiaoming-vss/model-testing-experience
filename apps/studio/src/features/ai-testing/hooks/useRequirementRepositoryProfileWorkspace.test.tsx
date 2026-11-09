import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import { generationChainApi } from '../api/generationChain.api'
import { repositoryProfileApi } from '../api/repositoryProfile.api'
import { useRequirementRepositoryProfileWorkspace } from './useRequirementRepositoryProfileWorkspace'
import { usePersonalLlmChoice } from './usePersonalLlmChoice'

vi.mock('./usePersonalLlmChoice', () => ({ usePersonalLlmChoice: vi.fn() }))
vi.mock('@/features/base-services/components/usePersonalConnectionChoice', () => ({
  usePersonalConnectionChoice: () => ({
    forRequirement: async () => ({ repo: 'gitlab' }),
    dialog: null,
  }),
}))
vi.mock('@/shared/utils/feedback', () => ({ message: { error: vi.fn(), success: vi.fn() } }))

beforeEach(() => {
  vi.mocked(usePersonalLlmChoice).mockReturnValue({
    chooseRun: async () => ({ connectionId: 'llm', instruction: '' }),
  } as never)
  vi.spyOn(baseServicesApi, 'getGitlabRequirementBindings').mockResolvedValue([
    { provider: 'gitlab', remoteResourceType: 'repository' },
  ] as never)
  vi.spyOn(repositoryProfileApi, 'getRepositoryProfileTasks').mockResolvedValue([
    { taskId: 'task', requirementId: 'req' },
  ] as never)
  vi.spyOn(repositoryProfileApi, 'getRepositoryProfileTaskRuns').mockResolvedValue([] as never)
  vi.spyOn(repositoryProfileApi, 'getRepositoryProfileVersions').mockResolvedValue([] as never)
})

afterEach(() => vi.restoreAllMocks())

function renderWorkspace(active = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const rendered = renderHook(
    () => useRequirementRepositoryProfileWorkspace('req', 'project', active),
    { wrapper },
  )
  return { ...rendered, client }
}

function chainWithVersions(versions: { versionId: string; versionNo: number; label: string }[]) {
  return {
    stages: [
      {
        stage: 'feature_understanding',
        versions,
        latestVersion: versions.at(-1),
      },
    ],
  } as never
}

it('默认携带最新已审核需求理解版本，并独立于阶段版本选择', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue(
    chainWithVersions([
      { versionId: 'sv-1', versionNo: 1, label: 'V1' },
      { versionId: 'sv-2', versionNo: 2, label: 'V2' },
    ]),
  )
  const launch = vi
    .spyOn(repositoryProfileApi, 'runRepositoryProfileTask')
    .mockResolvedValue({ runId: 'run-1', status: 'pending' } as never)
  const chainRun = vi.spyOn(generationChainApi, 'run')
  const { result, unmount, client } = renderWorkspace()

  await waitFor(() => expect(result.current.understandingVersionId).toBe('sv-2'))
  expect(result.current.runDisabledReason).toBeUndefined()

  act(() => result.current.setUnderstandingVersionId('sv-1'))
  await act(async () => {
    await result.current.start.mutateAsync()
  })

  expect(launch).toHaveBeenCalledWith(
    'task',
    expect.objectContaining({
      requirementUnderstandingVersionId: 'sv-1',
      llmConnectionId: 'llm',
      gitlabConnectionIds: { repo: 'gitlab' },
    }),
  )
  expect(chainRun).not.toHaveBeenCalled()
  unmount()
  client.clear()
})

it('默认选择最新画像版本，也可以切换历史版本', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue(
    chainWithVersions([{ versionId: 'sv-1', versionNo: 1, label: 'V1' }]),
  )
  vi.spyOn(repositoryProfileApi, 'getRepositoryProfileVersions').mockResolvedValue([
    {
      versionId: 'version-2', versionNo: 2, label: 'v2', sourceRunId: 'run-2',
      resultYaml: '{"repositories":[],"overallSummary":"v2"}', createdAt: '2026-11-09T10:00:00Z',
      profile: { repositories: [], overallSummary: 'v2' },
    },
    {
      versionId: 'version-1', versionNo: 1, label: 'v1', sourceRunId: 'run-1',
      resultYaml: '{"repositories":[],"overallSummary":"v1"}', createdAt: '2026-11-09T09:00:00Z',
      profile: { repositories: [], overallSummary: 'v1' },
    },
  ] as never)
  const { result, unmount, client } = renderWorkspace()

  await waitFor(() => expect(result.current.selectedVersionId).toBe('version-2'))
  expect(result.current.latestVersion?.versionId).toBe('version-2')
  expect(result.current.selectedVersion?.profile?.overallSummary).toBe('v2')

  act(() => result.current.setSelectedVersionId('version-1'))
  await waitFor(() => expect(result.current.selectedVersion?.profile?.overallSummary).toBe('v1'))
  unmount()
  client.clear()
})

it('没有已审核需求理解版本时禁用运行', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue(chainWithVersions([]))
  const { result, unmount, client } = renderWorkspace()

  await waitFor(() => {
    expect(result.current.runDisabledReason).toContain('审核通过需求理解')
  })
  unmount()
  client.clear()
})

it('没有绑定仓库时禁用运行', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue(
    chainWithVersions([{ versionId: 'sv-1', versionNo: 1, label: 'V1' }]),
  )
  vi.spyOn(baseServicesApi, 'getGitlabRequirementBindings').mockResolvedValue([] as never)
  const { result, unmount, client } = renderWorkspace()

  await waitFor(() => {
    expect(result.current.runDisabledReason).toContain('未绑定代码仓库')
  })
  unmount()
  client.clear()
})

it('网络失败后复用请求标识，成功后下一次运行使用新标识', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue(
    chainWithVersions([{ versionId: 'sv-1', versionNo: 1, label: 'V1' }]),
  )
  const launch = vi
    .spyOn(repositoryProfileApi, 'runRepositoryProfileTask')
    .mockRejectedValueOnce(new TypeError('network unavailable'))
    .mockResolvedValueOnce({ runId: 'run-1', status: 'pending' } as never)
    .mockResolvedValueOnce({ runId: 'run-2', status: 'pending' } as never)
  const { result, unmount, client } = renderWorkspace()
  await waitFor(() => expect(result.current.runDisabledReason).toBeUndefined())

  await act(async () => {
    await expect(result.current.start.mutateAsync()).rejects.toThrow('network unavailable')
  })
  await act(async () => {
    await result.current.start.mutateAsync()
  })
  await act(async () => {
    await result.current.start.mutateAsync()
  })

  const ids = launch.mock.calls.map(([, body]) => body.requestId)
  expect(ids[0]).toBeTruthy()
  expect(ids[1]).toBe(ids[0])
  expect(ids[2]).not.toBe(ids[1])
  unmount()
  client.clear()
})
