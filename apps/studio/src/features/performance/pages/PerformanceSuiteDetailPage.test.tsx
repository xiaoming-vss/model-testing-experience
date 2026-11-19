import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { seedOwnerProject } from '@/test/projectAccess'
import { listResponse } from '@/test/listResponse'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import type { PerfSuite } from '../types'
import { buildDefaultPerfYaml } from '../utils/perf'
import { PerformanceSuiteDetailPage } from './PerformanceSuiteDetailPage'

vi.mock('@/shared/utils/feedback', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const suite: PerfSuite = {
  suiteId: 'suite-1',
  projectId: 'project-1',
  name: '订单压测',
  description: '核心链路',
  caseCount: 1,
  stepCount: 1,
  dataFileCount: 0,
  loadModels: ['vus'],
  lastRunStatus: '',
  lastRunOutcome: '',
  createdBy: 'user-1',
  createdAt: '2026-09-27T09:00:00Z',
  updatedAt: '2026-09-27T10:00:00Z',
  cases: [{
    caseId: 'case-1',
    projectId: 'project-1',
    suiteId: 'suite-1',
    orderNo: 1,
    name: '登录下单',
    version: 1,
    dataFiles: [],
    yaml: buildDefaultPerfYaml('登录下单'),
    createdAt: '2026-09-27T09:00:00Z',
    updatedAt: '2026-09-27T10:00:00Z',
  }],
}

const environment = {
  environmentId: 'env-1',
  projectId: 'project-1',
  kind: 'perf' as const,
  name: '性能环境',
  baseUrl: 'http://perf.local',
  isDefault: true,
}

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/performance/suites/suite-1']}>
        <Routes>
          <Route path="/performance/suites/:suiteId" element={<PerformanceSuiteDetailPage />} />
          <Route path="/testing" element={<div>性能测试占位</div>} />
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

it('渲染性能测试集和当前用例表单', async () => {
  const getSuite = vi.spyOn(api, 'getPerfSuite').mockResolvedValue(suite)
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  expect(await screen.findByRole('heading', { name: '订单压测' })).toBeInTheDocument()
  expect(screen.getByText('1 个用例')).toBeInTheDocument()
  expect(screen.getByText(/1 个 VU，持续 10s/)).toBeInTheDocument()
  expect(screen.getByLabelText('用例名称')).toHaveValue('登录下单')
  expect(getSuite).toHaveBeenCalledWith('suite-1')
  client.clear()
})

it('切换运行契约 YAML 视图', async () => {
  vi.spyOn(api, 'getPerfSuite').mockResolvedValue(suite)
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByLabelText('用例名称')
  await userEvent.click(screen.getByRole('radio', { name: 'YAML' }).closest('label')!)

  expect(await screen.findByText('运行契约')).toBeInTheDocument()
  expect(screen.getByText(/只读，用于排查与 Worker 契约对照/)).toBeInTheDocument()
  client.clear()
})

it('打开新增性能用例弹窗', async () => {
  vi.spyOn(api, 'getPerfSuite').mockResolvedValue(suite)
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByLabelText('用例名称')
  await userEvent.click(screen.getByRole('button', { name: '新增用例' }))

  expect(await screen.findByText('新增性能用例')).toBeInTheDocument()
  expect(screen.getByPlaceholderText('例如：登录后查询订单')).toBeInTheDocument()
  client.clear()
})
