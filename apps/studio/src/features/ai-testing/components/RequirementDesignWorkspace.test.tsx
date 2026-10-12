import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { aiTestingApi } from '../api/aiTesting.api'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import { requirementDesignApi } from '../api/requirementDesign.api'
import { RequirementDesignWorkspace } from './RequirementDesignWorkspace'

vi.mock('../components/RequirementTaskRunDialogs', () => ({ RequirementTaskRunDialogs: () => <div>产物工作区</div> }))
vi.mock('../hooks/usePersonalLlmChoice', () => ({ usePersonalLlmChoice: () => ({ choose: async () => 'mine', chooseRun: async () => ({ connectionId: 'mine', checkpointEnabled: true }), dialog: null }) }))
vi.mock('../api/requirementDesign.api', () => ({ requirementDesignApi: { overview: vi.fn(), history: vi.fn(), start: vi.fn(), configure: vi.fn() } }))
import type { ListResponse } from '@/shared/api/request'

/** ListResponse 是 T[] 与 { total, items } 的交叉类型，测试夹具用 Object.assign 构造。 */
function listPayload<T>(items: T[]): ListResponse<T> {
  return Object.assign([...items], { total: items.length, items })
}

const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.clearAllMocks(); vi.restoreAllMocks() })
beforeEach(() => {
  vi.spyOn(aiTestingApi, 'getRequirementAnalysisRun').mockResolvedValue({ snapshotJson: {} })
  vi.spyOn(aiTestingApi, 'getCodeRiskTasks').mockResolvedValue(listPayload([]))
  vi.spyOn(baseServicesApi, 'getGitlabRequirementBindings').mockResolvedValue(listPayload([]))
  const emptyCandidate = { reviewStatus: 'pending' as const, importStatus: 'pending' as const, importedTargets: [], importedAt: null, importMigrationComplete: true }
  vi.spyOn(aiTestingApi, 'getFunctionalCaseGenerateTaskRun').mockResolvedValue(emptyCandidate)
  vi.spyOn(aiTestingApi, 'getApiCaseGenerateTaskRun').mockResolvedValue(emptyCandidate)
  vi.spyOn(aiTestingApi, 'getUiCaseGenerateTaskRun').mockResolvedValue(emptyCandidate)
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({ tasks: [{ taskId: 'task', kind: 'requirement_analysis', name: '需求分析', sourceType: 'docx', hasSource: true, sourceFilename: '' }], runCounts: { requirement_analysis: 3, function: 2, api: 0, ui: 0 }, adoptedUnderstanding: false })
  vi.mocked(requirementDesignApi.history).mockResolvedValue({ items: [
    { runId: 'rejected', taskId: 'old-task', status: 'success', reviewStatus: 'rejected', currentStage: 'completed', hasResult: true },
    { runId: 'pending', taskId: 'task', status: 'success', reviewStatus: 'pending', currentStage: 'completed', hasResult: true },
  ], total: 2 })
})
function mount(write = true, docked = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter>{docked ? <RequirementDesignWorkspace requirementId="req" projectId="project" document={<div>需求正文</div>} canWrite canExecute canReview /> : <RequirementDesignWorkspace requirementId="req" projectId="project"
    canWrite={write} canExecute={write} canReview={write} />}</MemoryRouter></QueryClientProvider></TestThemeProvider>)
}
it('文档与四类设计以同级 Tab 切换并保留文档节点', async () => {
  mount(true, true)
  const user = userEvent.setup()
  const documentNode = screen.getByText('需求正文')
  expect(screen.getByRole('tab', { name: '需求文档' })).toHaveAttribute('aria-selected', 'true')
  await user.click(await screen.findByRole('tab', { name: '功能测试2' }))
  expect(screen.getByRole('tab', { name: '功能测试2' })).toHaveAttribute('aria-selected', 'true')
  expect(documentNode).not.toBeVisible()
  expect(screen.queryByRole('button', { name: '收起测试设计' })).not.toBeInTheDocument()
  const toolbar = document.querySelector('.ai-requirement-design-toolbar')!
  expect(within(toolbar as HTMLElement).getByRole('button', { name: /^刷\s*新$/ })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /参考需求/ })).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: '需求文档' }))
  expect(screen.getByRole('tabpanel', { name: '需求文档' })).toContainElement(documentNode)
  expect(documentNode).toBeVisible()
  expect(requirementDesignApi.start).not.toHaveBeenCalled()
})
it('按当前需求切换类型与运行历史，并阻止缺少有效增强文本时生成功能用例', async () => {
  mount()
  await screen.findByText('rejected')
  const user = userEvent.setup()
  await user.click(screen.getByRole('tab', { name: '功能测试2' }))
  await waitFor(() => expect(requirementDesignApi.history).toHaveBeenLastCalledWith('req', 'function', { page: 1, pageSize: 20, pipelineFilter: 'all' }))
  expect(screen.getByRole('button', { name: '生成用例' })).toBeDisabled()
  expect(screen.queryByText('请先补充有效的需求增强文本，再生成功能用例。')).not.toBeInTheDocument()
  await user.hover(screen.getByRole('button', { name: '生成用例' }).parentElement!)
  await waitFor(() => expect(screen.getByText('请先补充有效的需求增强文本，再生成功能用例。')).toBeVisible())
  await user.unhover(screen.getByRole('button', { name: '生成用例' }).parentElement!)
  await waitFor(() => expect(screen.queryByText('请先补充有效的需求增强文本，再生成功能用例。')).not.toBeVisible())
})
it('已拒绝历史只允许查看产物和删除，待审核记录保留审核按钮', async () => {
  mount()
  const rejectedRow = (await screen.findByText('rejected')).closest('tr')!
  expect(within(rejectedRow).queryByRole('button', { name: /^审\s*核$/ })).not.toBeInTheDocument()
  expect(within(rejectedRow).getByRole('button', { name: '删除运行记录' })).toBeEnabled()
  expect(within(rejectedRow).queryByRole('button', { name: /更多/ })).not.toBeInTheDocument()
  const pendingRow = screen.getByText('pending').closest('tr')!
  expect(within(pendingRow).getByRole('button', { name: /^审\s*核$/ })).toBeEnabled()
})
it('只读成员没有配置、运行、审核或删除入口', async () => {
  mount(false)
  await screen.findByText('rejected')
  expect(screen.queryByRole('button', { name: /^设\s*置$/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '运行分析' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '删除运行记录' })).not.toBeInTheDocument()
})
it('请求响应丢失重试保留请求 UUID，成功后下一次运行使用新 UUID', async () => {
  vi.mocked(requirementDesignApi.start).mockRejectedValueOnce(new Error('网络中断')).mockResolvedValue({ runId: 'new-run', taskId: 'task', status: 'pending' })
  mount()
  const user = userEvent.setup()
  const button = await screen.findByRole('button', { name: '运行分析' })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  await waitFor(() => expect(requirementDesignApi.start).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  await waitFor(() => expect(requirementDesignApi.start).toHaveBeenCalledTimes(2))
  const first = vi.mocked(requirementDesignApi.start).mock.calls[0][2]
  const second = vi.mocked(requirementDesignApi.start).mock.calls[1][2]
  expect(first).toEqual(second)
  expect(first).toMatchObject({ taskId: 'task', connectionId: 'mine', checkpointEnabled: true })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  await waitFor(() => expect(requirementDesignApi.start).toHaveBeenCalledTimes(3))
  expect(vi.mocked(requirementDesignApi.start).mock.calls[2][2].requestId).not.toBe(first.requestId)
})

it('切换选中历史记录时，执行中的配置仍禁止再次启动', async () => {
  vi.mocked(requirementDesignApi.history).mockResolvedValue({ items: [
    { runId: 'extracting', taskId: 'task', status: 'waiting_review', reviewStatus: 'pending', currentStage: 'extracting_text' },
    { runId: 'older-rejected', taskId: 'old-task', status: 'success', reviewStatus: 'rejected', currentStage: 'completed', hasResult: true },
  ], total: 2 })
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({ tasks: [{ taskId: 'task', kind: 'requirement_analysis', name: '需求分析', sourceType: 'docx', hasSource: true, sourceFilename: '' }], runCounts: { requirement_analysis: 2, function: 0, api: 0, ui: 0 }, activeTaskIds: ['task'], adoptedUnderstanding: false })
  mount()
  await screen.findByText('extracti')
  expect(screen.getByRole('button', { name: '运行分析' })).toBeDisabled()
  const user = userEvent.setup()
  await user.click(screen.getByText('older-re').closest('tr')!)
  expect(screen.getByText('older-re').closest('tr')).toHaveClass('ai-task-run-table-row-active')
  expect(screen.getByRole('button', { name: '运行分析' })).toBeDisabled()
})


it('功能用例审核通过后可以生成图谱，使用本次操作人的模型授权', async () => {
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({ tasks: [], runCounts: { requirement_analysis: 0, function: 1, api: 0, ui: 0 }, adoptedUnderstanding: true })
  vi.mocked(requirementDesignApi.history).mockResolvedValue({ items: [{ runId: 'cases', taskId: 'function-task', status: 'success', reviewStatus: 'approved', importStatus: 'pending', currentStage: 'completed', hasResult: true }], total: 1 })
  const generate = vi.spyOn(aiTestingApi, 'generateFunctionalCaseRelationAnalysis').mockResolvedValue({ reviewStatus: 'approved', importStatus: 'pending', importedTargets: [], importedAt: null, importMigrationComplete: true })
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('tab', { name: '功能测试1' }))
  await user.click(await screen.findByRole('button', { name: '生成图谱' }))
  await waitFor(() => expect(generate).toHaveBeenCalledWith('cases', 'mine'))
})

it.each(['requirement_analysis', 'function'] as const)('首次 %s 自动创建任务，创建响应丢失后重试复用身份', async kind => {
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({ tasks: [], runCounts: { requirement_analysis: 0, function: 0, api: 0, ui: 0 }, adoptedUnderstanding: true })
  vi.mocked(requirementDesignApi.configure).mockRejectedValueOnce(new Error('网络中断')).mockResolvedValue({ taskId: 'created-task', name: '需求测试', instruction: '' })
  vi.mocked(requirementDesignApi.start).mockResolvedValue({ runId: 'new-run', taskId: 'created-task' })
  mount()
  const user = userEvent.setup()
  if (kind === 'function') await user.click(await screen.findByRole('tab', { name: '功能测试0' }))
  const button = await screen.findByRole('button', { name: kind === 'function' ? '生成用例' : '运行分析' })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  await waitFor(() => expect(requirementDesignApi.configure).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(button).toBeEnabled())
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await user.click(button)
  await waitFor(() => expect(requirementDesignApi.start).toHaveBeenCalledWith('req', kind, expect.objectContaining({ taskId: 'created-task', connectionId: 'mine', checkpointEnabled: true })))
  expect(vi.mocked(requirementDesignApi.configure).mock.calls[0]).toEqual(vi.mocked(requirementDesignApi.configure).mock.calls[1])
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  await waitFor(() => expect(requirementDesignApi.start).toHaveBeenCalledTimes(2))
  expect(requirementDesignApi.configure).toHaveBeenCalledTimes(2)
})

it('多个历史任务不显示配置选择，设置自动加载当前任务', async () => {
  const task = { taskId: 'task', kind: 'api' as const, name: 'API 测试', sourceType: 'openapi', hasSource: true, sourceFilename: '' }
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({ tasks: [task, { ...task, taskId: 'old-task' }], runCounts: { requirement_analysis: 2, function: 0, api: 0, ui: 0 }, adoptedUnderstanding: true })
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ code: 0, data: { taskId: 'task', sourceContent: '已有接口文档' } }), { headers: { 'Content-Type': 'application/json' } }))
  mount()
  await screen.findByText('rejected')
  expect(screen.queryByRole('combobox', { name: '当前生成配置' })).not.toBeInTheDocument()
  await userEvent.setup().click(screen.getByRole('tab', { name: 'API 测试0' }))
  await userEvent.setup().click(screen.getByRole('button', { name: /^设\s*置$/ }))
  const dialog = await screen.findByRole('dialog', { name: '生成设置' })
  expect(within(dialog).queryByRole('combobox')).not.toBeInTheDocument()
  expect(within(dialog).queryByText('新增配置')).not.toBeInTheDocument()
  await waitFor(() => expect(within(dialog).getByRole('textbox', { name: 'OpenAPI / Swagger 文档' })).toHaveValue('已有接口文档'))
})

it('Tab 支持方向键和首尾导航，且切换不提交生成', async () => {
  mount(true, true)
  const user = userEvent.setup()
  await screen.findByRole('tab', { name: '功能测试2' })
  screen.getByRole('tab', { name: '需求文档' }).focus()
  await user.keyboard('{ArrowRight}')
  expect(screen.getByRole('tab', { name: '需求分析3' })).toHaveFocus()
  expect(screen.getByRole('tab', { name: '需求文档' })).toHaveAttribute('tabindex', '-1')
  await user.keyboard('{End}')
  expect(await screen.findByRole('tab', { name: '代码风险0' })).toHaveFocus()
  await user.keyboard('{ArrowRight}')
  expect(screen.getByRole('tab', { name: '需求文档' })).toHaveFocus()
  await user.keyboard('{ArrowLeft}{Home}')
  expect(screen.getByRole('tab', { name: '需求文档' })).toHaveAttribute('aria-selected', 'true')
  expect(requirementDesignApi.start).not.toHaveBeenCalled()
})

it('运行中禁用入口可通过聚焦获知原因，计数明确表示所有状态运行次数', async () => {
  vi.mocked(requirementDesignApi.overview).mockResolvedValue({ tasks: [{ taskId: 'task', kind: 'requirement_analysis', name: '需求分析', sourceType: 'docx', hasSource: true, sourceFilename: '' }], activeTaskIds: ['task'], runCounts: { requirement_analysis: 3, function: 0, api: 0, ui: 0 }, adoptedUnderstanding: true })
  mount()
  const tab = await screen.findByRole('tab', { name: '需求分析3' })
  expect(tab).toHaveAttribute('aria-description', '本需求的需求分析历史运行共 3 次，含所有状态。')
  const run = screen.getByRole('button', { name: '运行分析' })
  expect(run).toBeDisabled()
  const user = userEvent.setup()
  run.parentElement!.focus()
  expect(await screen.findByRole('tooltip')).toHaveTextContent('当前任务尚未结束，请完成当前运行后再试。')
  await user.keyboard('{Enter}')
  expect(requirementDesignApi.start).not.toHaveBeenCalled()
})
