import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { aiTestingApi } from '../api/aiTesting.api'
import { generationCandidatesApi } from '../api/generationCandidates.api'
import { useRequirementCodeRiskWorkspace } from './useRequirementCodeRiskWorkspace'
import { usePersonalLlmChoice } from './usePersonalLlmChoice'

vi.mock('./usePersonalLlmChoice', () => ({ usePersonalLlmChoice: vi.fn() }))
vi.mock('@/features/base-services/components/usePersonalConnectionChoice', () => ({
  usePersonalConnectionChoice: () => ({ forRequirement: async () => ({ repo: 'gitlab' }) }),
}))
vi.mock('@/shared/utils/feedback', () => ({ message: { error: vi.fn(), success: vi.fn() } }))

beforeEach(() => {
  vi.mocked(usePersonalLlmChoice).mockReturnValue({
    chooseRun: async () => ({ connectionId: 'llm', instruction: '' }),
  } as never)
})

afterEach(() => vi.restoreAllMocks())

function renderWorkspace(active = false) {
  vi.spyOn(aiTestingApi, 'getCodeRiskTasks').mockResolvedValue([
    { taskId: 'task', requirementId: 'req' },
  ] as never)
  vi.spyOn(aiTestingApi, 'getCodeRiskTaskRuns').mockResolvedValue([] as never)
  vi.spyOn(interfaceLibraryApi, 'getRequirementSoftwareRepositories').mockResolvedValue([
    { softwareRepositoryId: 'repo-1', softwareRepositoryName: 'repo-1', branch: 'main', baselineBranch: 'main' },
  ] as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const rendered = renderHook(() => useRequirementCodeRiskWorkspace('req', 'project', active), { wrapper })
  return { ...rendered, client }
}

it('弹窗未打开时不读取任务、运行和仓库关联', async () => {
  const { result, unmount, client } = renderWorkspace(false)
  await act(async () => { await new Promise<void>(resolve => setTimeout(resolve, 0)) })
  expect(aiTestingApi.getCodeRiskTasks).not.toHaveBeenCalled()
  expect(aiTestingApi.getCodeRiskTaskRuns).not.toHaveBeenCalled()
  expect(interfaceLibraryApi.getRequirementSoftwareRepositories).not.toHaveBeenCalled()
  expect(result.current.runDisabledReason).toBe('正在读取运行信息，请稍候。')
  unmount()
  client.clear()
})

it('网络失败后复用请求标识，成功后下一次生成使用新标识', async () => {
  const launch = vi.spyOn(aiTestingApi, 'runCodeRiskTask')
    .mockRejectedValueOnce(new TypeError('network unavailable'))
    .mockResolvedValueOnce({ runId: 'run-1', status: 'pending' } as never)
    .mockResolvedValueOnce({ runId: 'run-2', status: 'pending' } as never)
  const { result, unmount, client } = renderWorkspace(true)
  await waitFor(() => expect(result.current.runDisabledReason).toBeUndefined())

  await act(async () => { await expect(result.current.start.mutateAsync()).rejects.toThrow('network unavailable') })
  await act(async () => { await result.current.start.mutateAsync() })
  await act(async () => { await result.current.start.mutateAsync() })
  const ids = launch.mock.calls.map(([, body]) => body.requestId)
  expect(ids[0]).toBeTruthy()
  expect(ids[1]).toBe(ids[0])
  expect(ids[2]).not.toBe(ids[1])
  unmount()
  client.clear()
})

it('使用当前材料，不发送历史版本选择', async () => {
  vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: 'material-a', invalidatedAt: null } as never)
  const launch = vi.spyOn(aiTestingApi, 'runCodeRiskTask').mockResolvedValue({ runId: 'run-1', status: 'pending' } as never)
  const { result, unmount, client } = renderWorkspace(true)
  await waitFor(() => expect(vi.mocked(usePersonalLlmChoice).mock.calls.at(-1)?.[1]?.confirmDisabled).toBe(false))
  await waitFor(() => expect(result.current.runDisabledReason).toBeUndefined())
  await act(async () => { await result.current.start.mutateAsync() })
  expect(launch.mock.calls[0][1]).not.toHaveProperty('requirementMaterialVersionId')
  unmount()
  client.clear()
})

it('没有当前材料时禁用确认', async () => {
  vi.spyOn(generationCandidatesApi, 'current').mockResolvedValue({ candidateId: null, invalidatedAt: null } as never)
  const { unmount, client } = renderWorkspace(true)
  await waitFor(() => expect(generationCandidatesApi.current).toHaveBeenCalled())
  await waitFor(() => expect(vi.mocked(usePersonalLlmChoice).mock.calls.at(-1)?.[1]?.confirmDisabled).toBe(true))
  unmount()
  client.clear()
})
