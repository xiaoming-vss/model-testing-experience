import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { generationCandidatesApi } from '../api/generationCandidates.api'
import type { CandidateRelationsView } from '../api/generationCandidates.contract'
import { FunctionalCaseRelationsModal } from './FunctionalCaseRelationsModal'

vi.mock('../api/generationCandidates.api', () => ({ generationCandidatesApi: { relations: vi.fn(), runRelations: vi.fn() } }))
vi.mock('@/domain/projects/components/ProjectAccessScope', () => ({ ProjectAccessScope: ({ children }: { children: React.ReactNode }) => children }))
vi.mock('./FunctionalCaseRelationsGraph', () => ({ FunctionalCaseRelationsGraph: ({ content }: { content: string }) => <div data-testid="relations-content">{content}</div> }))

let client: QueryClient
let inspector: HTMLDivElement
const relations = { schema_version: '2.0', main_paths: [{ path_id: 'P01', case_ids: ['c1', 'c2'] }], edges: [] }
const ready: CandidateRelationsView = { candidateId: 'candidate', snapshotId: 'snapshot', currentToken: 'token', sourceAttemptId: 'run', resultYaml: '[]', status: 'success', attemptId: null, errorMessage: '', caseRelations: relations }
const queued: CandidateRelationsView = { ...ready, status: 'running', caseRelations: null }
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  inspector = document.createElement('div')
  document.body.append(inspector)
  vi.mocked(generationCandidatesApi.relations).mockResolvedValue(ready)
  vi.mocked(generationCandidatesApi.runRelations).mockResolvedValue({ attemptId: 'graph', replayed: false })
})
afterEach(() => { cleanup(); inspector.remove(); client.clear(); vi.clearAllMocks() })
function mount() {
  render(<TestThemeProvider><QueryClientProvider client={client}>
    <FunctionalCaseRelationsModal open projectId="project" candidate={{ requirementId: 'req', currentToken: 'token' }} inspectorContainer={inspector} inspectorActionContainer={inspector} onClose={() => {}} chooseConnection={async () => 'llm'} />
  </QueryClientProvider></TestThemeProvider>)
}

it('入队后持续刷新，等待真实产物出现再显示图谱', async () => {
  let submitted = false
  vi.mocked(generationCandidatesApi.relations).mockImplementation(async () => {
    if (!submitted) return { ...ready, caseRelations: null }
    return { ...ready, caseRelations: relations }
  })
  vi.mocked(generationCandidatesApi.runRelations).mockImplementation(async () => { submitted = true; return { attemptId: 'graph', replayed: false } })
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '生成图谱' }))
  expect(await screen.findByText('已提交图谱生成')).toBeInTheDocument()
  await waitFor(() => expect(generationCandidatesApi.relations).toHaveBeenCalledTimes(2))
  expect(await screen.findByTestId('relations-content')).toHaveTextContent('P01')
})

it('图谱任务失败时展示失败原因并允许重试', async () => {
  vi.mocked(generationCandidatesApi.relations).mockResolvedValue({ ...queued, status: 'failed', errorMessage: '缺少需求分析输入' })
  mount()
  expect(await screen.findByText('图谱生成失败')).toBeInTheDocument()
  expect(screen.getByText('缺少需求分析输入')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重新生成图谱' })).toBeEnabled()
})

it('图谱仍在生成时禁用重复提交', async () => {
  vi.mocked(generationCandidatesApi.relations).mockResolvedValue(queued)
  mount()
  expect(await screen.findByRole('button', { name: /图谱生成中/ })).toBeDisabled()
})

it('以当前完整用例令牌提交生成请求', async () => {
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '生成图谱' }))
  await waitFor(() => expect(generationCandidatesApi.runRelations).toHaveBeenCalledWith('req', expect.objectContaining({ currentToken: 'token', connectionId: 'llm', requestId: expect.any(String) })))
  expect(await screen.findByTestId('relations-content')).toHaveTextContent('P01')
})
