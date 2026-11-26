import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { seedOwnerProject } from '@/test/projectAccess'
import { listResponse } from '@/test/listResponse'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import type { PerfRun, PerfSuite } from '../types'
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

function mockRunOptions() {
  vi.spyOn(api, 'listMonitoringConnections').mockResolvedValue(listResponse([{
    connectionId: 'monitoring-1',
    projectId: 'project-1',
    name: 'Prometheus',
    remoteWriteUrl: 'http://prom.local/api/v1/write',
    remoteWriteAuthType: 'none',
    hasRemoteWriteCredentials: false,
    enabled: true,
  }]))
  vi.spyOn(api, 'getSprints').mockResolvedValue(listResponse([]))
}

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/performance/suites/suite-1']}>
        <Routes>
          <Route path="/performance/suites/:suiteId" element={<PerformanceSuiteDetailPage />} />
          <Route path="/performance/runs" element={<div>运行记录占位</div>} />
          <Route path="/performance/case-runs/:runId" element={<div>单用例运行详情占位</div>} />
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
  expect(screen.queryByRole('button', { name: /编辑信息/ })).not.toBeInTheDocument()
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

it('删除性能用例需要二次确认并从测试集中移除', async () => {
  vi.spyOn(api, 'getPerfSuite')
    .mockResolvedValueOnce(suite)
    .mockResolvedValue({ ...suite, cases: [], caseCount: 0 })
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const deleteCase = vi.spyOn(api, 'deletePerfCase').mockResolvedValue({})
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByLabelText('用例名称')
  await userEvent.click(screen.getByRole('button', { name: '删除用例 登录下单' }))
  expect(await screen.findByText('确认删除该用例？')).toBeInTheDocument()
  expect(deleteCase).not.toHaveBeenCalled()

  await userEvent.click(screen.getByRole('button', { name: /^删\s*除$/ }))
  await waitFor(() => expect(deleteCase).toHaveBeenCalledWith('case-1'))
  await waitFor(() => expect(screen.queryByText('登录下单')).not.toBeInTheDocument())
  client.clear()
})

it('只有当前用例显示删除入口', async () => {
  const secondCase = { ...suite.cases[0], caseId: 'case-2', name: '查询订单', orderNo: 2 }
  vi.spyOn(api, 'getPerfSuite').mockResolvedValue({ ...suite, cases: [...suite.cases, secondCase], caseCount: 2 })
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  expect(await screen.findByRole('button', { name: '删除用例 登录下单' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '删除用例 查询订单' })).not.toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: /^2\s*查询订单/ }))
  expect(await screen.findByRole('button', { name: '删除用例 查询订单' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '删除用例 登录下单' })).not.toBeInTheDocument()
  client.clear()
})

it('失效用例在树中标记，状态胶囊只显示失效，运行弹窗排除失效用例', async () => {
  const secondCase = { ...suite.cases[0], caseId: 'case-2', name: '查询订单', orderNo: 2 }
  vi.spyOn(api, 'getPerfSuite').mockResolvedValue({
    ...suite,
    cases: [{ ...suite.cases[0], invalidatedAt: '2026-11-22T02:30:00Z' }, secondCase],
    caseCount: 2,
  })
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  expect(await screen.findByText('2 个用例 · 1 已失效')).toBeInTheDocument()
  expect(screen.getByText(/已失效/, { selector: '.tp-tone-tag' })).toBeInTheDocument()

  const statusChips = () =>
    [...document.querySelectorAll<HTMLButtonElement>('.tp-chip')]
  await userEvent.click(statusChips().find((chip) => chip.textContent === '已失效')!)
  await waitFor(() => expect(screen.queryByText('查询订单')).toBeNull())
  expect(screen.getByText('登录下单')).toBeInTheDocument()

  await userEvent.click(statusChips().find((chip) => chip.textContent === '全部')!)
  await userEvent.click(screen.getByRole('button', { name: '运行测试集' }))

  expect(await screen.findByText(/已排除 1 条失效用例/)).toBeInTheDocument()
  const modal = document.querySelector('.ant-modal') as HTMLElement
  expect(modal).toHaveTextContent('1 条有效用例')
  expect(within(modal).getByText('查询订单')).toBeInTheDocument()
  expect(within(modal).queryByText('登录下单')).toBeNull()
  client.clear()
})

it('从「用例状态」弹窗批量标记失效', async () => {
  vi.spyOn(api, 'getPerfSuite').mockResolvedValue(suite)
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const batch = vi
    .spyOn(api, 'batchInvalidatePerfCases')
    .mockResolvedValue({ caseIds: ['case-1'], updatedCount: 1 })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByLabelText('用例名称')
  await userEvent.click(screen.getByRole('button', { name: '用例状态' }))

  const checkboxes = [...document.querySelectorAll<HTMLInputElement>('.ant-modal input[type="checkbox"]')]
  await userEvent.click(checkboxes[1])
  await userEvent.click(screen.getByRole('button', { name: '标记失效' }))

  await waitFor(() =>
    expect(batch).toHaveBeenCalledWith('project-1', ['case-1'], true),
  )
  client.clear()
})

it('选中用例提供运行与运行记录入口，失效时禁用运行', async () => {
  vi.spyOn(api, 'getPerfSuite').mockResolvedValue({
    ...suite,
    cases: [{ ...suite.cases[0], invalidatedAt: '2026-11-22T02:30:00Z' }],
  })
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  expect(await screen.findByRole('button', { name: '运行用例 登录下单' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '查看用例 登录下单 的运行记录' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '删除用例 登录下单' })).toBeInTheDocument()
  client.clear()
})

it('运行记录入口按当前用例跳转', async () => {
  vi.spyOn(api, 'getPerfSuite').mockResolvedValue(suite)
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByLabelText('用例名称')
  await userEvent.click(screen.getByRole('button', { name: '查看用例 登录下单 的运行记录' }))

  expect(await screen.findByText('运行记录占位')).toBeInTheDocument()
  client.clear()
})

it('单用例运行提交环境与监控接入并进入运行详情', async () => {
  vi.spyOn(api, 'getPerfSuite').mockResolvedValue(suite)
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  mockRunOptions()
  const startRun = vi.spyOn(api, 'startPerfRun').mockResolvedValue({ runId: 'case-run-1' } as unknown as PerfRun)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByLabelText('用例名称')
  await userEvent.click(screen.getByRole('button', { name: '运行用例 登录下单' }))

  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText('运行用例')).toBeInTheDocument()
  const submit = within(dialog).getByRole('button', { name: '开始运行' })
  await waitFor(() => expect(submit).toBeEnabled())
  await userEvent.click(submit)

  await waitFor(() => expect(startRun).toHaveBeenCalledWith('case-1', {
    environmentId: 'env-1',
    monitoringConnectionId: 'monitoring-1',
  }))
  expect(await screen.findByText('单用例运行详情占位')).toBeInTheDocument()
  client.clear()
})

it('有未保存修改时不发起单用例运行', async () => {
  vi.spyOn(api, 'getPerfSuite').mockResolvedValue(suite)
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(listResponse([environment]))
  mockRunOptions()
  const startRun = vi.spyOn(api, 'startPerfRun')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  const nameInput = await screen.findByLabelText('用例名称')
  await userEvent.clear(nameInput)
  await userEvent.type(nameInput, '登录下单改')
  await userEvent.click(screen.getByRole('button', { name: '运行用例 登录下单' }))

  expect(message.warning).toHaveBeenCalledWith('当前用例有未保存修改，请先保存后再运行')
  expect(startRun).not.toHaveBeenCalled()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  client.clear()
})
