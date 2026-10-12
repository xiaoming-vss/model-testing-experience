import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import type { ResourceBinding } from '@/features/base-services/types'
import { aiTestingApi } from '../api/aiTesting.api'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import { requirementDesignApi } from '../api/requirementDesign.api'
import { RequirementDesignWorkspace } from './RequirementDesignWorkspace'

vi.mock('../components/RequirementTaskRunDialogs', () => ({ RequirementTaskRunDialogs: () => <div>产物工作区</div> }))
vi.mock('../hooks/usePersonalLlmChoice', () => ({ usePersonalLlmChoice: () => ({ choose: async () => 'mine', chooseRun: async () => ({ connectionId: 'mine', checkpointEnabled: false, instruction: '重点分析鉴权' }), dialog: null }) }))
vi.mock('@/features/base-services/components/usePersonalConnectionChoice', () => ({
  usePersonalConnectionChoice: () => ({ choose: vi.fn(), forRequirement: vi.fn(async () => ({ 'https://gitlab.example.com': 'gl-1' })), forZentaoRequirement: vi.fn(), dialog: null }),
}))
vi.mock('../api/requirementDesign.api', () => ({ requirementDesignApi: { overview: vi.fn(), history: vi.fn(), start: vi.fn(), configure: vi.fn() } }))

import type { ListResponse } from '@/shared/api/request'

/** ListResponse 是 T[] 与 { total, items } 的交叉类型，测试夹具用 Object.assign 构造。 */
function listPayload<T>(items: T[]): ListResponse<T> {
  return Object.assign([...items], { total: items.length, items })
}

const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.clearAllMocks(); vi.restoreAllMocks() })

const task = { taskId: 'risk-task', taskType: 'code_risk_analysis', name: '登录需求 代码风险分析', projectId: 'project-1', sprintId: 'sprint-1', requirementId: 'req', instruction: '', createdAt: '2026-10-01T00:00:00.000Z' }
const repoBinding: ResourceBinding = { bindingId: 'b1', provider: 'gitlab', remoteResourceType: 'repository', remoteResourceId: 'repo-1', instanceUrl: 'https://gitlab.example.com', status: 'active' }
const successRun = { runId: 'run-1', taskId: 'risk-task', status: 'success', reviewStatus: 'pending', importStatus: 'pending', currentStage: 'completed', hasResult: true, createdAt: '2026-10-02T00:00:00.000Z' }

beforeEach(() => {
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({ tasks: [], runCounts: { requirement_analysis: 0, function: 0, api: 0, ui: 0 }, adoptedUnderstanding: false })
  vi.mocked(requirementDesignApi.history).mockResolvedValue(listPayload([]))
  vi.spyOn(aiTestingApi, 'getRequirementAnalysisRun').mockResolvedValue({ snapshotJson: {} })
  vi.spyOn(aiTestingApi, 'getCodeRiskTasks').mockResolvedValue(listPayload([task]))
  vi.spyOn(baseServicesApi, 'getGitlabRequirementBindings').mockResolvedValue(listPayload([repoBinding]))
  vi.spyOn(aiTestingApi, 'getCodeRiskTaskRuns').mockResolvedValue(listPayload([successRun]))
})

function mount(write = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter>
    <RequirementDesignWorkspace requirementId="req" projectId="project-1" canWrite={write} canExecute={write} canReview={write} />
  </MemoryRouter></QueryClientProvider></TestThemeProvider>)
}

async function openCodeRiskTab() {
  const user = userEvent.setup()
  // 角标数字依赖「任务列表 → 运行汇总」链式查询，等待时兼容加载中的无数字形态。
  await user.click(await screen.findByRole('tab', { name: /^代码风险\d*$/ }, { timeout: 5000 }))
  return user
}

it('代码风险页签复用运行历史工作区，标题栏提供刷新与运行分析', async () => {
  mount()
  await openCodeRiskTab()
  expect(await screen.findByText('run-1')).toBeInTheDocument()
  const toolbar = document.querySelector('.ai-requirement-design-toolbar')!
  expect(within(toolbar as HTMLElement).getByRole('button', { name: /^刷\s*新$/ })).toBeInTheDocument()
  expect(within(toolbar as HTMLElement).getByRole('button', { name: '运行分析' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: '创建第一条任务' })).not.toBeInTheDocument()
  expect(within(screen.getByText('run-1').closest('tr')!).getByRole('button', { name: '分析报告' })).toBeEnabled()
})

it('没有任务时显示空态，首次运行自动创建绑定当前需求的任务并发起分析', async () => {
  vi.spyOn(aiTestingApi, 'getCodeRiskTasks').mockResolvedValue(listPayload([]))
  vi.spyOn(aiTestingApi, 'createCodeRiskTask').mockResolvedValue({ ...task, taskId: 'created-task' })
  const run = vi.spyOn(aiTestingApi, 'runCodeRiskTask').mockResolvedValue({ runId: 'new-run', taskId: 'created-task', status: 'pending' })
  mount()
  const user = await openCodeRiskTab()
  const panel = screen.getByRole('tabpanel', { name: /^代码风险/ })
  expect(await within(panel).findByText('当前类型暂无运行记录')).toBeInTheDocument()
  const button = screen.getByRole('button', { name: '运行分析' })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  await waitFor(() => expect(aiTestingApi.createCodeRiskTask).toHaveBeenCalledWith('project-1', { requirementId: 'req' }))
  await waitFor(() => expect(run).toHaveBeenCalledWith('created-task', expect.objectContaining({
    llmConnectionId: 'mine', instruction: '重点分析鉴权', triggerType: 'manual',
    gitlabConnectionIds: { 'https://gitlab.example.com': 'gl-1' },
  })))
})

it('已有任务直接复用，不再创建新任务', async () => {
  const create = vi.spyOn(aiTestingApi, 'createCodeRiskTask')
  const run = vi.spyOn(aiTestingApi, 'runCodeRiskTask').mockResolvedValue({ runId: 'new-run', taskId: 'risk-task', status: 'pending' })
  mount()
  const user = await openCodeRiskTab()
  const button = await screen.findByRole('button', { name: '运行分析' })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  await waitFor(() => expect(run).toHaveBeenCalledWith('risk-task', expect.objectContaining({ llmConnectionId: 'mine' })))
  expect(create).not.toHaveBeenCalled()
})

it('需求未绑定代码仓库时运行禁用并说明原因', async () => {
  vi.spyOn(baseServicesApi, 'getGitlabRequirementBindings').mockResolvedValue(listPayload([]))
  mount()
  await openCodeRiskTab()
  const button = await screen.findByRole('button', { name: '运行分析' })
  expect(button).toBeDisabled()
  button.parentElement!.focus()
  expect(await screen.findByRole('tooltip')).toHaveTextContent('该需求未绑定代码仓库，请先在需求列表完成「代码绑定」。')
})

it('运行进行中禁止再次发起', async () => {
  vi.spyOn(aiTestingApi, 'getCodeRiskTaskRuns').mockResolvedValue(listPayload([{ ...successRun, status: 'running', currentStage: 'generate', hasResult: false }]))
  mount()
  await openCodeRiskTab()
  const button = await screen.findByRole('button', { name: '运行分析' })
  await waitFor(() => expect(button).toBeDisabled())
  button.parentElement!.focus()
  expect(await screen.findByRole('tooltip')).toHaveTextContent('当前任务尚未结束，请完成当前运行后再试。')
})

it('分析报告在弹窗中展示，失败运行提供错误信息', async () => {
  vi.spyOn(aiTestingApi, 'getCodeRiskRun').mockResolvedValue({
    ...successRun, report: { changeOverview: { filesChanged: 3 }, risks: [{ level: 'high', reason: '鉴权逻辑变更影响登录流程' }] },
  })
  mount()
  const user = await openCodeRiskTab()
  await user.click(await screen.findByRole('button', { name: '分析报告' }))
  const dialog = await screen.findByRole('dialog', { name: '分析报告' })
  expect(await within(dialog).findByText('鉴权逻辑变更影响登录流程')).toBeInTheDocument()
})

it('删除运行记录需要确认，只读成员没有运行与删除入口', async () => {
  const deleteRun = vi.spyOn(aiTestingApi, 'deleteCodeRiskRun').mockResolvedValue({})
  mount()
  const user = await openCodeRiskTab()
  await user.click(await screen.findByRole('button', { name: '删除运行记录' }))
  const confirm = await screen.findByRole('dialog', { name: '确认删除该运行记录？' })
  await user.click(within(confirm).getByRole('button', { name: /^删\s*除$/ }))
  await waitFor(() => expect(deleteRun).toHaveBeenCalledWith('run-1'))
})

it('只读成员没有运行与删除入口', async () => {
  mount(false)
  await openCodeRiskTab()
  expect(await screen.findByText('run-1')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '运行分析' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '删除运行记录' })).not.toBeInTheDocument()
})
