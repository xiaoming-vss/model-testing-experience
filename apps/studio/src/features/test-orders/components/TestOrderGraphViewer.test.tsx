import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
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

beforeEach(() => {
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([]))
})

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

const executionEntry = {
  entryId: 'entry-1', orderId: 'order-1', caseId: 'case-1', caseTitle: '当前执行条目标题',
  status: 'pending', assigneeUserId: '',
  snapshot: { preconditions: ['执行条目的前置条件'], steps: [{ action: '执行条目的操作', expected: '执行条目的预期' }] },
}

it('图谱内判定、补充原因与缺陷同步到执行条目并保持选中节点', async () => {
  let saved = { ...executionEntry, failureReason: '', zentaoBugId: '' }
  vi.spyOn(api, 'getTestOrderGraph').mockResolvedValue({ orderId: 'order-1', run: RUN_WITH_GRAPH })
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async () => listResponse([saved]))
  const update = vi.spyOn(api, 'updateTestOrderEntry').mockImplementation(async (_order, _entry, payload) => {
    saved = { ...saved, ...payload }
    return saved
  })
  const client = makeClient()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  renderViewer(client, { currentUserId: 'user-1' })
  const user = userEvent.setup()
  fireEvent.click(await screen.findByText('验证转换'))
  const panel = await screen.findByRole('region', { name: '图谱用例执行' })
  expect(within(panel).getByText('预期：执行条目的预期')).toBeInTheDocument()
  expect(within(panel).getByText('执行条目的前置条件')).toBeInTheDocument()
  await user.click(within(panel).getByRole('button', { name: '判定该用例为失败' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('order-1', 'entry-1', { status: 'failed' }))
  await waitFor(() => expect(within(panel).getByRole('button', { name: '判定该用例为失败' })).toHaveAttribute('aria-pressed', 'true'))
  await waitFor(() => expect(within(panel).getByLabelText('失败原因')).toBeEnabled())
  expect(screen.getByLabelText('执行状态：失败')).toBeInTheDocument()
  await user.type(within(panel).getByLabelText('失败原因'), '预期结果不符')
  await user.type(within(panel).getByLabelText('禅道缺陷号'), '1234')
  await user.click(within(panel).getByRole('button', { name: '保存补充信息' }))
  await waitFor(() => expect(update).toHaveBeenLastCalledWith('order-1', 'entry-1', { failureReason: '预期结果不符', zentaoBugId: '1234' }))
  await waitFor(() => expect(within(panel).getByText('已保存')).toBeInTheDocument())
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['testOrderEntries', 'order-1'] })
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['testOrder', 'order-1'] })
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['testOrders'] })
  await user.click(within(panel).getByRole('button', { name: '解绑缺陷' }))
  await waitFor(() => expect(update).toHaveBeenLastCalledWith('order-1', 'entry-1', { zentaoBugId: '' }))
  expect(within(panel).getByRole('heading', { name: '当前执行条目标题' })).toBeInTheDocument()
  client.clear()
})

it.each([
  { canExecute: false, isProjectOwner: false, assignee: '', allowed: false },
  { canExecute: true, isProjectOwner: false, assignee: 'another-user', allowed: false },
  { canExecute: true, isProjectOwner: true, assignee: 'another-user', allowed: true },
  { canExecute: true, isProjectOwner: false, assignee: 'user-1', allowed: true },
])('图谱执行遵守权限与分配规则 %j', async ({ canExecute, isProjectOwner, assignee, allowed }) => {
  vi.spyOn(api, 'getTestOrderGraph').mockResolvedValue({ orderId: 'order-1', run: RUN_WITH_GRAPH })
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([{ ...executionEntry, assigneeUserId: assignee }]))
  const client = makeClient()
  renderViewer(client, { canExecute, isProjectOwner, currentUserId: 'user-1' })
  fireEvent.click(await screen.findByText('验证转换'))
  const panel = await screen.findByRole('region', { name: '图谱用例执行' })
  const button = within(panel).getByRole('button', { name: '判定该用例为通过' })
  if (allowed) expect(button).toBeEnabled()
  else expect(button).toBeDisabled()
  client.clear()
})

it('已移除的用例只显示提示，不提供执行操作', async () => {
  vi.spyOn(api, 'getTestOrderGraph').mockResolvedValue({ orderId: 'order-1', run: RUN_WITH_GRAPH })
  const client = makeClient()
  renderViewer(client)
  fireEvent.click(await screen.findByText('验证转换'))
  expect(await screen.findByText(/此用例已不在当前测试单中/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '判定该用例为通过' })).not.toBeInTheDocument()
  client.clear()
})

it('保存失败保留草稿且不伪造执行成功', async () => {
  vi.spyOn(api, 'getTestOrderGraph').mockResolvedValue({ orderId: 'order-1', run: RUN_WITH_GRAPH })
  vi.spyOn(api, 'getTestOrderEntries').mockResolvedValue(listResponse([{ ...executionEntry, status: 'failed' }]))
  vi.spyOn(api, 'updateTestOrderEntry').mockRejectedValue(new Error('保存被拒绝'))
  const client = makeClient()
  renderViewer(client)
  const user = userEvent.setup()
  fireEvent.click(await screen.findByText('验证转换'))
  const panel = await screen.findByRole('region', { name: '图谱用例执行' })
  await user.type(within(panel).getByLabelText('失败原因'), '保留原因')
  await user.click(within(panel).getByRole('button', { name: '保存补充信息' }))
  expect(await within(panel).findByText('保存失败，请重试')).toBeInTheDocument()
  expect(within(panel).getByLabelText('失败原因')).toHaveValue('保留原因')
  expect(within(panel).getByRole('button', { name: '判定该用例为失败' })).toHaveAttribute('aria-pressed', 'true')
  client.clear()
})

it.each(['passed', 'blocked', 'skipped'] as const)('图谱支持判定为 %s', async (status) => {
  let saved = { ...executionEntry }
  vi.spyOn(api, 'getTestOrderGraph').mockResolvedValue({ orderId: 'order-1', run: RUN_WITH_GRAPH })
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async () => listResponse([saved]))
  const update = vi.spyOn(api, 'updateTestOrderEntry').mockImplementation(async (_order, _entry, payload) => {
    saved = { ...saved, ...payload }
    return saved
  })
  const client = makeClient()
  renderViewer(client)
  fireEvent.click(await screen.findByText('验证转换'))
  const panel = await screen.findByRole('region', { name: '图谱用例执行' })
  const labels = { passed: '通过', blocked: '阻塞', skipped: '跳过' }
  await userEvent.setup().click(within(panel).getByRole('button', { name: `判定该用例为${labels[status]}` }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('order-1', 'entry-1', { status }))
  await waitFor(() => expect(screen.getByLabelText(`执行状态：${labels[status]}`)).toBeInTheDocument())
  if (status === 'blocked') expect(within(panel).getByLabelText('阻塞原因')).toBeInTheDocument()
  client.clear()
})

it('保存途中切换卡片不会将响应应用到另一条用例', async () => {
  let entries = [executionEntry, { ...executionEntry, entryId: 'entry-2', caseId: 'case-2', caseTitle: '第二条执行用例' }]
  vi.spyOn(api, 'getTestOrderGraph').mockResolvedValue({ orderId: 'order-1', run: RUN_WITH_GRAPH })
  vi.spyOn(api, 'getTestOrderEntries').mockImplementation(async () => listResponse(entries))
  let complete!: () => void
  const update = vi.spyOn(api, 'updateTestOrderEntry').mockImplementation((_order, entryId, payload) => new Promise((resolve) => {
    complete = () => {
      entries = entries.map((entry) => entry.entryId === entryId ? { ...entry, ...payload } : entry)
      resolve(entries.find((entry) => entry.entryId === entryId)!)
    }
  }))
  const client = makeClient()
  renderViewer(client)
  fireEvent.click(await screen.findByText('验证转换'))
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '判定该用例为通过' }))
  await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
  fireEvent.click(screen.getByText('验证重试'))
  expect(await screen.findByRole('heading', { name: '第二条执行用例' })).toBeInTheDocument()
  complete()
  await waitFor(() => expect(screen.getByLabelText('执行状态：通过')).toBeInTheDocument())
  expect(screen.getByRole('heading', { name: '第二条执行用例' })).toBeInTheDocument()
  const panel = screen.getByRole('region', { name: '图谱用例执行' })
  expect(within(panel).getByRole('button', { name: '判定该用例为通过' })).toHaveAttribute('aria-pressed', 'false')
  expect(update).toHaveBeenCalledWith('order-1', 'entry-1', { status: 'passed' })
  client.clear()
})
