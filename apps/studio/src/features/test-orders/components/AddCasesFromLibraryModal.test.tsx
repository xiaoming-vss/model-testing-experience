import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { AddCasesFromLibraryModal } from './AddCasesFromLibraryModal'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))

const sprint = { sprintId: 'sprint-1', name: 'v1.2.0', status: 'running' as const }
const requirement = { requirementId: 'req-1', name: '租户隔离', sprintId: 'sprint-1' }
const suite = { suiteId: 'suite-1', name: '转换数据', requirementId: 'req-1' }
const libraryCase = {
  caseId: 'case-9',
  title: '验证其他租户用户不可查看转换任务与转换结果',
  priority: 'P1',
  caseType: '功能测试',
  suiteName: '转换数据',
  sprintName: 'v1.2.0',
  requirementName: '租户隔离',
  content: {
    preconditions: ['已保存租户 A 创建的转换任务'],
    steps: [{ action: '使用租户 B 账号登录', expected: '看不到租户 A 的转换任务' }],
  },
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function renderModal(client: QueryClient, props: Record<string, unknown> = {}) {
  return render(
    <QueryClientProvider client={client}>
      <AddCasesFromLibraryModal
        open
        orderId="order-1"
        projectId="project-1"
        sprintId="sprint-1"
        onClose={() => {}}
        {...props}
      />
    </QueryClientProvider>,
  )
}

function filterSelect(label: string) {
  const field = screen.getByText(label).closest('.api-filter-field')
  if (!field) throw new Error(`找不到「${label}」筛选框`)
  // antd v6 的 Select 没有 ant-select-selector，点击组件根节点即可展开下拉
  return field.querySelector('.ant-select') as HTMLElement
}

/** 在下拉浮层里按文案点选，避免和表格里的同名词撞车。 */
async function pickDropdownOption(user: ReturnType<typeof userEvent.setup>, label: string) {
  await waitFor(() => {
    const option = [...document.querySelectorAll('.ant-select-item-option')].find(
      (node) => node.textContent === label,
    )
    if (!option) throw new Error(`下拉里还没有「${label}」`)
  })
  const option = [...document.querySelectorAll('.ant-select-item-option')].find(
    (node) => node.textContent === label,
  ) as HTMLElement
  await user.click(option)
}

function mockLibraryApis() {
  vi.spyOn(api, 'getSprints').mockImplementation(async () => listResponse([sprint]))
  vi.spyOn(api, 'getRequirements').mockImplementation(async () => listResponse([requirement]))
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockImplementation(async () => listResponse([suite]))
  return vi
    .spyOn(api, 'getProjectFunctionTestCases')
    .mockImplementation(async () => listResponse([libraryCase]))
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('打开弹窗默认按测试单迭代查询用例', async () => {
  const getCases = mockLibraryApis()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  renderModal(client)

  await screen.findByText(libraryCase.title)
  await waitFor(() =>
    expect(getCases).toHaveBeenLastCalledWith(
      'project-1',
      expect.objectContaining({ sprintId: 'sprint-1', requirementId: '', suiteId: '' }),
    ),
  )
  client.clear()
})

it('切换迭代 / 需求 / 测试集筛选后查询参数跟随变化', async () => {
  const getCases = mockLibraryApis()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const user = userEvent.setup()
  renderModal(client)

  await screen.findByText(libraryCase.title)

  await user.click(filterSelect('需求'))
  await pickDropdownOption(user, '租户隔离')
  await waitFor(() =>
    expect(getCases).toHaveBeenLastCalledWith(
      'project-1',
      expect.objectContaining({ sprintId: 'sprint-1', requirementId: 'req-1' }),
    ),
  )

  await user.click(filterSelect('测试集'))
  await pickDropdownOption(user, '转换数据')
  await waitFor(() =>
    expect(getCases).toHaveBeenLastCalledWith(
      'project-1',
      expect.objectContaining({ requirementId: 'req-1', suiteId: 'suite-1' }),
    ),
  )

  // 切回全部迭代后，需求与测试集的选择一并清空
  await user.click(filterSelect('迭代'))
  await pickDropdownOption(user, '全部迭代')
  await waitFor(() =>
    expect(getCases).toHaveBeenLastCalledWith(
      'project-1',
      expect.objectContaining({ sprintId: '', requirementId: '', suiteId: '' }),
    ),
  )
  client.clear()
})

it('点击用例标题可以查看用例详情内容', async () => {
  mockLibraryApis()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const user = userEvent.setup()
  renderModal(client)

  await user.click(await screen.findByText(libraryCase.title))

  expect(await screen.findByText('用例详情')).toBeInTheDocument()
  expect(screen.getByText('已保存租户 A 创建的转换任务')).toBeInTheDocument()
  expect(screen.getByText('使用租户 B 账号登录')).toBeInTheDocument()
  expect(screen.getByText('预期：看不到租户 A 的转换任务')).toBeInTheDocument()
  client.clear()
})

it('已在测试单里的用例勾选框置灰', async () => {
  mockLibraryApis()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  renderModal(client, { existingCaseIds: ['case-9'] })

  await screen.findByText(libraryCase.title)
  await waitFor(() => {
    const node = document.querySelector('[aria-label="选择用例：验证其他租户用户不可查看转换任务与转换结果"]')
    expect(node).toBeTruthy()
    expect((node as HTMLInputElement).disabled).toBe(true)
  })
  client.clear()
})

/** 分页的每页条数下拉：按文案片段找选项，避免依赖 antd 的完整文案格式。 */
async function pickPageSize(user: ReturnType<typeof userEvent.setup>, size: string) {
  await user.click(document.querySelector('.ant-pagination-options .ant-select') as HTMLElement)
  await waitFor(() => {
    const option = [...document.querySelectorAll('.ant-select-item-option')].find((node) =>
      node.textContent?.startsWith(size),
    )
    if (!option) throw new Error(`下拉里还没有每页 ${size} 的选项`)
    // 全站没有引 antd 的 zh_CN，断言这个分页确实用了中文本地化，别退回「20 / page」。
    expect(option.textContent).toContain('条/页')
  })
  const option = [...document.querySelectorAll('.ant-select-item-option')].find((node) =>
    node.textContent?.startsWith(size),
  ) as HTMLElement
  await user.click(option)
}

it('可以切换每页条数并按新的条数重新查询', async () => {
  const getCases = mockLibraryApis()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const user = userEvent.setup()
  renderModal(client)

  await screen.findByText(libraryCase.title)
  await waitFor(() =>
    expect(getCases).toHaveBeenLastCalledWith('project-1', expect.objectContaining({ pageSize: 20 })),
  )

  await pickPageSize(user, '50')
  await waitFor(() =>
    expect(getCases).toHaveBeenLastCalledWith(
      'project-1',
      expect.objectContaining({ page: 1, pageSize: 50 }),
    ),
  )
  client.clear()
})

it('加入成功后弹窗不关闭，保留筛选并清空选择', async () => {
  mockLibraryApis()
  const add = vi
    .spyOn(api, 'addTestOrderCases')
    .mockImplementation(async () => ({ addedCount: 1, skippedCount: 0 }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const user = userEvent.setup()
  renderModal(client)

  await screen.findByText(libraryCase.title)
  await user.click(
    document.querySelector('[aria-label="选择用例：验证其他租户用户不可查看转换任务与转换结果"]') as HTMLInputElement,
  )
  await user.click(screen.getByRole('button', { name: /^加\s*入$/ }))
  await waitFor(() => expect(add).toHaveBeenCalledWith('order-1', ['case-9']))

  // 弹窗留着继续挑用例，选择被清空后「加入」回到不可点。
  expect(screen.getByText('加入用例')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('button', { name: /^加\s*入$/ })).toBeDisabled())
  client.clear()
})
