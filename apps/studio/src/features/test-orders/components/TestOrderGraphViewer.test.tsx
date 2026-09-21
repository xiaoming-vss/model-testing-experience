import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { TestOrderGraphViewer } from './TestOrderGraphViewer'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
// 断言传给编辑器的是哪份 JSON：CodeMirror 在 jsdom 里不渲染正文，这里只看入参。
vi.mock('@/shared/components/JsonEditor/JsonEditor', () => ({
  JsonEditor: ({ value }: { value?: string }) => <pre data-testid="graph-json">{value}</pre>,
}))

const GRAPH_INPUT = {
  requirements: [
    { requirement_id: 'REQ-001', requirement_title: '转换数据', requirement_content: '需求正文' },
  ],
  cases: [
    {
      case_id: 'case-1',
      case_module: '转换数据',
      case_title: '验证转换',
      case_type: '功能测试',
      priority: '1',
      precondition: ['1. 已登录。'],
      test_steps: ['1. 发起转换。'],
      expected_results: ['1. 转换成功。'],
    },
  ],
  case_requirement_links: [{ requirement_id: 'REQ-001', case_ids: ['case-1'] }],
}

const GRAPH_JSON = {
  schema_version: '2.0',
  main_paths: [{ path_id: 'P01', case_ids: ['case-1', 'case-2'] }],
  edges: [
    {
      edge_id: 'E01',
      from_case_id: 'case-1',
      to_case_id: 'case-2',
      relation_type: 'next',
      order: 1,
    },
  ],
}

/** 节点名称取自派发时回显的用例：图谱本身只存 case_id。 */
const RUN_WITH_GRAPH = {
  runId: 'run-1',
  status: 'success',
  resultYaml: JSON.stringify(GRAPH_JSON),
  configJson: {
    graphInput: {
      cases: [
        { case_id: 'case-1', case_title: '验证转换' },
        { case_id: 'case-2', case_title: '验证重试' },
      ],
    },
  },
}

const LLM_CONNECTION = {
  connectionId: 'conn-1',
  provider: 'llm',
  name: 'llm',
  baseUrl: 'https://llm.example/v1',
  authType: 'api_key',
  account: 'me',
  status: 'active',
  hasAccessToken: true,
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function renderViewer(
  client: QueryClient,
  props: Partial<Parameters<typeof TestOrderGraphViewer>[0]> = {},
) {
  // 连接选择弹框内部用 useNavigate，运行时由 AppShell 提供 Router。
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TestOrderGraphViewer
          open
          orderId="order-1"
          projectId="project-1"
          canExecute
          onClose={() => {}}
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('没有运行记录时提示先生成', async () => {
  vi.spyOn(api, 'getTestOrderGraph').mockImplementation(async () => ({ orderId: 'order-1', run: null }))
  const client = makeClient()

  renderViewer(client)

  expect(await screen.findByText('这张测试单还没有生成过图谱')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '生成图谱' })).toBeEnabled()
  client.clear()
})

it('运行中显示进度并禁用重新生成', async () => {
  vi.spyOn(api, 'getTestOrderGraph').mockImplementation(async () => ({
    orderId: 'order-1',
    run: { runId: 'run-1', status: 'running' },
  }))
  const client = makeClient()

  renderViewer(client)

  expect(await screen.findByText('图谱生成中…')).toBeInTheDocument()
  expect(screen.getByText('每 5 秒自动刷新')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重新生成' })).toBeDisabled()
  client.clear()
})

it('成功后默认展示可视化图谱与统计', async () => {
  vi.spyOn(api, 'getTestOrderGraph').mockImplementation(async () => ({
    orderId: 'order-1',
    run: RUN_WITH_GRAPH,
  }))
  const client = makeClient()

  renderViewer(client)

  // 节点名称来自 configJson.graphInput.cases，不是 case_id 本身。
  expect(await screen.findByText('验证转换')).toBeInTheDocument()
  expect(screen.getByText('验证重试')).toBeInTheDocument()
  expect(document.querySelector('.ai-relations-node')).not.toBeNull()
  expect(screen.getByText('2 条用例 · 1 条关联 · 1 条业务主线')).toBeInTheDocument()
  expect(screen.getByText('主线 / 后续')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重新生成' })).toBeEnabled()
  client.clear()
})

it('切到 json 页签展示 resultYaml', async () => {
  vi.spyOn(api, 'getTestOrderGraph').mockImplementation(async () => ({
    orderId: 'order-1',
    run: RUN_WITH_GRAPH,
  }))
  const client = makeClient()

  renderViewer(client)
  await screen.findByText('验证转换')

  // 单行工具条用 Segmented 切换：隐藏的 radio input 不可点击，点可见分段项。
  const bar = document.querySelector('.ai-relations-page-bar') as HTMLElement
  await userEvent.setup().click(within(bar).getByText('json'))

  const json = await screen.findByTestId('graph-json')
  expect(JSON.parse(json.textContent ?? '')).toEqual(GRAPH_JSON)
  client.clear()
})

it('失败时显示运行错误', async () => {
  vi.spyOn(api, 'getTestOrderGraph').mockImplementation(async () => ({
    orderId: 'order-1',
    run: { runId: 'run-1', status: 'failed', errorMessage: '图谱生成失败：invalid_json' },
  }))
  const client = makeClient()

  renderViewer(client)

  expect(await screen.findByText('图谱生成失败：invalid_json')).toBeInTheDocument()
  client.clear()
})

it('生成图谱会先取输入再选连接并派发', async () => {
  vi.spyOn(api, 'getTestOrderGraph').mockImplementation(async () => ({ orderId: 'order-1', run: null }))
  vi.spyOn(api, 'getTestOrderGraphInput').mockImplementation(async () => GRAPH_INPUT)
  vi.spyOn(api, 'getLlmConnections').mockImplementation(async () => listResponse([LLM_CONNECTION]))
  const dispatch = vi
    .spyOn(api, 'dispatchTestOrderGraph')
    .mockImplementation(async () => ({ runId: 'run-1', status: 'pending' }))
  const client = makeClient()

  renderViewer(client)
  await userEvent.setup().click(await screen.findByRole('button', { name: '生成图谱' }))

  await waitFor(() => expect(dispatch).toHaveBeenCalledTimes(1))
  expect(dispatch.mock.calls[0][0]).toBe('order-1')
  // 图谱输入必须原样回传：字段名是 skill 的 snake_case 契约，不能被改写。
  expect(dispatch.mock.calls[0][1]).toEqual({ graphInput: GRAPH_INPUT, connectionId: 'conn-1' })
  client.clear()
})

it('无执行权限时不显示生成入口', async () => {
  vi.spyOn(api, 'getTestOrderGraph').mockImplementation(async () => ({ orderId: 'order-1', run: null }))
  const client = makeClient()

  renderViewer(client, { canExecute: false })

  expect(await screen.findByText('这张测试单还没有生成过图谱')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '生成图谱' })).toBeNull()
  client.clear()
})
