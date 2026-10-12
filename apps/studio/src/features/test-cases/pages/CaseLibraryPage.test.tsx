import { seedOwnerProject } from '@/test/projectAccess'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { CaseLibraryPage } from './CaseLibraryPage'

const testScope = vi.hoisted(() => ({ sprintId: 'sprint-1', requirementId: undefined as string | undefined }))

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/features/projects/hooks/useActiveSprint', () => ({
  useActiveSprint: () => ({
    activeSprintId: 'sprint-1',
    sprints: [{ sprintId: 'sprint-1', name: 'V1.0.0 迭代' }],
    sprintsQuery: { isLoading: false, error: null },
    selectSprint: vi.fn(),
    sprintSelectorOptions: [
      { label: '全部迭代', value: 'all' },
      { label: 'V1.0.0 迭代', value: 'sprint-1' },
    ],
  }),
}))
vi.mock('@/features/projects/hooks/useSprintRequirementScope', () => ({
  useSprintRequirementScope: () => ({
    currentSprintSelection: null,
    currentRequirementSelection: null,
    resolvedSelectedSprintId: testScope.sprintId,
    resolvedSelectedRequirementId: testScope.requirementId,
    sprints: [{ sprintId: 'sprint-1', name: 'V1.0.0 迭代' }],
    sprintsQuery: { isLoading: false, error: null },
    requirementsQuery: { data: [], isLoading: false, error: null },
    sprintFilterOptions: [
      { label: '全部迭代', value: 'all' },
      { label: 'V1.0.0 迭代', value: 'sprint-1' },
    ],
    requirementFilterOptions: [{ label: '全部需求', value: 'all' }],
    selectRequirement: vi.fn(),
    selectSprint: vi.fn(),
  }),
}))
vi.mock('@/features/projects/hooks/useProjectRequirements', () => ({
  useProjectRequirements: () => ({
    allRequirements: [],
    allRequirementsQuery: { isLoading: false, error: null },
    requirementNameMap: new Map([['req-1', '私有化云服务器部署流程']]),
    requirementSprintMap: new Map([['req-1', 'sprint-1']]),
    sprintNameMap: new Map([['sprint-1', 'V1.0.0 迭代']]),
  }),
}))

const suite = { suiteId: 'suite-1', name: '业务价值验证场景', requirementId: 'req-1', caseCount: 12 }

const loginCase = {
  caseId: 'case-1',
  suiteId: 'suite-1',
  title: '服务器部署判定【本地连接】',
  module: '私有化云服务端部署',
  priority: 'P0',
  caseType: '安装部署',
  suiteName: '业务价值验证场景',
  requirementName: '私有化云服务器部署流程',
  sprintName: 'V1.0.0 迭代',
  content: { preconditions: ['已进入页面'], steps: [{ action: '点击部署', expected: '部署成功' }] },
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// 这个环境里 getByRole 每次要遍历整棵 DOM（单次约 5s），所以按文案 / aria-label 取节点。
// antd 会给「两个汉字且没有图标」的按钮插入空格（取消 → 取 消），所以逐字允许空白。
function button(text: string) {
  const pattern = new RegExp(`^${[...text].map(escapeRegExp).join('\\s*')}$`)
  const node = screen.getByText(pattern).closest('button')
  if (!node) throw new Error(`找不到按钮：${text}`)
  return node
}

/** 图标按钮没有文字，只能按 aria-label 取。 */
function iconButton(label: string, scope: ParentNode = document) {
  const node = scope.querySelector(`[aria-label="${label}"]`)
  if (!node) throw new Error(`找不到图标按钮：${label}`)
  return node as HTMLElement
}

function checkbox(label: string) {
  const node = document.querySelector(`[aria-label="${label}"]`)
  if (!node) throw new Error(`找不到勾选框：${label}`)
  return node as HTMLInputElement
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function caseTitleInput() {
  return screen.getByPlaceholderText('例如：用户使用正确账号密码登录成功') as HTMLInputElement
}

function caseField(label: '请输入前置条件，可换行填写' | '每行填写一个操作步骤' | '每行填写对应步骤的预期结果') {
  return screen.getByPlaceholderText(label) as HTMLTextAreaElement
}

/** 用例编辑弹窗：点行或点「新建用例」之后它就是唯一的那块容器。 */
function caseModal() {
  const node = document.querySelector('.case-library-case-modal')
  if (!node) throw new Error('用例弹窗没有打开')
  return node as HTMLElement
}

/** 点表格里的用例标题：直接弹出编辑弹窗，没有抽屉也没有只读态。 */
async function openCaseRow(title: string) {
  await userEvent.setup().click(await screen.findByText(title))
  await waitFor(() => expect(document.querySelector('.case-library-case-modal')).not.toBeNull())
}

beforeEach(() => {
  testScope.sprintId = 'sprint-1'
  testScope.requirementId = undefined
  useWorkbenchStore.setState({ activeProjectId: 'project-1', activeSprintId: 'sprint-1' })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

function buildClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  return client
}

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CaseLibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** 选中左栏的测试集，右栏随即只请求该测试集。 */
async function selectSuite(container: HTMLElement) {
  const sidebar = container.querySelector('.api-case-sidebar') as HTMLElement
  await within(sidebar).findByText('业务价值验证场景')
  await userEvent.setup().click(within(sidebar).getByText('业务价值验证场景'))
  await waitFor(() => expect(within(sidebar).getByText('业务价值验证场景').closest('button')).toHaveAttribute('aria-current', 'true'))
}

it('左栏平铺展示测试集，默认落在「全部用例」', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  const cases = vi
    .spyOn(api, 'getProjectFunctionTestCases')
    .mockImplementation(async () => listResponse([loginCase]))
  const client = buildClient()
  const { container } = renderPage(client)
  const sidebar = container.querySelector('.api-case-sidebar') as HTMLElement

  // 左栏：测试集 + 用例数，没有需求分组标题
  expect(await within(sidebar).findByText('业务价值验证场景')).toBeInTheDocument()
  expect(within(sidebar).queryByText('私有化云服务器部署流程')).toBeNull()
  // 这一份 fixture 只有一个测试集，两行的数字恰好都是 12，所以按行分别断言
  const allCasesRow = within(sidebar).getByText('全部用例').closest('button') as HTMLElement
  expect(within(allCasesRow).getByText('12')).toBeInTheDocument()
  const suiteRow = within(sidebar).getByText('业务价值验证场景').closest('button') as HTMLElement
  expect(within(suiteRow).getByText('12')).toBeInTheDocument()

  // 右栏：全部用例时显示「所属测试集」列，且不请求某个具体测试集
  expect(await screen.findByText('服务器部署判定【本地连接】')).toBeInTheDocument()
  expect(screen.getByText('所属测试集', { selector: 'th' })).toBeInTheDocument()
  expect(cases.mock.calls.at(-1)?.[1]).toMatchObject({ sprintId: 'sprint-1', suiteId: '' })
  client.clear()
})

it('测试集搜索只看测试集名称', async () => {
  const other = { suiteId: 'suite-2', name: '数据集管理', requirementId: 'req-1', caseCount: 3 }
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () =>
    listResponse([suite, other]),
  )
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  const client = buildClient()
  const { container } = renderPage(client)
  const sidebar = container.querySelector('.api-case-sidebar') as HTMLElement
  await within(sidebar).findByText('数据集管理')

  const user = userEvent.setup()
  // 需求名不再是左栏可见信息，因此也不参与筛选。
  await user.type(within(sidebar).getByPlaceholderText('搜索测试集'), '部署流程')
  expect(within(sidebar).queryByText('业务价值验证场景')).toBeNull()
  expect(within(sidebar).queryByText('数据集管理')).toBeNull()

  await user.clear(within(sidebar).getByPlaceholderText('搜索测试集'))
  await user.type(within(sidebar).getByPlaceholderText('搜索测试集'), '数据')
  expect(within(sidebar).getByText('数据集管理')).toBeInTheDocument()
  expect(within(sidebar).queryByText('业务价值验证场景')).toBeNull()
  client.clear()
})

it('选中测试集后只请求该测试集，并出现测试集操作', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  const cases = vi
    .spyOn(api, 'getProjectFunctionTestCases')
    .mockImplementation(async () => listResponse([loginCase]))
  const client = buildClient()
  const { container } = renderPage(client)
  await selectSuite(container)

  await waitFor(() =>
    expect(cases.mock.calls.some((call) => (call[1] as { suiteId?: string }).suiteId === 'suite-1')).toBe(
      true,
    ),
  )
  // 选中具体测试集后不再显示「所属测试集」列
  await waitFor(() => expect(screen.queryByText('所属测试集')).toBeNull())
  expect(iconButton('编辑测试集')).toBeEnabled()
  expect(iconButton('删除测试集')).toBeEnabled()
  // 用例归属测试集，选中后新建与导入才可用
  expect(button('新建用例')).toBeEnabled()
  expect(button('用例导入')).toBeEnabled()
  // 加入测试单改在测试单里操作，用例库不再提供这个入口
  expect(screen.queryByText(/加入测试单/)).toBeNull()
  client.clear()
})

it('测试集的新建 / 编辑 / 删除都收在左栏底部', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  const client = buildClient()
  const { container } = renderPage(client)
  const sidebar = container.querySelector('.api-case-sidebar') as HTMLElement
  const foot = sidebar.querySelector('.case-library-sidebar-foot') as HTMLElement
  await within(foot).findByText('新建测试集')

  // 三个动作都在左栏底部：新建带文字，编辑 / 删除是图标按钮；后者未选中测试集时不可用
  expect(iconButton('编辑测试集', foot)).toBeDisabled()
  expect(iconButton('删除测试集', foot)).toBeDisabled()

  // 左栏的测试集要等接口回来才渲染出来
  await selectSuite(container)
  await waitFor(() => expect(iconButton('删除测试集', foot)).not.toBeDisabled())
  expect(iconButton('编辑测试集', foot)).not.toBeDisabled()

  // 顶部工具栏不重复测试集管理动作
  const head = container.querySelector('.api-panel-header') as HTMLElement
  expect(within(head).queryByText('新建测试集')).toBeNull()
  expect(head.querySelector('[aria-label="编辑测试集"]')).toBeNull()
  expect(head.querySelector('[aria-label="删除测试集"]')).toBeNull()
  client.clear()
})

it('全部用例时不显示按测试集执行的那组动作', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  const client = buildClient()
  const { container } = renderPage(client)

  await screen.findByText('服务器部署判定【本地连接】')
  // 这三个都按测试集执行，未选中测试集时整组不出现（而不是显示成禁用）
  expect(screen.queryByText('新建用例')).toBeNull()
  expect(screen.queryByText('用例导入')).toBeNull()
  expect(screen.queryByText('导入禅道')).toBeNull()
  expect(container.querySelector('.case-library-main-actions')).toBeNull()
  // 编辑 / 删除测试集属于左栏底部那组，仍在，只是禁用
  const sidebar = container.querySelector('.api-case-sidebar') as HTMLElement
  expect(iconButton('编辑测试集', sidebar)).toBeDisabled()
  expect(iconButton('删除测试集', sidebar)).toBeDisabled()
  client.clear()
})

it('「全部用例」显示的是全部用例数，不随选中的测试集变化', async () => {
  const other = { suiteId: 'suite-2', name: '数据集管理', requirementId: 'req-1', caseCount: 5 }
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () =>
    listResponse([suite, other]),
  )
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  const client = buildClient()
  const { container } = renderPage(client)
  const sidebar = container.querySelector('.api-case-sidebar') as HTMLElement
  const allCasesRow = () => within(sidebar).getByText('全部用例').closest('button') as HTMLElement

  // 12 + 5
  await waitFor(() => expect(within(allCasesRow()).getByText('17')).toBeInTheDocument())

  // 选中某个测试集后，列表请求换成了该测试集，但「全部用例」仍是全部的数量
  await selectSuite(container)
  expect(within(allCasesRow()).getByText('17')).toBeInTheDocument()
  expect(within(sidebar).getByText('12')).toBeInTheDocument()
  client.clear()
})

it('点用例直接进编辑：没有抽屉、没有只读态、没有编辑按钮', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  const update = vi
    .spyOn(api, 'updateFunctionTestCase')
    .mockImplementation(async (_caseId, body) => ({ ...loginCase, ...body }))
  const client = buildClient()
  renderPage(client)

  await openCaseRow('服务器部署判定【本地连接】')

  // 打开的是一块弹窗容器，表单里直接就是这条用例的内容
  const modal = caseModal()
  expect(within(modal).getByText('编辑用例')).toBeInTheDocument()
  expect(caseTitleInput().value).toBe('服务器部署判定【本地连接】')
  expect(caseField('请输入前置条件，可换行填写').value).toBe('已进入页面')
  expect(caseField('每行填写一个操作步骤').value).toBe('点击部署')
  expect(caseField('每行填写对应步骤的预期结果').value).toBe('部署成功')

  // 不是抽屉，也没有需要再点一次的「编辑」
  expect(document.querySelector('.ant-drawer')).toBeNull()
  expect(screen.queryByText('用例详情')).toBeNull()
  expect(screen.queryByText('编辑')).toBeNull()
  expect(screen.queryByText('在所属测试集中打开')).toBeNull()

  // 改完保存
  const user = userEvent.setup()
  await user.clear(caseTitleInput())
  await user.type(caseTitleInput(), '服务器部署判定改')
  await user.click(button('保存变更'))
  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      'case-1',
      expect.objectContaining({ title: '服务器部署判定改', module: '业务价值验证场景' }),
    ),
  )
  // 保存后弹窗留在原地
  expect(document.querySelector('.case-library-case-modal')).not.toBeNull()

  // 关掉弹窗后回到列表
  await user.click(button('取消'))
  await waitFor(() => expect(document.querySelector('.case-library-case-modal')).toBeNull())
  expect(screen.getByText('所属测试集', { selector: 'th' })).toBeInTheDocument()
  client.clear()
})

it('选中测试集后新建用例，新建时挂在该测试集下', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  const create = vi
    .spyOn(api, 'createFunctionTestCase')
    .mockImplementation(async (_suiteId, body) => ({ ...body, caseId: 'case-new' }))
  const client = buildClient()
  const { container } = renderPage(client)
  await selectSuite(container)

  const user = userEvent.setup()
  await user.click(button('新建用例'))
  await waitFor(() => expect(document.querySelector('.case-library-case-modal')).not.toBeNull())

  // 新建是同一个弹窗容器，只是没有「删除」、也没有创建 / 更新时间
  const modal = caseModal()
  expect(within(modal).getByText('新建用例')).toBeInTheDocument()
  expect(within(modal).queryByText('删除')).toBeNull()
  expect(within(modal).queryByText(/创建时间/)).toBeNull()
  expect(caseTitleInput().value).toBe('')

  await user.type(caseTitleInput(), '新增的部署判定用例')
  await user.click(button('保存变更'))

  await waitFor(() =>
    expect(create).toHaveBeenCalledWith(
      'suite-1',
      expect.objectContaining({
        title: '新增的部署判定用例',
        module: '业务价值验证场景',
        // 排在测试集现有 12 条之后
        orderNo: 13,
      }),
    ),
  )
  client.clear()
})

it.each([false, true])('批量删除只提交勾选项，失败保留选择（失败=%s）', async (fail) => {
  let items = [
    { ...loginCase, caseId: 'case-1', title: '用例甲' },
    { ...loginCase, caseId: 'case-2', title: '用例乙' },
  ]
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse(items))
  const remove = vi.spyOn(api, 'batchDeleteFunctionTestCases').mockImplementation(async () => {
    if (fail) throw new Error('删除失败')
    items = items.filter((item) => item.caseId !== 'case-1')
    return { deletedIds: ['case-1'], deletedCount: 1 }
  })
  const client = buildClient()
  const { container } = renderPage(client)
  await selectSuite(container)

  const user = userEvent.setup()
  await screen.findByText('用例甲')
  expect(button('批量删除')).toBeDisabled()
  await user.click(checkbox('选择用例：用例甲'))
  await user.click(button('批量删除（1）'))
  expect(remove).not.toHaveBeenCalled()

  await user.click(await screen.findByText('确认删除').then((node) => node.closest('button')!))
  await waitFor(() => expect(remove).toHaveBeenCalledExactlyOnceWith('suite-1', ['case-1']))

  if (fail) {
    expect(checkbox('选择用例：用例甲')).toBeChecked()
  } else {
    await waitFor(() =>
      expect(document.querySelector('[aria-label="选择用例：用例甲"]')).toBeNull(),
    )
    expect(checkbox('选择用例：用例乙')).not.toBeChecked()
    expect(button('批量删除')).toBeDisabled()
  }
  client.clear()
})

it('列表行带上用例编号、优先级色块与用例类型色块', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  const client = buildClient()
  renderPage(client)

  await screen.findByText('服务器部署判定【本地连接】')
  // 快速过滤条里也有 P0，所以这几条断言限定在表格里
  const table = within(document.querySelector('.case-library-table-scroll') as HTMLElement)
  // 编号是 UUID，只露前 8 位，完整值留在 title 里
  expect(table.getByText('case-1')).toHaveAttribute('title', 'case-1')
  expect(table.getByText('P0')).toHaveClass('tone-red')
  // 用例类型按关键词归色调，认不出来的走兜底色
  expect(table.getByText('安装部署')).toHaveClass('tone-indigo')
  client.clear()
})

it('快速过滤条按优先级筛选，再点一次取消', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  const cases = vi
    .spyOn(api, 'getProjectFunctionTestCases')
    .mockImplementation(async () => listResponse([loginCase]))
  const client = buildClient()
  renderPage(client)
  await screen.findByText('服务器部署判定【本地连接】')

  const user = userEvent.setup()
  await user.click(button('P1'))
  await waitFor(() => expect(cases.mock.calls.at(-1)?.[1]).toMatchObject({ priority: 'P1' }))

  // 同一档再点一次就是取消，不是重复筛选；取消后回到挂载时的筛选组合，
  // 30s 内命中缓存不再发请求，列表直接显示未过滤数据。
  const callsBeforeCancel = cases.mock.calls.length
  await user.click(button('P1'))
  expect(cases.mock.calls.length).toBe(callsBeforeCancel)
  expect(await screen.findByText('服务器部署判定【本地连接】')).toBeInTheDocument()
  client.clear()
})

it('用例类型按精确值筛选，选择后请求带上 caseType', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  const cases = vi
    .spyOn(api, 'getProjectFunctionTestCases')
    .mockImplementation(async () => listResponse([loginCase]))
  const client = buildClient()
  renderPage(client)
  await screen.findByText('服务器部署判定【本地连接】')

  const user = userEvent.setup()
  await user.click(screen.getByText('全部类型'))
  await user.click(await screen.findByTitle('安全测试'))

  await waitFor(() => expect(cases.mock.calls.at(-1)?.[1]).toMatchObject({ caseType: '安全测试' }))
  client.clear()
})

it('搜索框支持 Ctrl / ⌘ + K 聚焦', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async () => listResponse([loginCase]))
  const client = buildClient()
  renderPage(client)
  await screen.findByText('服务器部署判定【本地连接】')

  const input = screen.getByPlaceholderText('搜索用例名称 / 模块')
  expect(input).not.toHaveFocus()
  await userEvent.setup().keyboard('{Control>}k{/Control}')
  expect(input).toHaveFocus()
  client.clear()
})

it('用例推送使用项目 MCP，部分失败保留详情并阻止未知结果重试', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue(listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockResolvedValue(listResponse([loginCase]))
  const oldConnections = vi.spyOn(api, 'getZentaoConnections')
  const push = vi.spyOn(api, 'importFunctionTestCasesToZentao').mockResolvedValue({
    status: 'partial_failure', importedCaseCount: 1,
    items: [{ caseId: 'case-1', status: 'uncertain', errorMessage: '请先在禅道核对，勿直接重试' }],
  })
  const client = buildClient()
  const { container } = renderPage(client)
  await selectSuite(container)
  await userEvent.click(button('导入禅道'))
  await userEvent.click(button('开始导入'))
  await waitFor(() => expect(push).toHaveBeenCalledWith('suite-1', { productId: 1, moduleId: 0, caseIds: undefined }))
  expect(await screen.findByText('推送未全部完成')).toBeInTheDocument()
  expect(screen.getByText(/请先在禅道核对/)).toBeInTheDocument()
  expect(button('开始导入')).toBeDisabled()
  expect(oldConnections).not.toHaveBeenCalled()
  client.clear()
})

it('切换测试集清空旧选择，返回后不恢复，并支持手动清空', async () => {
  const other = { ...suite, suiteId: 'suite-2', name: '数据集管理' }
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue(listResponse([suite, other]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockResolvedValue(listResponse([loginCase]))
  const client = buildClient()
  const { container } = renderPage(client)
  await selectSuite(container)
  const user = userEvent.setup()
  await user.click(checkbox(`选择用例：${loginCase.title}`))
  expect(button('批量删除（1）')).toBeEnabled()
  await user.click(within(container.querySelector('.case-library-tree') as HTMLElement).getByText('数据集管理'))
  await waitFor(() => expect(button('批量删除')).toBeDisabled())
  expect(checkbox(`选择用例：${loginCase.title}`)).not.toBeChecked()
  await selectSuite(container)
  expect(checkbox(`选择用例：${loginCase.title}`)).not.toBeChecked()
  await user.click(checkbox(`选择用例：${loginCase.title}`))
  await user.click(button('清空选择'))
  expect(button('批量删除')).toBeDisabled()
  client.clear()
})

it('空库中央提供新建测试集入口并打开原抽屉', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue(listResponse([]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockResolvedValue(listResponse([]))
  const client = buildClient()
  const { container } = renderPage(client)
  expect(await screen.findByText('先创建测试集，再添加或导入用例。')).toBeInTheDocument()
  const main = container.querySelector('.case-library-main') as HTMLElement
  await userEvent.click(within(main).getByText('新建测试集').closest('button')!)
  expect(await screen.findByText('新建功能测试集')).toBeInTheDocument()
  client.clear()
})

it('清除用例筛选保留测试集和迭代范围', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue(listResponse([suite]))
  const cases = vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async (_id, params) =>
    listResponse(params?.priority || params?.keyword ? [] : [loginCase]),
  )
  const client = buildClient()
  const { container } = renderPage(client)
  await selectSuite(container)
  const user = userEvent.setup()
  await user.click(button('P1'))
  await user.type(screen.getByLabelText('搜索用例名称或模块'), '找不到')
  await waitFor(() => expect(cases.mock.calls.at(-1)?.[1]).toMatchObject({ keyword: '找不到' }))
  expect(await screen.findByText('没有符合筛选条件的用例')).toBeInTheDocument()
  await user.click(button('清除用例筛选'))
  // 清除后回到 30s 内请求过的组合时命中缓存、可能不再发请求；
  // 但列表必须恢复未过滤数据，且任何补发请求都要保留测试集与迭代范围。
  const callsBeforeClear = cases.mock.calls.length
  const newCallsAfterClear = () => cases.mock.calls.slice(callsBeforeClear)
  await waitFor(() => {
    for (const [, params] of newCallsAfterClear()) {
      expect(params).toMatchObject({
        suiteId: 'suite-1', sprintId: 'sprint-1', priority: '', caseType: '', keyword: '', page: 1,
      })
    }
    expect(screen.getByLabelText('搜索用例名称或模块')).toHaveValue('')
    expect(screen.queryByText('没有符合筛选条件的用例')).toBeNull()
  })
  expect(await screen.findByText(loginCase.title)).toBeInTheDocument()
  const sidebar = container.querySelector('.api-case-sidebar') as HTMLElement
  expect(within(sidebar).getByText('业务价值验证场景').closest('button')).toHaveAttribute('aria-current', 'true')
  client.clear()
})

it('加载失败不显示空库或零数量，原位重试恢复数据', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockRejectedValueOnce(new Error('测试集网络中断'))
    .mockResolvedValue(listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockRejectedValueOnce(new Error('用例网络中断'))
    .mockResolvedValue(listResponse([loginCase]))
  const client = buildClient()
  renderPage(client)
  expect(await screen.findByText('测试集加载失败')).toBeInTheDocument()
  expect(await screen.findByText('用例加载失败')).toBeInTheDocument()
  expect(screen.queryByText('当前范围暂无测试集')).toBeNull()
  expect(screen.queryByText('当前范围暂无用例')).toBeNull()
  expect(screen.queryByText(/共 0 条/)).toBeNull()
  const user = userEvent.setup()
  await user.click(button('重试测试集'))
  await user.click(button('重试用例'))
  expect(await screen.findByText(loginCase.title)).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByText('用例加载失败')).toBeNull())
  client.clear()
})

it('刷新失败保留已加载用例', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue(listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockResolvedValueOnce(listResponse([loginCase]))
    .mockRejectedValue(new Error('连接中断'))
  const client = buildClient()
  renderPage(client)
  await screen.findByText(loginCase.title)
  await userEvent.click(iconButton('刷新用例列表'))
  expect(await screen.findByText('用例加载失败')).toBeInTheDocument()
  expect(screen.getByText(loginCase.title)).toBeInTheDocument()
  expect(screen.queryByText('当前范围暂无用例')).toBeNull()
  client.clear()
})


it.each(['sprint', 'requirement', 'project'])('切换业务范围清空选择：%s', async (scope) => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue(listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockResolvedValue(listResponse([loginCase]))
  const client = buildClient()
  const view = renderPage(client)
  await selectSuite(view.container)
  await userEvent.click(checkbox(`选择用例：${loginCase.title}`))
  expect(button('批量删除（1）')).toBeEnabled()
  if (scope === 'sprint') testScope.sprintId = 'sprint-2'
  if (scope === 'requirement') testScope.requirementId = 'req-2'
  if (scope === 'project') seedOwnerProject(client, 'project-2')
  view.rerender(<QueryClientProvider client={client}><MemoryRouter><CaseLibraryPage /></MemoryRouter></QueryClientProvider>)
  await waitFor(() => expect(button('批量删除')).toBeDisabled())
  await screen.findByText(loginCase.title)
  expect(checkbox(`选择用例：${loginCase.title}`)).not.toBeChecked()
  client.clear()
})

it('同一测试集翻页保留选择，批量提交两页的用例', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue(listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockImplementation(async (_id, params) => {
    const item = params?.page === 2 ? { ...loginCase, caseId: 'case-2', title: '第二页用例' } : loginCase
    return Object.assign(listResponse([item]), { total: 21 })
  })
  const remove = vi.spyOn(api, 'batchDeleteFunctionTestCases').mockResolvedValue({ deletedIds: ['case-1', 'case-2'], deletedCount: 2 })
  const client = buildClient()
  const { container } = renderPage(client)
  await selectSuite(container)
  const user = userEvent.setup()
  await user.click(checkbox(`选择用例：${loginCase.title}`))
  await user.click(container.querySelector('.ant-pagination-next button')!)
  await screen.findByText('第二页用例')
  await user.click(checkbox('选择用例：第二页用例'))
  await user.click(button('批量删除（2）'))
  await user.click(button('确认删除'))
  await waitFor(() => expect(remove).toHaveBeenCalledWith('suite-1', ['case-1', 'case-2']))
  client.clear()
})

it('不重复展示模块列，数字优先级与快速筛选使用一致标签', async () => {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue(listResponse([suite]))
  vi.spyOn(api, 'getProjectFunctionTestCases').mockResolvedValue(listResponse([
    { ...loginCase, module: suite.name, priority: '2' },
  ]))
  const client = buildClient()
  const { container } = renderPage(client)
  await screen.findByText(loginCase.title)
  expect(screen.queryByText('模块', { selector: 'th' })).toBeNull()
  expect(container.querySelector('.case-library-priority')).toHaveTextContent('P2')
  client.clear()
})
