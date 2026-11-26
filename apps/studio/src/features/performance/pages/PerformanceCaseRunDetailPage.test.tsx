import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import type { PerfRun } from '../types'
import { PerformanceCaseRunDetailPage } from './PerformanceCaseRunDetailPage'

vi.mock('@/shared/utils/feedback', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const run: PerfRun = {
  runId: 'case-run-1',
  caseId: 'case-1',
  projectId: 'project-1',
  caseVersion: 3,
  caseName: '登录下单',
  environmentId: 'env-1',
  environmentName: '性能环境',
  monitoringConnectionId: 'monitoring-1',
  monitoringConnectionName: 'Prometheus',
  triggerUserId: 'user-1',
  triggerType: 'manual',
  status: 'running',
  outcome: '',
  flags: [],
  errorMessage: '',
  k6Version: '2.3.0',
  templateVersion: '1.0',
  scriptSha256: 'abc123',
  startedAt: '2026-09-27T10:00:00Z',
  durationMs: 5000,
  createdAt: '2026-09-27T09:59:00Z',
  summary: {
    metrics: {
      http_reqs: { values: { rate: 12.5, count: 120 } },
      iterations: { values: { count: 50 } },
      http_req_duration: { values: { 'p(95)': 120.5, 'p(99)': 220 } },
      http_req_failed: { values: { rate: 0.01 } },
    },
  },
  logTail: 'iteration complete',
  runner: { node: 'runner-1' },
  dataFiles: [{ fileId: 'file-1', filename: 'data.csv', size: 2048, sha256: 'def456' }],
  monitoring: {
    connectionId: 'monitoring-1',
    name: 'Prometheus',
    remoteWriteUrl: 'http://prom.local/api/v1/write',
  },
}

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/performance/case-runs/case-run-1']}>
        <Routes>
          <Route path="/performance/case-runs/:runId" element={<PerformanceCaseRunDetailPage />} />
          <Route path="/performance/runs" element={<div>运行记录占位</div>} />
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

it('渲染单用例运行指标、日志、监控快照和数据文件', async () => {
  const getRun = vi.spyOn(api, 'getPerfRun').mockResolvedValue(run)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  expect(await screen.findByRole('heading', { name: '登录下单' })).toBeInTheDocument()
  expect(screen.getByText('运行中')).toBeInTheDocument()
  expect(screen.getByText('120')).toBeInTheDocument()
  expect(screen.getByText('50')).toBeInTheDocument()
  expect(screen.getByText('12.5 req/s')).toBeInTheDocument()
  expect(screen.getByText('120.5 ms')).toBeInTheDocument()
  expect(screen.getByText(/iteration complete/)).toBeInTheDocument()
  expect(screen.getByText('data.csv')).toBeInTheDocument()
  expect(screen.getByText('http://prom.local/api/v1/write')).toBeInTheDocument()
  expect(screen.getByText('执行器信息')).toBeInTheDocument()
  expect(screen.getByText('user-1')).toBeInTheDocument()
  expect(getRun).toHaveBeenCalledWith('case-run-1')
  client.clear()
})

it('触发人可以停止运行', async () => {
  vi.spyOn(api, 'getPerfRun').mockResolvedValue(run)
  const stopRun = vi.spyOn(api, 'stopPerfRun').mockResolvedValue({})
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByRole('heading', { name: '登录下单' })
  await userEvent.click(screen.getByRole('button', { name: /停止运行/ }))

  await waitFor(() => expect(stopRun).toHaveBeenCalledWith('case-run-1'))
  await waitFor(() => expect(message.success).toHaveBeenCalledWith('停止请求已发送'))
  client.clear()
})

it('已结束运行隐藏停止操作并显示结果', async () => {
  vi.spyOn(api, 'getPerfRun').mockResolvedValue({
    ...run,
    status: 'completed',
    outcome: 'passed',
    durationMs: 30000,
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByRole('heading', { name: '登录下单' })
  expect(screen.getByText('已完成')).toBeInTheDocument()
  expect(screen.getByText('达标')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /停止运行/ })).not.toBeInTheDocument()
  client.clear()
})
