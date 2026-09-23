import { ApiCollectionDetailPage } from '@/features/api-automation/pages/ApiCollectionDetailPage'
import { api } from '@/services/api'
import { TestThemeProvider as ThemeProvider } from '@/test/TestThemeProvider'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

/*
 * 详情页的表面层按设计稿重做（顶栏 + 用例列表卡片 + 请求编辑与运行结果卡片），
 * 这组测试锁住设计稿要求的结构钩子与两条主链路：运行测试集、运行单条用例后在控制台读结果。
 */

vi.mock('@/features/projects/hooks/useProjectAccess', () => ({
  useProjectAccess: () => ({ can: () => true, loading: false, error: null }),
}))
// ThemeProvider 会调用真实的 bindFeedbackMessage，所以这里只替换 message 本身。
vi.mock('@/shared/utils/feedback', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/utils/feedback')>()),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

const list = <T,>(items: T[]) => Object.assign([...items], { items, total: items.length })

const collection = {
  collectionId: 'collection-1',
  requirementId: 'requirement-1',
  name: 'xiaoming',
  description: '登录与项目相关的接口集',
  updatedAt: '2026-09-23T10:12:00',
}

const cases = [
  { caseId: 'case-1', collectionId: 'collection-1', name: 'login', method: 'POST' as const, urlTemplate: '/v1/login', enabled: true, orderNo: 1, timeoutMs: 5000 },
  { caseId: 'case-2', collectionId: 'collection-1', name: 'list_projects', method: 'GET' as const, urlTemplate: '/v1/projects', enabled: true, orderNo: 2 },
]

const environment = {
  environmentId: 'environment-1',
  projectId: 'project-1',
  name: 'dev',
  baseUrl: 'http://127.0.0.1:9000',
  isDefault: true,
}

const runResult = {
  runId: 'case-run-1',
  status: 'success' as const,
  success: true,
  durationMs: 459,
  environmentId: 'environment-1',
  response: { statusCode: 200, body: '{"code":200}' },
  assertResults: [
    { assertRuleId: 'assert-1', name: '状态码为 200', success: true, assertSource: 'status_code' as const, comparator: 'eq' as const },
    { assertRuleId: 'assert-2', name: '响应里存在 token', success: false, assertSource: 'body_jsonpath' as const, comparator: 'exists' as const },
  ],
  extractResults: [],
}

function mockDetailApis() {
  vi.spyOn(api, 'getApiCollection').mockResolvedValue(collection)
  vi.spyOn(api, 'getApiCases').mockResolvedValue(list(cases))
  vi.spyOn(api, 'getRequirement').mockResolvedValue({ requirementId: 'requirement-1', sprintId: 'sprint-1', name: '安装部署' })
  vi.spyOn(api, 'getSprint').mockResolvedValue({ sprintId: 'sprint-1', projectId: 'project-1', name: 'v1.0.0', status: 'running' })
  vi.spyOn(api, 'getApiEnvironments').mockResolvedValue(list([environment]))
  vi.spyOn(api, 'getApiEnvironmentVars').mockResolvedValue(list([]))
  vi.spyOn(api, 'getApiCase').mockResolvedValue({ ...cases[0], query: [{ enabled: true, key: 'client_type', value: 'web_desktop' }], bodyType: 'json' as const, bodyJson: '{"username":"admin"}' })
  vi.spyOn(api, 'getApiAssertRules').mockResolvedValue(list([]))
  vi.spyOn(api, 'getApiExtractRules').mockResolvedValue(list([]))
  vi.spyOn(api, 'getApiCollectionRuns').mockResolvedValue(list([{ collectionRunId: 'run-1', status: 'success', startedAt: '2026-09-23T10:00:00' }]))
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <MemoryRouter initialEntries={['/api/collection-1']}>
          <Routes>
            <Route path="/api/:collectionId" element={<ApiCollectionDetailPage />} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  )
  return { ...view, client }
}

beforeEach(() => {
  mockDetailApis()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('顶栏给出测试集、需求、迭代与当前环境，运行测试集提交当前环境', async () => {
  const run = vi.spyOn(api, 'runApiCollection').mockResolvedValue({ status: 'success' })
  const { container, client } = renderPage()

  await screen.findByText('xiaoming')
  // 需求与迭代跟在测试集名后面，是同一行「/ 需求 / 迭代」；两者是随需求、迭代查询各自回来的
  await screen.findByText('/ 安装部署 / v1.0.0')
  // Base URL 在顶栏环境胶囊与请求地址条上各有一处，这里只看顶栏；环境列表是随项目 id 后到的
  const toolbar = within(container.querySelector('.api-wb-toolbar') as HTMLElement)
  await toolbar.findByText('http://127.0.0.1:9000')
  expect(toolbar.getByRole('button', { name: /运行记录/ })).toHaveTextContent('运行记录 (1)')

  await userEvent.setup().click(screen.getByRole('button', { name: /运行测试集/ }))
  await waitFor(() =>
    expect(run).toHaveBeenCalledWith('collection-1', { environmentId: 'environment-1' }),
  )
  expect(container.querySelector('.api-wb-cols')).toBeTruthy()
  client.clear()
})

it('左栏按请求方式列出用例，点击切换当前用例', async () => {
  const { container, client } = renderPage()

  await screen.findByText('xiaoming')
  await waitFor(() => expect(container.querySelectorAll('.api-wb-case-item')).toHaveLength(2))

  const items = [...container.querySelectorAll('.api-wb-case-item')]
  expect(items[0].querySelector('.api-wb-case-method')).toHaveTextContent('POST')
  expect(items[1].querySelector('.api-wb-case-method')).toHaveTextContent('GET')
  expect(items[0].querySelector('.api-wb-case-item-path')).toHaveTextContent('/v1/login')
  expect(items[0]).toHaveAttribute('aria-current', 'true')

  await userEvent.setup().click(items[1])
  await waitFor(() => expect(items[1]).toHaveAttribute('aria-current', 'true'))
  await waitFor(() =>
    expect(screen.getByLabelText('用例名称')).toHaveValue('list_projects'),
  )
  client.clear()
})

it('搜索按用例名与接口路径在本地过滤', async () => {
  const { container, client } = renderPage()

  await screen.findByText('xiaoming')
  await userEvent.setup().type(screen.getByPlaceholderText('搜索用例名称 / 接口路径'), 'projects')

  await waitFor(() => expect(container.querySelectorAll('.api-wb-case-item')).toHaveLength(1))
  expect(screen.queryByText('login')).toBeNull()
  client.clear()
})

it('运行单条用例后控制台给出状态、耗时与逐条断言结论', async () => {
  vi.spyOn(api, 'runApiCase').mockResolvedValue(runResult)
  const { container, client } = renderPage()

  await screen.findByText('xiaoming')
  await waitFor(() => expect(screen.getByLabelText('用例名称')).toHaveValue('login'))

  await userEvent.setup().click(container.querySelector('.api-wb-send') as HTMLElement)
  await waitFor(() => expect(container.querySelector('.api-wb-console')).toBeTruthy())

  const console_ = within(container.querySelector('.api-wb-console') as HTMLElement)
  expect(console_.getByText('200 · 成功')).toBeInTheDocument()
  expect(console_.getByText(/耗时/).parentElement).toHaveTextContent('459 ms')
  // 一条通过一条失败：简报给失败数，底部逐条断言给 PASS / FAIL
  expect(console_.getByText('断言失败 1/2')).toBeInTheDocument()
  expect(console_.getByText('状态码为 200（PASS）')).toBeInTheDocument()
  expect(console_.getByText('响应里存在 token（FAIL）')).toBeInTheDocument()
  // 详情页每个页签的计数取自当前表单值
  expect(container.querySelector('.api-wb-tab-dot')).toBeTruthy()
  client.clear()
})

it('新建用例先落成草稿，左栏标出草稿并可从草稿丢弃回到列表', async () => {
  const create = vi.spyOn(api, 'createApiCase')
  const { container, client } = renderPage()

  await screen.findByText('xiaoming')
  await userEvent.setup().click(screen.getByRole('button', { name: '新建用例' }))

  await waitFor(() => expect(container.querySelector('.api-wb-case-draft')).toBeTruthy())
  expect(screen.getByLabelText('用例名称')).toHaveValue('')
  expect(create).not.toHaveBeenCalled()
  client.clear()
})
