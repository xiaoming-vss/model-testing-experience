import type { ReactNode } from 'react'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { useDeleteTaskRun, useStartTaskRun } from './useTaskRunActions'

vi.mock('@/services/api', () => ({
  api: {
    deleteApiCaseGenerateTaskRun: vi.fn(),
    deleteFunctionalCaseGenerateTaskRun: vi.fn(),
    deleteUiCaseGenerateTaskRun: vi.fn(),
    deleteRequirementAnalysisRun: vi.fn(),
    deleteCodeRiskRun: vi.fn(),
  },
}))
vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))

const scenarios = [
  ['api', 'apiCaseGenerateTaskRun', 'apiCaseGenerateTaskRuns', 'apiCaseGenerateTask', 'apiCaseGenerateTasks', 'deleteApiCaseGenerateTaskRun'],
  ['functional', 'functionalCaseGenerateTaskRun', 'functionalCaseGenerateTaskRuns', 'functionalCaseGenerateTask', 'functionalCaseGenerateTasks', 'deleteFunctionalCaseGenerateTaskRun'],
  ['ui', 'uiCaseGenerateTaskRun', 'uiCaseGenerateTaskRuns', 'uiCaseGenerateTask', 'uiCaseGenerateTasks', 'deleteUiCaseGenerateTaskRun'],
  ['analysis', 'requirementAnalysisRun', 'requirementAnalysisTaskRuns', 'requirementAnalysisTask', 'requirementAnalysisTasks', 'deleteRequirementAnalysisRun'],
  ['codeRisk', 'codeRiskRun', 'codeRiskTaskRuns', 'codeRiskTask', 'codeRiskTasks', 'deleteCodeRiskRun'],
] as const

const clients: QueryClient[] = []
function setup() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } })
  clients.push(client)
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  return { client, wrapper }
}

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear())
  vi.resetAllMocks()
})

describe('任务运行公共操作', () => {
  it.each(scenarios)('%s 删除成功只清除对应记录，刷新当前任务列表', async (kind, runKey, runsKey, _taskKey, _tasksKey, method) => {
    const { client, wrapper } = setup()
    client.setQueryData([runKey, 'run-1'], { runId: 'run-1' })
    client.setQueryData([runKey, 'run-2'], { runId: 'run-2' })
    client.setQueryData([runKey, 'run-1', 'extra'], { keep: true })
    client.setQueryData([runsKey, 'task-1'], [])
    client.setQueryData([runsKey, 'task-2'], [])
    const resetDraft = vi.fn()
    const { result } = renderHook(() => useDeleteTaskRun({ kind, taskId: 'task-1', selectedRunId: 'run-1', onSelectedRunDeleted: resetDraft }), { wrapper })

    await act(async () => { await result.current.mutateAsync('run-1') })

    expect(api[method]).toHaveBeenCalledWith('run-1')
    expect(resetDraft).toHaveBeenCalledOnce()
    expect(client.getQueryData([runKey, 'run-1'])).toBeUndefined()
    expect(client.getQueryData([runKey, 'run-2'])).toBeDefined()
    expect(client.getQueryData([runKey, 'run-1', 'extra'])).toEqual({ keep: true })
    expect(client.getQueryState([runsKey, 'task-1'])?.isInvalidated).toBe(true)
    expect(client.getQueryState([runsKey, 'task-2'])?.isInvalidated).toBe(false)
  })

  it('删除其它记录不丢弃正在编辑的草稿', async () => {
    const { wrapper } = setup()
    const resetDraft = vi.fn()
    const { result } = renderHook(() => useDeleteTaskRun({ kind: 'ui', taskId: 'task-1', selectedRunId: 'run-2', onSelectedRunDeleted: resetDraft }), { wrapper })
    await act(async () => { await result.current.mutateAsync('run-1') })
    expect(resetDraft).not.toHaveBeenCalled()
  })

  it('删除失败保留记录与草稿', async () => {
    const { client, wrapper } = setup()
    client.setQueryData(['uiCaseGenerateTaskRun', 'run-1'], { runId: 'run-1' })
    client.setQueryData(['uiCaseGenerateTaskRuns', 'task-1'], [])
    vi.mocked(api.deleteUiCaseGenerateTaskRun).mockRejectedValue(new Error('运行中，不可删除'))
    const resetDraft = vi.fn()
    const { result } = renderHook(() => useDeleteTaskRun({ kind: 'ui', taskId: 'task-1', selectedRunId: 'run-1', onSelectedRunDeleted: resetDraft }), { wrapper })
    await act(async () => { await expect(result.current.mutateAsync('run-1')).rejects.toThrow('运行中') })
    expect(resetDraft).not.toHaveBeenCalled()
    expect(client.getQueryData(['uiCaseGenerateTaskRun', 'run-1'])).toBeDefined()
    expect(client.getQueryState(['uiCaseGenerateTaskRuns', 'task-1'])?.isInvalidated).toBe(false)
  })

  it.each(scenarios)('%s 执行后保持该类型原有的缓存刷新范围', async (kind, _runKey, runsKey, taskKey, tasksKey) => {
    const { client, wrapper } = setup()
    client.setQueryData([runsKey, 'task-1'], [])
    client.setQueryData([taskKey, 'task-1'], {})
    client.setQueryData([tasksKey, 'project-1'], [])
    const run = { runId: 'new-run', projectId: 'project-1' }
    const startRun = vi.fn<(input: { connectionId: string }) => Promise<typeof run>>(async () => run)
    const onStarted = vi.fn()
    const { result } = renderHook(() => useStartTaskRun({ kind, taskId: 'task-1', startRun, onStarted }), { wrapper })
    await act(async () => { await result.current.mutateAsync({ connectionId: 'connection-1' }) })
    expect(startRun.mock.calls[0][0]).toEqual({ connectionId: 'connection-1' })
    expect(onStarted).toHaveBeenCalledWith(run)
    expect(client.getQueryState([runsKey, 'task-1'])?.isInvalidated).toBe(true)
    const refreshTask = kind !== 'ui' && kind !== 'codeRisk'
    expect(client.getQueryState([taskKey, 'task-1'])?.isInvalidated).toBe(refreshTask)
    expect(client.getQueryState([tasksKey, 'project-1'])?.isInvalidated).toBe(refreshTask)
  })

  it('执行失败不切换当前运行或刷新列表', async () => {
    const { client, wrapper } = setup()
    client.setQueryData(['apiCaseGenerateTaskRuns', 'task-1'], [])
    const onStarted = vi.fn()
    const startRun = vi.fn<(input: string) => Promise<{ runId: string }>>(async () => { throw new Error('执行失败') })
    const { result } = renderHook(() => useStartTaskRun({ kind: 'api', taskId: 'task-1', startRun, onStarted }), { wrapper })
    await act(async () => { await expect(result.current.mutateAsync('connection-1')).rejects.toThrow('执行失败') })
    expect(onStarted).not.toHaveBeenCalled()
    expect(client.getQueryState(['apiCaseGenerateTaskRuns', 'task-1'])?.isInvalidated).toBe(false)
  })
})
