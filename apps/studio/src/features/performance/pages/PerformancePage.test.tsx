import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { seedOwnerProject } from '@/test/projectAccess'
import { listResponse } from '@/test/listResponse'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import type { PerfSuiteSummary } from '../types'
import { PerformancePage } from './PerformancePage'

vi.mock('@/shared/utils/feedback', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const suite: PerfSuiteSummary = {
  suiteId: 'suite-1',
  projectId: 'project-1',
  name: '核心链路压测',
  description: '登录与下单链路',
  caseCount: 3,
  stepCount: 6,
  dataFileCount: 1,
  loadModels: ['vus'],
  lastRunStatus: 'completed',
  lastRunOutcome: 'passed',
  updatedAt: '2026-09-27T10:00:00Z',
}

const secondSuite: PerfSuiteSummary = {
  ...suite,
  suiteId: 'suite-2',
  name: '登录接口基线',
  description: '登录接口单独压测',
  lastRunStatus: '',
  lastRunOutcome: '',
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
      <MemoryRouter initialEntries={['/testing?tab=perf']}>
        <Routes>
          <Route path="/testing" element={<PerformancePage />} />
          <Route path="/performance/runs" element={<div>运行记录占位</div>} />
          <Route path="/performance/suites/:suiteId" element={<div>测试集详情占位</div>} />
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

it('渲染性能测试集清单和环境', async () => {
  vi.spyOn(api, 'listPerfSuites').mockResolvedValue(listResponse([suite]))
  const getEnvironments = vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  expect(await screen.findByText('核心链路压测')).toBeInTheDocument()
  expect(screen.getByText('3 个')).toBeInTheDocument()
  expect(screen.getByText('6 个')).toBeInTheDocument()
  expect(screen.getByText('已完成')).toBeInTheDocument()
  expect(screen.getByText('达标')).toBeInTheDocument()
  expect(getEnvironments).toHaveBeenCalledWith('project-1', 'perf')
  client.clear()
})

it('按名称或描述过滤测试集', async () => {
  vi.spyOn(api, 'listPerfSuites').mockResolvedValue(listResponse([suite, secondSuite]))
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByText('核心链路压测')
  await userEvent.type(screen.getByPlaceholderText('搜索测试集名称 / 描述'), '基线')

  expect(await screen.findByText('登录接口基线')).toBeInTheDocument()
  expect(screen.queryByText('核心链路压测')).not.toBeInTheDocument()
  client.clear()
})

it('打开新建性能测试集抽屉', async () => {
  vi.spyOn(api, 'listPerfSuites').mockResolvedValue(listResponse([suite]))
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByText('核心链路压测')
  await userEvent.click(screen.getByRole('button', { name: '新建测试集' }))

  expect(await screen.findByText('新建性能测试集')).toBeInTheDocument()
  expect(screen.getByLabelText('测试集名称')).toBeInTheDocument()
  client.clear()
})
