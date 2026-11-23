import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { generationChainApi } from '../api/generationChain.api'
import { generationCandidatesApi } from '../api/generationCandidates.api'
import { profileCandidatesApi } from '../api/profileCandidates.api'
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
  vi.spyOn(interfaceLibraryApi, 'getRequirementSoftwareRepositories').mockResolvedValue([
    { softwareRepositoryId: 'repo-1', softwareRepositoryName: 'repo-1', branch: 'main', baselineBranch: 'main' },
  ] as never)
  vi.spyOn(repositoryProfileApi, 'getRepositoryProfileTasks').mockResolvedValue([
    { taskId: 'task', requirementId: 'req' },
  ] as never)
  vi.spyOn(repositoryProfileApi, 'getRepositoryProfileTaskRuns').mockResolvedValue([] as never)
  vi.spyOn(profileCandidatesApi, 'list').mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
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

it('候选模式使用已采用材料并移除旧版本参数', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue({ candidateMode: true, stages: [{ stage: 'extracting_text', versions: [] }] } as never)
  vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: 'material-a', invalidatedAt: null } as never)
  const launch = vi.spyOn(repositoryProfileApi, 'runRepositoryProfileTask').mockResolvedValue({ runId: 'run-1', status: 'pending' } as never)
  const { result, unmount, client } = renderWorkspace()
  await waitFor(() => expect(result.current.currentMaterialAvailable).toBe(true))
  await waitFor(() => expect(result.current.runDisabledReason).toBeUndefined())
  await act(async () => { await result.current.start.mutateAsync() })
  expect(launch).toHaveBeenCalledWith('task', expect.not.objectContaining({ requirementMaterialVersionId: expect.anything() }))
  unmount()
  client.clear()
})

it('候选模式没有当前材料时禁止画像运行', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue({ candidateMode: true, stages: [{ stage: 'extracting_text', versions: [] }] } as never)
  vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: null, invalidatedAt: null } as never)
  const { result, unmount, client } = renderWorkspace()
  await waitFor(() => expect(result.current.runDisabledReason).toContain('采用有效的材料整理'))
  unmount()
  client.clear()
})

it('画像候选显式采用并携带候选和当前令牌', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue({ candidateMode: true, stages: [{ stage: 'extracting_text', versions: [] }] } as never)
  vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: 'material-a', invalidatedAt: null } as never)
  const candidate = { candidateId: 'profile-a', snapshotId: 'profile-snapshot', candidateToken: 'candidate-token',
    currentAttemptId: 'attempt-a', derivedFromCandidateId: null, disposition: 'available' as const, generationMode: 'current' as const,
    frozenAt: null, createdBy: 'user', createdAt: '2026-11-20T10:00:00Z', isCurrent: false }
  vi.mocked(profileCandidatesApi.list).mockResolvedValue({ items: [candidate], total: 1, page: 1, pageSize: 20 })
  vi.spyOn(profileCandidatesApi, 'current').mockResolvedValue({ candidateId: null, currentToken: 'empty-token' } as never)
  vi.spyOn(profileCandidatesApi, 'detail').mockResolvedValue({ ...candidate, content: '{"repositories":[],"overallSummary":"画像"}', format: 'json' })
  const adopt = vi.spyOn(profileCandidatesApi, 'adopt').mockResolvedValue({ requestId: 'request', candidateId: 'profile-a', contentToken: 'current-token', replayed: false })
  const { result, unmount, client } = renderWorkspace()
  await waitFor(() => expect(result.current.selectedCandidate?.candidateId).toBe('profile-a'))
  await waitFor(() => expect(result.current.currentProfile?.currentToken).toBe('empty-token'))
  expect(result.current.selectedProfileView?.profile?.overallSummary).toBe('画像')
  await act(async () => { await result.current.adopt.mutateAsync() })
  expect(adopt).toHaveBeenCalledWith('req', expect.objectContaining({ candidateId: 'profile-a', expectedCandidateToken: 'candidate-token', expectedAttemptId: 'attempt-a', expectedCurrentToken: 'empty-token' }))
  unmount()
  client.clear()
})

it('没有关联软件仓库时禁用运行', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue({ candidateMode: true, stages: [] } as never)
  vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: 'material-a', invalidatedAt: null } as never)
  vi.spyOn(interfaceLibraryApi, 'getRequirementSoftwareRepositories').mockResolvedValue([] as never)
  const { result, unmount, client } = renderWorkspace()

  await waitFor(() => {
    expect(result.current.runDisabledReason).toContain('未关联软件仓库')
  })
  unmount()
  client.clear()
})

it('网络失败后复用请求标识，成功后下一次运行使用新标识', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue({ candidateMode: true, stages: [] } as never)
  vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: 'material-a', invalidatedAt: null } as never)
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
