import { StrictMode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { seedOwnerProject } from '@/test/projectAccess'
import extractionText from '@/domain/requirements/fixtures/document-extraction.example.json?raw'
import understandingText from '@/domain/requirements/fixtures/requirement-understanding.example.json?raw'
import { RequirementDesignWorkspace } from './RequirementDesignWorkspace'

const clients: QueryClient[] = []
afterEach(() => {
  cleanup()
  clients.forEach(client => client.clear())
  clients.length = 0
  vi.restoreAllMocks()
})
function mount() {
  const run = { runId: 'run', taskId: 'task', status: 'success', reviewStatus: 'pending',
    currentStage: 'completed', stageStatus: 'completed', hasResult: true, availableArtifacts: ['firstStepOutput'],
    configJson: { firstStepOutput: JSON.parse(extractionText) }, resultYaml: understandingText,
    snapshotJson: { taskType: 'requirement_analysis', workflowVersion: 2 }, workflowVersion: 2 }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const path = new URL(String(input), 'http://localhost').pathname
    let data: unknown = { items: [], total: 0 }
    if (path === '/v1/requirements/req/design') data = { tasks: [{ taskId: 'task', kind: 'requirement_analysis', name: '需求分析', hasSource: true }], runCounts: { requirement_analysis: 1, function: 0, api: 0, ui: 0 }, adoptedUnderstanding: true }
    if (path === '/v1/requirements/req/design/requirement_analysis/runs') data = { items: [run], total: 1 }
    if (path === '/v1/requirement-analysis-tasks/task') data = { taskId: 'task', projectId: 'project-1', name: '需求分析', sourceType: 'text' }
    if (path === '/v1/requirement-analysis-runs/run') data = run
    return new Response(JSON.stringify({ code: 0, message: 'ok', data }), { headers: { 'Content-Type': 'application/json' } })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  seedOwnerProject(client)
  clients.push(client)
  render(<StrictMode><TestThemeProvider><QueryClientProvider client={client}><MemoryRouter>
    <RequirementDesignWorkspace requirementId="req" projectId="project-1" canWrite canExecute canReview />
  </MemoryRouter></QueryClientProvider></TestThemeProvider></StrictMode>)
}

it.each(['材料提取结果', '需求理解记录'])('严格模式下重复查看 %s 后仍能切换类型', async artifact => {
  mount()
  const user = userEvent.setup()
  const open = await screen.findByRole('button', { name: artifact })
  for (let attempt = 0; attempt < 2; attempt++) {
    await user.click(open)
    const modal = await screen.findByRole('dialog')
    await user.click(within(modal).getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.getByRole('tab', { name: '功能测试0' })).toBeEnabled())
  }
  await user.click(screen.getByRole('tab', { name: '功能测试0' }))
  expect(await screen.findByRole('button', { name: '生成用例' })).toBeEnabled()
})

it('产物弹窗宿主不在运行记录旁渲染旧任务页面布局', async () => {
  mount()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '材料提取结果' }))
  await screen.findByRole('dialog')
  const workspace = document.querySelector('.ai-requirement-design')!
  expect(workspace.querySelector('.workbench-page')).toBeNull()
})
