import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import type { FunctionalCaseGenerateTaskRun } from '../types'
import { FunctionalCaseRelationsViewer } from './FunctionalCaseRelationsViewer'

vi.mock('@/services/api', () => ({
  api: {
    getFunctionalCaseGenerateTask: vi.fn(),
    getFunctionalCaseGenerateTaskRun: vi.fn(),
  },
}))
vi.mock('@/domain/projects/components/ProjectAccessScope', () => ({
  ProjectAccessScope: ({ children }: { children: React.ReactNode }) => children,
}))
vi.mock('@/shared/components/JsonEditor/JsonEditor', () => ({
  JsonEditor: ({ value }: { value?: string }) => (
    <textarea aria-label="图谱 JSON" value={value} readOnly />
  ),
}))
vi.mock('./FunctionalCaseRelationsGraph', () => ({
  FunctionalCaseRelationsGraph: ({ content }: { content: string }) => (
    <div data-testid="relations-content">{content}</div>
  ),
}))

const relations = {
  schema_version: '2.0',
  main_paths: [{ path_id: 'P01', case_ids: ['c1', 'c2'] }],
  edges: [{ edge_id: 'E01', from_case_id: 'c1', to_case_id: 'c2', relation_type: 'next', order: 1 }],
}

const readyRun: FunctionalCaseGenerateTaskRun = {
  runId: 'run-1',
  taskId: 'task-1',
  status: 'success',
  currentStage: 'completed',
  reviewStatus: 'approved',
  configJson: { caseRelations: relations },
  resultYaml: '[]',
  importStatus: 'pending',
  importedTargets: [],
  importedAt: '',
}

let client: QueryClient

beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  vi.mocked(api.getFunctionalCaseGenerateTask).mockResolvedValue({
    taskId: 'task-1',
    name: '登录需求',
    projectId: 'project-1',
    instruction: '',
  })
  vi.mocked(api.getFunctionalCaseGenerateTaskRun).mockResolvedValue(readyRun)
})

afterEach(() => {
  cleanup()
  client.clear()
  vi.clearAllMocks()
})

function mount() {
  render(
    <QueryClientProvider client={client}>
      <FunctionalCaseRelationsViewer taskId="task-1" runId="run-1" />
    </QueryClientProvider>
  )
}

it('渲染层级图谱，并可切换到完整 JSON 查看', async () => {
  mount()

  expect(await screen.findByTestId('relations-content')).toHaveTextContent('P01')
  expect(screen.getByText(/条业务主线/)).toBeInTheDocument()

  await userEvent
    .setup()
    .click(screen.getByRole('radio', { name: 'JSON' }).closest('label')!)

  const editor = await screen.findByRole('textbox', { name: '图谱 JSON' })
  expect((editor as HTMLTextAreaElement).value).toContain('"schema_version": "2.0"')
})

it('尚未生成图谱时显示空状态，不交给图谱解析器报错', async () => {
  vi.mocked(api.getFunctionalCaseGenerateTaskRun).mockResolvedValue({
    ...readyRun,
    configJson: {},
  })
  mount()

  expect(await screen.findByText('当前运行尚未生成用例图谱')).toBeInTheDocument()
  expect(screen.queryByTestId('relations-content')).not.toBeInTheDocument()
})

it('图谱生成失败时展示失败原因', async () => {
  vi.mocked(api.getFunctionalCaseGenerateTaskRun).mockResolvedValue({
    ...readyRun,
    status: 'failed',
    currentStage: 'relation_analysis',
    errorMessage: '缺少需求分析输入',
  })
  mount()

  expect(await screen.findByText('图谱生成失败')).toBeInTheDocument()
  expect(screen.getByText('缺少需求分析输入')).toBeInTheDocument()
})
