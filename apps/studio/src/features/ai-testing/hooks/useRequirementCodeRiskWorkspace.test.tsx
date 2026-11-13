import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import { aiTestingApi } from '../api/aiTesting.api'
import { generationChainApi } from '../api/generationChain.api'
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
  vi.spyOn(baseServicesApi, 'getGitlabRequirementBindings').mockResolvedValue([
    { provider: 'gitlab', remoteResourceType: 'repository' },
  ] as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const rendered = renderHook(() => useRequirementCodeRiskWorkspace('req', 'project', active), { wrapper })
  return { ...rendered, client }
}

function chainWithVersions(versions: { versionId: string; versionNo: number; label: string }[]) {
  return {
    stages: [{
      stage: 'extracting_text',
      versions,
      latestVersion: versions.at(-1),
    }],
  } as never
}

it('网络失败后复用请求标识，成功后下一次生成使用新标识', async () => {
  const launch = vi.spyOn(aiTestingApi, 'runCodeRiskTask')
    .mockRejectedValueOnce(new TypeError('network unavailable'))
    .mockResolvedValueOnce({ runId: 'run-1', status: 'pending' } as never)
    .mockResolvedValueOnce({ runId: 'run-2', status: 'pending' } as never)
  const { result, unmount, client } = renderWorkspace()
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

it('默认携带最新已审核的材料整理版本', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue(chainWithVersions([
    { versionId: 'sv-1', versionNo: 1, label: 'V1' },
    { versionId: 'sv-2', versionNo: 2, label: 'V2' },
  ]))
  const launch = vi.spyOn(aiTestingApi, 'runCodeRiskTask')
    .mockResolvedValue({ runId: 'run-1', status: 'pending' } as never)
  const { result, unmount, client } = renderWorkspace(true)
  await waitFor(() => expect(result.current.runDisabledReason).toBeUndefined())

  await act(async () => { await result.current.start.mutateAsync() })

  expect(launch).toHaveBeenCalledWith('task', expect.objectContaining({
    requirementMaterialVersionId: 'sv-2',
  }))
  unmount()
  client.clear()
})

it('没有已审核材料整理版本时禁用确认运行', async () => {
  vi.spyOn(generationChainApi, 'chain').mockResolvedValue(chainWithVersions([]))
  const { unmount, client } = renderWorkspace(true)

  await waitFor(() => {
    expect(vi.mocked(usePersonalLlmChoice).mock.calls.at(-1)?.[1]?.confirmDisabled).toBe(true)
  })
  unmount()
  client.clear()
})
