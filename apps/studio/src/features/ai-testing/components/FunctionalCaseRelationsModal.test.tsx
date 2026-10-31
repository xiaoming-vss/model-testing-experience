import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { api } from '@/services/api'
import { aiTestingApi } from '../api/aiTesting.api'
import type { FunctionalCaseGenerateTaskRun } from '../types'
import { FunctionalCaseRelationsModal } from './FunctionalCaseRelationsModal'

vi.mock('@/services/api', () => ({ api: { getFunctionalCaseGenerateTask: vi.fn(), getFunctionalCaseGenerateTaskRun: vi.fn() } }))
vi.mock('../api/aiTesting.api', () => ({ aiTestingApi: { generateFunctionalCaseRelationAnalysis: vi.fn() } }))
vi.mock('@/features/projects/components/ProjectAccessScope', () => ({ ProjectAccessScope: ({ children }: { children: React.ReactNode }) => children }))
vi.mock('./FunctionalCaseRelationsGraph', () => ({ FunctionalCaseRelationsGraph: ({ content }: { content: string }) => <div data-testid="relations-content">{content}</div> }))

let client: QueryClient
const ready: FunctionalCaseGenerateTaskRun = { runId: 'run', taskId: 'task', status: 'success', currentStage: 'completed', reviewStatus: 'approved', configJson: {}, resultYaml: '[]', importStatus: 'pending', importedTargets: [], importedAt: '', importMigrationComplete: true }
const queued: FunctionalCaseGenerateTaskRun = { ...ready, status: 'pending', currentStage: 'relation_analysis' }
const relations = { schema_version: '2.0', main_paths: [{ path_id: 'P01', case_ids: ['c1', 'c2'] }], edges: [] }
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  vi.mocked(api.getFunctionalCaseGenerateTask).mockResolvedValue({ taskId: 'task', name: '需求', projectId: 'project', instruction: '' })
  vi.mocked(api.getFunctionalCaseGenerateTaskRun).mockResolvedValue(ready)
  vi.mocked(aiTestingApi.generateFunctionalCaseRelationAnalysis).mockResolvedValue(queued)
})
afterEach(() => { cleanup(); client.clear(); vi.clearAllMocks() })
function mount() {
  render(<TestThemeProvider><QueryClientProvider client={client}>
    <FunctionalCaseRelationsModal embedded open taskId="task" runId="run" onClose={() => {}} chooseConnection={async () => 'llm'} />
  </QueryClientProvider></TestThemeProvider>)
}

it('未生成图谱时显示明确空状态，不交给图谱解析器报错', async () => {
  mount()
  expect(await screen.findByText('当前运行尚未生成用例图谱')).toBeInTheDocument()
  expect(screen.queryByTestId('relations-content')).not.toBeInTheDocument()
})

it('入队后持续刷新，等待真实产物出现再显示图谱', async () => {
  let submitted = false
  let reads = 0
  vi.mocked(api.getFunctionalCaseGenerateTaskRun).mockImplementation(async () => {
    if (!submitted) return ready
    return ++reads < 2 ? queued : { ...ready, configJson: { caseRelations: relations } }
  })
  vi.mocked(aiTestingApi.generateFunctionalCaseRelationAnalysis).mockImplementation(async () => { submitted = true; return queued })
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '生成图谱' }))
  expect(await screen.findByText('已提交图谱生成')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /图谱生成中/ })).toBeDisabled()
  await waitFor(() => expect(screen.getByTestId('relations-content')).toHaveTextContent('P01'), { timeout: 6000 })
})

it('图谱任务失败时展示失败原因并允许重试', async () => {
  vi.mocked(api.getFunctionalCaseGenerateTaskRun).mockResolvedValue({ ...queued, status: 'failed', errorMessage: '缺少需求分析输入' })
  mount()
  expect(await screen.findByText('图谱生成失败')).toBeInTheDocument()
  expect(screen.getByText('缺少需求分析输入')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重新生成图谱' })).toBeEnabled()
})

it('完整用例尚未审核通过时禁止生成图谱', async () => {
  vi.mocked(api.getFunctionalCaseGenerateTaskRun).mockResolvedValue({ ...ready, reviewStatus: 'pending' })
  mount()
  expect(await screen.findByText('当前运行尚未生成用例图谱')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '生成图谱' })).toBeDisabled()
})
