import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider as ThemeProvider } from '@/test/TestThemeProvider'
import type { RequirementAnalysisTaskRun } from '../types'
import { RequirementAnalysisTaskDetailPage } from './RequirementAnalysisTaskDetailPage'

const clients: QueryClient[] = []
afterEach(() => {
  cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks()
})
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify({ code: status === 200 ? 0 : status, message: status === 200 ? 'ok' : '提交失败', data }), {
    status, headers: { 'Content-Type': 'application/json' },
  })
}
function setup(stage: RequirementAnalysisTaskRun['currentStage'], status = 'error', fail = false, overrides: Partial<RequirementAnalysisTaskRun> = {}) {
  let run: RequirementAnalysisTaskRun = { runId: 'run', taskId: 'task', status,
    currentStage: stage, stageStatus: 'failed', reviewStatus: 'pending', errorMessage: 'model unavailable', ...overrides }
  const submit = vi.fn(async (_body: unknown) => {
    expect(_body).toEqual({ stage, llmConnectionId: 'mine' })
    if (fail) return response(null, 500)
    run = { ...run, status: 'pending', stageStatus: 'pending' }
    return response(run)
  })
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://localhost').pathname
    if (path.includes('/integrations/llm/connections')) return response({ items: [{ connectionId: 'mine', name: '本人模型', status: 'active' }], total: 1 })
    if (path.endsWith('/stage-retry')) return submit(JSON.parse(String(init?.body)))
    if (path === '/v1/requirement-analysis-tasks/task') return response({ taskId: 'task', projectId: 'project-1', name: '需求分析', sourceType: 'text' })
    if (path.endsWith('/runs')) return response({ items: [run], total: 1 })
    if (path === '/v1/requirement-analysis-runs/run') return response(run)
    return response({ items: [], total: 0 })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  seedOwnerProject(client)
  clients.push(client)
  render(<ThemeProvider><QueryClientProvider client={client}>
    <MemoryRouter initialEntries={['/requirements/task']}><Routes>
      <Route path="/requirements/:taskId" element={<RequirementAnalysisTaskDetailPage />} />
    </Routes></MemoryRouter>
  </QueryClientProvider></ThemeProvider>)
  return submit
}

// 运行记录操作列内联「审核/错误信息」，重试等状态变更收在行内「更多」下拉里。
async function findRunRow() {
  const idCell = await screen.findByText('run')
  const row = idCell.closest('tr')
  if (!row) throw new Error('未找到运行记录行')
  return row
}

async function findRunInlineAction(name: string) {
  const row = await findRunRow()
  // antd 会在两个汉字间插入空格。
  return within(row).findByRole('button', { name: new RegExp(`^${name.split('').join('\\s*')}$`) })
}

/** Modal.confirm 是命令式弹窗，上一个用例的实例可能还在离场动画里，这里只取当前这一个。 */
async function findDeleteConfirm() {
  const dialogs = await screen.findAllByRole('dialog')
  const dialog = dialogs.find((node) => node.textContent?.includes('确认删除该运行记录？') && !node.className.includes('zoom-leave'))
  if (!dialog) throw new Error('未找到删除运行记录的确认框')
  return dialog
}

async function openRunActionsMenu(user: ReturnType<typeof userEvent.setup>) {
  const row = await findRunRow()
  await user.click(await within(row).findByRole('button', { name: '更多操作' }))
}

it.each(['extracting_text', 'writing_requirement', 'feature_understanding'] as const)('重试 %s 并刷新为等待执行', async stage => {
  const submit = setup(stage)
  const user = userEvent.setup()
  await openRunActionsMenu(user)
  await user.click(await screen.findByRole('menuitem', { name: '重试阶段' }))
  await waitFor(() => expect(submit).toHaveBeenCalledExactlyOnceWith({ stage, llmConnectionId: 'mine' }))
  await waitFor(() => expect(screen.queryByRole('menuitem', { name: '重试阶段' })).toBeNull())
})

it('提交失败后保留重试入口', async () => {
  const submit = setup('extracting_text', 'error', true)
  const user = userEvent.setup()
  await openRunActionsMenu(user)
  await user.click(await screen.findByRole('menuitem', { name: '重试阶段' }))
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1))
  await openRunActionsMenu(user)
  await waitFor(() => expect(screen.getByRole('menuitem', { name: '重试阶段' })).not.toHaveAttribute('aria-disabled', 'true'))
})

it.each(['success', 'running', 'waiting_review'])('%s 不显示重试', async status => {
  setup('extracting_text', status)
  await screen.findByText('run')
  expect(screen.queryByRole('menuitem', { name: '重试阶段' })).toBeNull()
})


it('等待提交期间禁用重试，重复点击只发送一次', async () => {
  const submit = setup('extracting_text')
  let resolve!: (value: Response) => void
  submit.mockImplementationOnce(() => new Promise<Response>(done => { resolve = done }))
  const user = userEvent.setup()
  await openRunActionsMenu(user)
  await user.click(await screen.findByRole('menuitem', { name: '重试阶段' }))
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1))
  await openRunActionsMenu(user)
  await waitFor(() => expect(screen.getByRole('menuitem', { name: '重试阶段' })).toHaveAttribute('aria-disabled', 'true'))
  await user.click(screen.getByRole('menuitem', { name: '重试阶段' }))
  expect(submit).toHaveBeenCalledTimes(1)
  resolve(response(null, 500))
  await waitFor(() => expect(screen.getByRole('menuitem', { name: '重试阶段' })).not.toHaveAttribute('aria-disabled', 'true'))
})


it.each([
  ['extracting_text', ['增强文本']],
  ['writing_requirement', ['增强文本', '需求流程稿']],
  ['feature_understanding', ['增强文本', '需求流程稿', '需求理解记录']],
] as const)('失败在 %s 时只显示已执行到的阶段入口', async (stage, visible) => {
  setup(stage)
  await screen.findByText('run')
  for (const label of ['增强文本', '需求流程稿', '需求理解记录']) {
    expect(Boolean(screen.queryByRole('button', { name: label }))).toBe((visible as readonly string[]).includes(label))
  }
  expect(screen.getByRole('button', { name: '错误信息' })).toBeInTheDocument()
})

it('成功记录仍展示全部阶段产物入口', async () => {
  setup('completed', 'success')
  await screen.findByText('run')
  for (const label of ['增强文本', '需求流程稿', '需求理解记录']) {
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
  }
  expect(screen.queryByRole('button', { name: '错误信息' })).toBeNull()
})


it.each([
  ['extracting_text', '增强文本', []],
  ['writing_requirement', '需求流程稿', ['增强文本']],
] as const)('%s 待审核入口属于当前阶段且隐藏后续阶段', async (stage, label, previous) => {
  setup(stage, 'waiting_review', false, {
    checkpointEnabled: true, stageStatus: 'waiting_review',
    configJson: { firstStepOutput: '第一阶段内容', secondStepOutput: '第二阶段内容' },
  })
  await screen.findByText('run')
  const user = userEvent.setup()
  const reviewAction = await findRunInlineAction('审核')
  for (const section of ['增强文本', '需求流程稿', '需求理解记录']) {
    const reached = section === label || (previous as readonly string[]).includes(section)
    expect(Boolean(screen.queryByRole('button', { name: section }))).toBe(reached)
  }
  await user.click(reviewAction)
  expect(await screen.findByRole('dialog', { name: '审核' })).toBeInTheDocument()
  expect(screen.getByText(stage === 'extracting_text'
    ? '阶段产物 增强文本 firstStepOutput' : '阶段产物 需求流程稿 secondStepOutput')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '审核通过并继续' })).toBeInTheDocument()
})

it('待审核时已完成的增强文本入口只查看对应产物', async () => {
  setup('writing_requirement', 'waiting_review', false, {
    checkpointEnabled: true, stageStatus: 'waiting_review',
    configJson: { firstStepOutput: '增强文本的内容', secondStepOutput: '需求流程稿的内容' },
  })
  await userEvent.setup().click(await screen.findByRole('button', { name: '增强文本' }))
  expect(await screen.findByRole('dialog', { name: '增强文本' })).toBeInTheDocument()
  expect(screen.getByText('增强文本的内容')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '审核通过并继续' })).toBeNull()
})

it.each(['pending', 'running'] as const)('%s 时隐藏尚未执行的后续阶段', async status => {
  setup('extracting_text', status, false, { stageStatus: status })
  await screen.findByText('run')
  expect(screen.queryByRole('button', { name: '需求流程稿' })).toBeNull()
  expect(screen.queryByRole('button', { name: '需求理解记录' })).toBeNull()
})

it('继续优化在同一审核窗口展开，取消后保留内容和优化草稿', async () => {
  setup('writing_requirement', 'waiting_review', false, {
    checkpointEnabled: true, stageStatus: 'waiting_review',
    configJson: { secondStepOutput: '当前需求流程稿' },
  })
  const user = userEvent.setup()
  await user.click(await findRunInlineAction('审核'))
  const dialog = within(screen.getByRole('dialog'))
  const originalEditor = document.querySelector('.cm-content')
  await user.click(dialog.getByRole('button', { name: '继续优化' }))
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  expect(dialog.queryByRole('button', { name: '保存修改' })).not.toBeInTheDocument()
  expect(dialog.queryByRole('button', { name: '审核通过并继续' })).not.toBeInTheDocument()
  expect(dialog.getByRole('button', { name: '提交优化' }).closest('.ant-modal-footer')).not.toBeNull()
  expect(dialog.getByRole('button', { name: '取消优化' }).closest('.ant-modal-footer')).not.toBeNull()
  expect(dialog.queryByRole('button', { name: '继续优化' })).not.toBeInTheDocument()
  expect(document.querySelector('.cm-content')).toBe(originalEditor)
  expect(originalEditor).toHaveTextContent('当前需求流程稿')
  await user.type(dialog.getByLabelText('优化指令'), '补充异常分支')
  await user.click(dialog.getByRole('button', { name: '取消优化' }))
  expect(document.querySelector('.cm-content')).toBe(originalEditor)
  expect(dialog.getByRole('button', { name: '保存修改' })).toBeInTheDocument()
  await user.click(dialog.getByRole('button', { name: '继续优化' }))
  expect(dialog.getByLabelText('优化指令')).toHaveValue('补充异常分支')
  expect(dialog.getByLabelText('本次使用的模型')).toBeInTheDocument()
})

it('右侧提交使用所选模型并携带左侧未保存的需求修改', async () => {
  setup('writing_requirement', 'waiting_review', false, {
    checkpointEnabled: true, stageStatus: 'waiting_review', configJson: { secondStepOutput: '原流程' },
  })
  const previousFetch = vi.mocked(globalThis.fetch).getMockImplementation()!
  let body: Record<string, unknown> | undefined
  vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
    if (String(input).includes('/stage-revise')) {
      body = JSON.parse(String(init?.body))
      return response({ runId: 'run', status: 'pending', currentStage: 'writing_requirement', stageStatus: 'pending' })
    }
    return previousFetch(input, init)
  })
  const user = userEvent.setup()
  await user.click(await findRunInlineAction('审核'))
  const dialog = within(screen.getByRole('dialog'))
  const editor = document.querySelector('.cm-content') as HTMLElement
  await user.click(editor)
  await user.keyboard('{Control>}a{/Control}')
  await user.paste('尚未保存的新流程')
  await user.click(dialog.getByRole('button', { name: '继续优化' }))
  await user.type(dialog.getByLabelText('优化指令'), '补充异常处理')
  await user.click(dialog.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(body).toMatchObject({ llmConnectionId: 'mine', revisionInstruction: '补充异常处理', configJson: { secondStepOutput: '尚未保存的新流程' } }))
})


it('删除运行记录需确认，且只删除该次运行', async () => {
  const deleted: string[] = []
  setup('completed', 'success')
  const user = userEvent.setup()
  vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://localhost').pathname
    if (init?.method === 'DELETE') {
      deleted.push(path)
      return response({})
    }
    if (path.includes('/integrations/llm/connections')) return response({ items: [], total: 0 })
    if (path === '/v1/requirement-analysis-tasks/task') return response({ taskId: 'task', projectId: 'project-1', name: '需求分析', sourceType: 'text' })
    if (path.endsWith('/runs')) return response({ items: [{ runId: 'run', taskId: 'task', status: 'success', currentStage: 'completed', reviewStatus: 'pending' }], total: 1 })
    if (path === '/v1/requirement-analysis-runs/run') return response({ runId: 'run', taskId: 'task', status: 'success', currentStage: 'completed', reviewStatus: 'pending' })
    return response({ items: [], total: 0 })
  })
  await screen.findByText('run')

  await openRunActionsMenu(user)
  await user.click(await screen.findByRole('menuitem', { name: '删除运行记录' }))
  const confirm = await findDeleteConfirm()
  expect(deleted).toEqual([])
  await user.click(within(confirm).getByRole('button', { name: /^删\s*除$/ }))
  await waitFor(() => expect(deleted).toEqual(['/v1/requirement-analysis-runs/run']))
})

it('运行中的记录没有可用的删除入口', async () => {
  setup('extracting_text', 'running', false, { stageStatus: 'running' })
  const user = userEvent.setup()
  await openRunActionsMenu(user)
  expect(await screen.findByRole('menuitem', { name: '删除运行记录' })).toHaveAttribute('aria-disabled', 'true')
})

/** 顶栏与左侧导航的字段来自任务本身，与运行记录无关，这里单独起一份最小 mock。 */
function setupTaskOnly(overrides: Record<string, unknown> = {}) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = new URL(String(input), 'http://localhost').pathname
    if (path === '/v1/requirement-analysis-tasks/task') {
      return response({ taskId: 'task', projectId: 'project-1', name: '需求分析', sourceType: 'docx', instruction: '原指令', ...overrides })
    }
    if (path.endsWith('/runs')) return response({ items: [], total: 0 })
    return response({ items: [], total: 0 })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  seedOwnerProject(client)
  clients.push(client)
  render(<ThemeProvider><QueryClientProvider client={client}>
    <MemoryRouter initialEntries={['/requirements/task']}><Routes>
      <Route path="/requirements/:taskId" element={<RequirementAnalysisTaskDetailPage />} />
    </Routes></MemoryRouter>
  </QueryClientProvider></ThemeProvider>)
}

it('补充指令直接在详情页内联编辑并保存', async () => {
  let patchBody: unknown
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://localhost').pathname
    if (path === '/v1/requirement-analysis-tasks/task' && init?.method === 'PATCH') {
      patchBody = JSON.parse(String(init.body))
      return response({ taskId: 'task', projectId: 'project-1', name: '需求分析', sourceType: 'docx', instruction: '重点分析异常场景' })
    }
    if (path === '/v1/requirement-analysis-tasks/task') {
      return response({ taskId: 'task', projectId: 'project-1', name: '需求分析', sourceType: 'docx', instruction: '原指令' })
    }
    if (path.endsWith('/runs')) return response({ items: [], total: 0 })
    return response({ items: [], total: 0 })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  seedOwnerProject(client)
  clients.push(client)
  render(<ThemeProvider><QueryClientProvider client={client}>
    <MemoryRouter initialEntries={['/requirements/task']}><Routes>
      <Route path="/requirements/:taskId" element={<RequirementAnalysisTaskDetailPage />} />
    </Routes></MemoryRouter>
  </QueryClientProvider></ThemeProvider>)

  const user = userEvent.setup()
  // 导航条目的可访问名是「标题 + 摘要」，所以用正则匹配。
  await user.click(await screen.findByRole('button', { name: /补充指令/ }))

  const editor = await screen.findByPlaceholderText('例如：重点分析异常场景和歧义点')
  expect(editor).toHaveValue('原指令')

  // 没改动前不允许提交，避免把原值当成一次修改写回去。
  const save = screen.getByRole('button', { name: '保存指令' })
  expect(save).toBeDisabled()

  await user.clear(editor)
  await user.type(editor, '重点分析异常场景')
  await waitFor(() => expect(screen.getByRole('button', { name: '保存指令' })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: '保存指令' }))

  await waitFor(() => expect(patchBody).toMatchObject({ name: '需求分析', instruction: '重点分析异常场景' }))
})

it('顶栏按设计稿展示任务名与迭代，左侧导航带运行条数徽标', async () => {
  setupTaskOnly({ sprintId: 'sprint-1', requirementId: 'requirement-1' })
  await screen.findByText('需求分析')

  const toolbar = document.querySelector('.ai-task-detail-toolbar')
  expect(toolbar).not.toBeNull()
  expect(within(toolbar as HTMLElement).getByText('任务名称')).toBeInTheDocument()
  expect(within(toolbar as HTMLElement).getByText('迭代')).toBeInTheDocument()
  expect(within(toolbar as HTMLElement).getByText('来源类型')).toBeInTheDocument()
  expect(within(toolbar as HTMLElement).getByText('docx')).toBeInTheDocument()

  const runsNav = screen.getByRole('button', { name: /运行记录/ })
  expect(within(runsNav).getByText('0')).toBeInTheDocument()
})
