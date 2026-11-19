import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { seedOwnerProject } from '@/test/projectAccess'
import { listResponse } from '@/test/listResponse'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import type { PerfSuiteRunSummary, PerfSuiteSummary } from '../types'
import { PerformanceRunsPage } from './PerformanceRunsPage'

vi.mock('@/shared/utils/feedback', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const suite: PerfSuiteSummary = {
  suiteId: 'suite-1',
  projectId: 'project-1',
  name: '核心链路压测',
  description: '登录与下单链路',
  caseCount: 4,
  stepCount: 8,
  dataFileCount: 0,
  loadModels: ['vus'],
  lastRunStatus: 'completed',
  lastRunOutcome: 'passed',
}

const run: PerfSuiteRunSummary = {
  suiteRunId: 'run-1',
  suiteId: 'suite-1',
  projectId: 'project-1',
  suiteName: '核心链路压测',
  environmentId: 'env-1',
  environmentName: '性能环境',
  monitoringConnectionId: 'monitoring-1',
  monitoringConnectionName: 'Prometheus',
  triggerUserId: 'user-1',
  triggerType: 'manual',
  status: 'completed',
  outcome: 'passed',
  totalCount: 4,
  completedCount: 3,
  failedCount: 0,
  skippedCount: 1,
  errorMessage: '',
  startedAt: '2026-09-27T10:00:00Z',
  durationMs: 65000,
  createdAt: '2026-09-27T09:59:00Z',
}

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/performance/runs']}>
        <Routes>
          <Route path="/performance/runs" element={<PerformanceRunsPage />} />
          <Route path="/performance/runs/:runId" element={<div>运行详情占位</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useWorkbenchStore.setState({ activeProjectId: 'project-1' })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('渲染运行记录、进度和结果', async () => {
  vi.spyOn(api, 'listPerfSuites').mockResolvedValue(listResponse([suite]))
  const getRuns = vi.spyOn(api, 'listPerfSuiteRuns').mockResolvedValue(listResponse([run], 1))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  expect(await screen.findByText('核心链路压测')).toBeInTheDocument()
  expect(screen.getByText('4/4')).toBeInTheDocument()
  expect(screen.getByText('已完成')).toBeInTheDocument()
  expect(screen.getByText('达标')).toBeInTheDocument()
  expect(screen.getByText('1 分 5 秒')).toBeInTheDocument()
  expect(getRuns).toHaveBeenCalledWith('project-1', expect.objectContaining({ page: 1, pageSize: 20 }))
  client.clear()
})

it('刷新运行记录并重新取数', async () => {
  vi.spyOn(api, 'listPerfSuites').mockResolvedValue(listResponse([suite]))
  const getRuns = vi.spyOn(api, 'listPerfSuiteRuns').mockResolvedValue(listResponse([run], 1))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByText('核心链路压测')
  await userEvent.click(screen.getByRole('button', { name: /刷新/ }))
  await waitFor(() => expect(getRuns).toHaveBeenCalledTimes(2))
  client.clear()
})

it('从运行记录进入运行详情', async () => {
  vi.spyOn(api, 'listPerfSuites').mockResolvedValue(listResponse([suite]))
  vi.spyOn(api, 'listPerfSuiteRuns').mockResolvedValue(listResponse([run], 1))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByText('核心链路压测')
  await userEvent.click(screen.getByRole('button', { name: /查\s*看/ }))

  expect(await screen.findByText('运行详情占位')).toBeInTheDocument()
  client.clear()
})
