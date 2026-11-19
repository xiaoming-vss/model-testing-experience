import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import type { PerfSuiteRun } from '../types'
import { PerformanceRunDetailPage } from './PerformanceRunDetailPage'

vi.mock('@/shared/utils/feedback', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const run: PerfSuiteRun = {
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
  status: 'running',
  outcome: '',
  totalCount: 1,
  completedCount: 0,
  failedCount: 0,
  skippedCount: 0,
  errorMessage: '',
  startedAt: '2026-09-27T10:00:00Z',
  durationMs: 5000,
  items: [{
    itemId: 'item-1',
    caseId: 'case-1',
    caseName: '登录下单',
    orderNo: 1,
    status: 'running',
    childRunId: 'child-run-1',
    errorMessage: '',
    startedAt: '2026-09-27T10:00:01Z',
    durationMs: 1000,
    summary: {
      metrics: {
        http_reqs: { values: { rate: 12.5 } },
        iterations: { values: { count: 50 } },
        http_req_duration: { values: { 'p(95)': 120.5, 'p(99)': 220 } },
        http_req_failed: { values: { rate: 0.01 } },
      },
    },
    load: { model: 'vus', vus: 10, duration: '30s' },
    logTail: 'iteration complete',
    flags: [],
    k6Version: '2.3.0',
  }],
}

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/performance/runs/run-1']}>
        <Routes>
          <Route path="/performance/runs/:runId" element={<PerformanceRunDetailPage />} />
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

it('渲染运行状态、用例执行数据和 k6 日志', async () => {
  const getRun = vi.spyOn(api, 'getPerfSuiteRun').mockResolvedValue(run)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  expect(await screen.findByText('1. 登录下单')).toBeInTheDocument()
  expect(screen.getAllByText('运行中').length).toBeGreaterThan(0)
  expect(screen.getByText('0/1')).toBeInTheDocument()
  expect(screen.getByText('P95 延迟')).toBeInTheDocument()
  expect(screen.getByText('12.5 req/s')).toBeInTheDocument()
  expect(screen.getByText(/iteration complete/)).toBeInTheDocument()
  expect(screen.getByText('10 VUs · 30s')).toBeInTheDocument()
  expect(getRun).toHaveBeenCalledWith('run-1')
  client.clear()
})

it('运行中可发送停止请求', async () => {
  vi.spyOn(api, 'getPerfSuiteRun').mockResolvedValue(run)
  const stopRun = vi.spyOn(api, 'stopPerfSuiteRun').mockResolvedValue({})
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByText('1. 登录下单')
  await userEvent.click(screen.getByRole('button', { name: /停止运行/ }))

  await waitFor(() => expect(stopRun).toHaveBeenCalledWith('run-1'))
  await waitFor(() => expect(message.success).toHaveBeenCalledWith('停止请求已发送，当前用例结束后将不再启动后续用例'))
  client.clear()
})

it('已结束运行不再显示停止操作', async () => {
  vi.spyOn(api, 'getPerfSuiteRun').mockResolvedValue({
    ...run,
    status: 'completed',
    outcome: 'passed',
    completedCount: 1,
    items: [{ ...run.items[0], status: 'completed' }],
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByText('1. 登录下单')
  expect(screen.getAllByText('已完成').length).toBeGreaterThan(0)
  expect(screen.getByText('达标')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /停止运行/ })).not.toBeInTheDocument()
  expect(screen.getByText('判定说明')).toBeInTheDocument()
  client.clear()
})
