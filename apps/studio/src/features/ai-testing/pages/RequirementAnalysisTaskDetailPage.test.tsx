import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider as ThemeProvider } from '@/test/TestThemeProvider'
import type { RequirementAnalysisTaskRun } from '../types'
import { RequirementAnalysisTaskDetailPage } from './RequirementAnalysisTaskDetailPage'
import extractionText from '@/domain/requirements/fixtures/document-extraction.example.json?raw'
import understandingText from '@/domain/requirements/fixtures/requirement-understanding.example.json?raw'

const extraction = JSON.parse(extractionText)
const understanding = JSON.parse(understandingText)

const clients: QueryClient[] = []
afterEach(() => {
  cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks()
})
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify({ code: status === 200 ? 0 : status, message: status === 200 ? 'ok' : '提交失败', data }), {
    status, headers: { 'Content-Type': 'application/json' },
  })
}
function setup(stage: RequirementAnalysisTaskRun['currentStage'], status = 'error', fail = false, overrides: Partial<RequirementAnalysisTaskRun> = {}, otherRuns: RequirementAnalysisTaskRun[] = [], embedded = false) {
  let run: RequirementAnalysisTaskRun = { runId: 'run', taskId: 'task', status,
    currentStage: stage, stageStatus: 'failed', reviewStatus: 'pending', errorMessage: 'model unavailable', workflowVersion: 2, snapshotJson: { workflowVersion: 2, taskType: 'requirement_analysis' }, configJson: { firstStepOutput: extraction }, resultYaml: JSON.stringify(understanding), ...overrides }
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
    if (path.endsWith('/runs')) return response({ items: [...otherRuns, run], total: otherRuns.length + 1 })
    const otherRun = otherRuns.find(item => path === `/v1/requirement-analysis-runs/${item.runId}`)
    if (otherRun) return response(otherRun)
    if (path === '/v1/requirement-analysis-runs/run') return response(run)
    return response({ items: [], total: 0 })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  seedOwnerProject(client)
  clients.push(client)
  render(<ThemeProvider><QueryClientProvider client={client}>
    <MemoryRouter initialEntries={['/requirements/task']}><Routes>
      <Route path="/requirements/:taskId" element={<RequirementAnalysisTaskDetailPage dialogRequest={embedded ? { taskId: 'task', runId: 'run', artifact: 'resultYaml', mode: 'review', onClose: vi.fn() } : undefined} />} />
    </Routes></MemoryRouter>
  </QueryClientProvider></ThemeProvider>)
  return submit
}

// 运行记录当前至多三项操作，审核、重试与删除均直接展示。
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

it.each(['extracting_text', 'feature_understanding'] as const)('重试 %s 并刷新为等待执行', async stage => {
  const submit = setup(stage)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '重试阶段' }))
  await waitFor(() => expect(submit).toHaveBeenCalledExactlyOnceWith({ stage, llmConnectionId: 'mine' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: '重试阶段' })).toBeNull())
})

it('提交失败后保留重试入口', async () => {
  const submit = setup('extracting_text', 'error', true)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '重试阶段' }))
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(screen.getByRole('button', { name: '重试阶段' })).toBeEnabled())
})

it.each(['success', 'running', 'waiting_review'])('%s 不显示重试', async status => {
  setup('extracting_text', status)
  await screen.findByText('run')
  expect(screen.queryByRole('button', { name: '重试阶段' })).toBeNull()
})


it('等待提交期间禁用重试，重复点击只发送一次', async () => {
  const submit = setup('extracting_text')
  let resolve!: (value: Response) => void
  submit.mockImplementationOnce(() => new Promise<Response>(done => { resolve = done }))
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '重试阶段' }))
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(screen.getByRole('button', { name: '重试阶段' })).toBeDisabled())
  await user.click(screen.getByRole('button', { name: '重试阶段' }))
  expect(submit).toHaveBeenCalledTimes(1)
  resolve(response(null, 500))
  await waitFor(() => expect(screen.getByRole('button', { name: '重试阶段' })).toBeEnabled())
})


it.each([
  ['extracting_text', ['材料提取结果']],
  ['feature_understanding', ['材料提取结果', '需求理解记录']],
] as const)('失败在 %s 时只显示已执行到的阶段入口', async (stage, visible) => {
  setup(stage)
  await screen.findByText('run')
  for (const label of ['材料提取结果', '需求理解记录']) {
    expect(Boolean(screen.queryByRole('button', { name: label }))).toBe((visible as readonly string[]).includes(label))
  }
  expect(screen.getByRole('button', { name: '错误信息' })).toBeInTheDocument()
})

it('成功记录仍展示全部阶段产物入口', async () => {
  setup('feature_understanding', 'success')
  await screen.findByText('run')
  for (const label of ['材料提取结果', '需求理解记录']) {
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
  }
  expect(screen.queryByRole('button', { name: '错误信息' })).toBeNull()
})


it.each([
  ['extracting_text', '材料提取结果', []],
] as const)('%s 待审核入口属于当前阶段且隐藏后续阶段', async (stage, label, previous) => {
  setup(stage, 'waiting_review', false, {
    checkpointEnabled: true, stageStatus: 'waiting_review',
    configJson: { firstStepOutput: extraction },
  })
  await screen.findByText('run')
  const user = userEvent.setup()
  const reviewAction = await findRunInlineAction('审核')
  for (const section of ['材料提取结果', '需求理解记录']) {
    const reached = section === label || (previous as readonly string[]).includes(section)
    expect(Boolean(screen.queryByRole('button', { name: section }))).toBe(reached)
  }
  await user.click(reviewAction)
  expect(await screen.findByRole('dialog', { name: stage === 'extracting_text' ? '材料提取结果' : '审核' })).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: '业务内容' }).closest('label')).toHaveClass('ant-segmented-item-selected')
  expect(screen.getByRole('button', { name: '审核通过并继续' })).toBeInTheDocument()
})

it('已完成的材料提取入口只查看对应产物', async () => {
  setup('feature_understanding', 'success', false, {
    checkpointEnabled: true, stageStatus: 'completed', configJson: { firstStepOutput: extraction },
  })
  await userEvent.setup().click(await screen.findByRole('button', { name: '材料提取结果' }))
  expect(await screen.findByRole('dialog', { name: '材料提取结果' })).toBeInTheDocument()
  expect(screen.getByRole('region', { name: '材料与提取结果对照' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '审核通过并继续' })).toBeNull()
})

it.each(['pending', 'running'] as const)('%s 时隐藏尚未执行的后续阶段', async status => {
  setup('extracting_text', status, false, { stageStatus: status })
  await screen.findByText('run')
    expect(screen.queryByRole('button', { name: '需求理解记录' })).toBeNull()
})

it('继续优化在同一审核窗口展开，取消后保留内容和优化草稿', async () => {
  setup('extracting_text', 'waiting_review', false, {
    checkpointEnabled: true, stageStatus: 'waiting_review',
    configJson: { firstStepOutput: extraction },
  })
  const user = userEvent.setup()
  await user.click(await findRunInlineAction('审核'))
  const dialog = within(screen.getByRole('dialog'))
  await user.click(dialog.getByRole('radio', { name: 'JSON' }).closest('label')!)
  const originalEditor = document.querySelector('.cm-content')
  await user.click(dialog.getByRole('button', { name: '继续优化' }))
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  expect(dialog.queryByRole('button', { name: '保存修改' })).not.toBeInTheDocument()
  expect(dialog.queryByRole('button', { name: '审核通过并继续' })).not.toBeInTheDocument()
  expect(dialog.getByRole('button', { name: '提交优化' }).closest('.ant-modal-footer')).not.toBeNull()
  expect(dialog.getByRole('button', { name: '取消优化' }).closest('.ant-modal-footer')).not.toBeNull()
  expect(dialog.queryByRole('button', { name: '继续优化' })).not.toBeInTheDocument()
  expect(document.querySelector('.cm-content')).toBe(originalEditor)
  expect(originalEditor).toHaveTextContent('document_extraction')
  await user.clear(dialog.getByLabelText('优化指令'))
  await user.type(dialog.getByLabelText('优化指令'), '补充异常分支')
  await user.click(dialog.getByRole('button', { name: '取消优化' }))
  expect(document.querySelector('.cm-content')).toBe(originalEditor)
  expect(dialog.getByRole('button', { name: '保存修改' })).toBeInTheDocument()
  await user.click(dialog.getByRole('button', { name: '继续优化' }))
  expect(dialog.getByLabelText('优化指令')).toHaveValue('补充异常分支')
  expect(dialog.getByLabelText('本次使用的模型')).toBeInTheDocument()
})

it('右侧提交使用所选模型并携带左侧未保存的需求修改', async () => {
  setup('extracting_text', 'waiting_review', false, {
    checkpointEnabled: true, stageStatus: 'waiting_review', configJson: { firstStepOutput: extraction },
  })
  const previousFetch = vi.mocked(globalThis.fetch).getMockImplementation()!
  let body: Record<string, unknown> | undefined
  vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
    if (String(input).includes('/stage-revise')) {
      body = JSON.parse(String(init?.body))
      return response({ runId: 'run', status: 'pending', currentStage: 'extracting_text', stageStatus: 'pending' })
    }
    return previousFetch(input, init)
  })
  const user = userEvent.setup()
  await user.click(await findRunInlineAction('审核'))
  const dialog = within(screen.getByRole('dialog'))
  await user.click(dialog.getByRole('radio', { name: 'JSON' }).closest('label')!)
  const editor = document.querySelector('.cm-content') as HTMLElement
  await user.click(editor)
  await user.keyboard('{Control>}a{/Control}')
  const revised = { ...extraction, documentTitle: '尚未保存的新材料', questions: [
    { ...extraction.questions[0], id: 'Q09', question: '未保存的新增问题？' },
    { ...extraction.questions[1], status: 'resolved' },
  ] }
  await user.paste(JSON.stringify(revised))
  await user.click(dialog.getByRole('button', { name: '继续优化' }))
  expect((dialog.getByLabelText('优化指令') as HTMLTextAreaElement).value).toContain('【Q09】未保存的新增问题？')
  expect((dialog.getByLabelText('优化指令') as HTMLTextAreaElement).value).not.toContain(extraction.questions[1].question)
  await user.clear(dialog.getByLabelText('优化指令'))
  await user.type(dialog.getByLabelText('优化指令'), '补充异常处理')
  await user.click(dialog.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(body).toMatchObject({ llmConnectionId: 'mine', revisionInstruction: '补充异常处理', configJson: { firstStepOutput: revised } }))
})

it.each(['extracting_text', 'completed'] as const)('%s 优化预填当前待确认问题，原样模板不能提交', async stage => {
  setup(stage, stage === 'extracting_text' ? 'waiting_review' : 'success', false, {
    checkpointEnabled: true, stageStatus: stage === 'extracting_text' ? 'waiting_review' : 'completed',
  })
  const previousFetch = vi.mocked(globalThis.fetch).getMockImplementation()!
  let submitted: Record<string, unknown> | undefined
  vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
    if (String(input).includes('/stage-revise')) {
      submitted = JSON.parse(String(init?.body))
      return response(null, 500)
    }
    return previousFetch(input, init)
  })
  const user = userEvent.setup()
  await user.click(await findRunInlineAction('审核'))
  const dialog = within(screen.getByRole('dialog'))
  await user.click(dialog.getByRole('button', { name: '继续优化' }))
  const artifact = stage === 'extracting_text' ? extraction : understanding
  const instruction = dialog.getByLabelText('优化指令') as HTMLTextAreaElement
  for (const question of artifact.questions) {
    expect(instruction.value).toContain(`【${question.id}】${question.question}`)
  }
  expect(instruction.value.match(/答复：\[请填写已确认的信息\]/g)).toHaveLength(artifact.questions.length)
  expect(instruction.value).toContain('未填写或仍为占位文字的项目继续保留为待确认，不要推测答案')
  await waitFor(() => expect(dialog.getByRole('button', { name: '提交优化' })).toBeEnabled())
  await user.click(dialog.getByRole('button', { name: '提交优化' }))
  expect(await screen.findByText('请补充已确认的信息，或填写其他优化要求')).toBeInTheDocument()
  expect(vi.mocked(globalThis.fetch).mock.calls.some(([input]) => String(input).includes('/stage-revise'))).toBe(false)
  const answered = instruction.value.replace('答复：[请填写已确认的信息]', '答复：本题已确认的信息')
  await user.clear(instruction)
  await user.click(instruction)
  await user.paste(answered)
  await user.click(dialog.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(submitted).toMatchObject({
    stage: stage === 'extracting_text' ? 'extracting_text' : 'feature_understanding',
    llmConnectionId: 'mine', revisionInstruction: answered,
  }))
  if (stage === 'extracting_text') expect(submitted?.configJson).toEqual({ firstStepOutput: extraction })
  else expect(submitted?.resultYaml).toBe(JSON.stringify(understanding, null, 2))
  await waitFor(() => expect(dialog.getByRole('button', { name: '提交优化' })).toBeEnabled())
  expect(instruction).toHaveValue(answered)
})

it('没有待确认问题时优化指令留空，手写要求可保留', async () => {
  setup('completed', 'success', false, { checkpointEnabled: true, stageStatus: 'completed', resultYaml: JSON.stringify({ ...understanding, questions: [] }) })
  const user = userEvent.setup()
  await user.click(await findRunInlineAction('审核'))
  const dialog = within(screen.getByRole('dialog'))
  await user.click(dialog.getByRole('button', { name: '继续优化' }))
  expect(dialog.getByLabelText('优化指令')).toHaveValue('')
  await user.type(dialog.getByLabelText('优化指令'), '进一步整理业务规则')
  await user.click(dialog.getByRole('button', { name: '取消优化' }))
  await user.click(dialog.getByRole('button', { name: '继续优化' }))
  expect(dialog.getByLabelText('优化指令')).toHaveValue('进一步整理业务规则')
})


it('删除运行记录需确认，且只删除该次运行', async () => {
  const deleted: string[] = []
  setup('feature_understanding', 'success')
  const user = userEvent.setup()
  vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://localhost').pathname
    if (init?.method === 'DELETE') {
      deleted.push(path)
      return response({})
    }
    if (path.includes('/integrations/llm/connections')) return response({ items: [], total: 0 })
    if (path === '/v1/requirement-analysis-tasks/task') return response({ taskId: 'task', projectId: 'project-1', name: '需求分析', sourceType: 'text' })
    if (path.endsWith('/runs')) return response({ items: [{ runId: 'run', taskId: 'task', status: 'success', currentStage: 'feature_understanding', reviewStatus: 'pending' }], total: 1 })
    if (path === '/v1/requirement-analysis-runs/run') return response({ runId: 'run', taskId: 'task', status: 'success', currentStage: 'feature_understanding', reviewStatus: 'pending' })
    return response({ items: [], total: 0 })
  })
  await screen.findByText('run')

  await user.click(await screen.findByRole('button', { name: '删除运行记录' }))
  const confirm = await findDeleteConfirm()
  expect(deleted).toEqual([])
  await user.click(within(confirm).getByRole('button', { name: /^删\s*除$/ }))
  await waitFor(() => expect(deleted).toEqual(['/v1/requirement-analysis-runs/run']))
})

it('运行中的记录没有可用的删除入口', async () => {
  setup('extracting_text', 'running', false, { stageStatus: 'running' })
  expect(await screen.findByRole('button', { name: '删除运行记录' })).toBeDisabled()
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

it.each(['feature_understanding', 'completed'] as const)('%s 两阶段运行可审核且默认按业务内容阅读', async stage => {
  const artifact = {
    schemaVersion: '1.0', artifactType: 'requirement_understanding', title: '模块使用理解',
    sources: [], questions: [], modules: [],
  }
  setup(stage, 'success', false, {
    workflowVersion: 2, snapshotJson: { workflowVersion: 2 }, checkpointEnabled: true,
    stageStatus: 'completed', resultYaml: JSON.stringify(artifact),
    configJson: { firstStepOutput: { schemaVersion: '1.0', artifactType: 'document_extraction', sources: [], questions: [], contentBlocks: [] } },
  })
  const row = await findRunRow()
  expect(within(row).getByRole('button', { name: '材料提取结果' })).toBeVisible()
  expect(within(row).queryByRole('button', { name: '需求流程稿' })).toBeNull()
  await userEvent.setup().click(await findRunInlineAction('审核'))
  expect(await screen.findByRole('radio', { name: '业务内容' })).toBeChecked()
  await userEvent.setup().click(screen.getByRole('radio', { name: 'JSON' }).closest('label')!)
  expect(await screen.findByLabelText('阶段产物 JSON')).toBeVisible()
  expect(screen.getByRole('button', { name: '审核通过' })).toBeVisible()
  expect(screen.getByRole('button', { name: '审核不通过' })).toBeVisible()
  expect(screen.getByRole('button', { name: '继续优化' })).toBeVisible()
})


it.each(['feature_understanding', 'completed'] as const)('已拒绝的 %s 结果不再显示审核入口或审核操作', async stage => {
  setup(stage, 'success', false, {checkpointEnabled:true,stageStatus:'completed',reviewStatus:'rejected',errorMessage:''})
  const user=userEvent.setup()
  const row=await findRunRow()
  expect(within(row).getByText('已拒绝')).toBeVisible()
  expect(within(row).queryByRole('button',{name:/^审\s*核$/})).toBeNull()
  expect(within(row).queryByRole('button',{name:'更多操作'})).toBeNull()
  await user.click(within(row).getByRole('button',{name:'需求理解记录'}))
  const dialogs=await screen.findAllByRole('dialog')
  const dialog=dialogs.find(node=>node.querySelector('.requirement-analysis-artifact-tabs'))
  if (!dialog) throw new Error('未找到运行产物弹框')
  expect(within(dialog).queryByRole('button',{name:'审核通过'})).toBeNull()
  expect(within(dialog).queryByRole('button',{name:'审核不通过'})).toBeNull()
  expect(within(dialog).queryByRole('button',{name:'导入需求'})).toBeNull()
  expect(within(dialog).queryByRole('button',{name:'保存修改'})).toBeNull()
  expect(within(dialog).queryByRole('button',{name:'继续优化'})).toBeNull()
  await user.click(within(dialog).getByRole('radio', { name: 'JSON' }).closest('label')!)
  expect(within(dialog).getByRole('textbox',{name:'阶段产物 JSON'})).toHaveAttribute('aria-readonly','true')
})


it.each([
  {stage:'extracting_text',status:'waiting_review',stageStatus:'waiting_review'},
  {stage:'feature_understanding',status:'error',stageStatus:'failed'},
] as const)('已拒绝的 $stage / $status 只保留查看和删除入口', async ({stage,status,stageStatus}) => {
  setup(stage,status,false,{checkpointEnabled:true,stageStatus,reviewStatus:'rejected',errorMessage:''})
  const user=userEvent.setup()
  const row=await findRunRow()
  expect(within(row).queryByRole('button',{name:/^审\s*核$/})).toBeNull()
  expect(within(row).queryByRole('button',{name:'更多操作'})).toBeNull()
  expect(screen.queryByRole('button',{name:'重试阶段'})).toBeNull()
  expect(screen.getByRole('button',{name:'删除运行记录'})).toBeEnabled()
  await user.keyboard('{Escape}')
  await user.click(within(row).getByRole('button',{name:'材料提取结果'}))
  const dialogs=await screen.findAllByRole('dialog')
  const dialog=dialogs.find(node=>node.querySelector('.requirement-analysis-artifact-tabs'))
  if (!dialog) throw new Error('未找到运行产物弹框')
  expect(within(dialog).queryByRole('button',{name:'保存修改'})).toBeNull()
  expect(within(dialog).queryByRole('button',{name:'继续优化'})).toBeNull()
  expect(within(dialog).queryByRole('button',{name:'审核通过并继续'})).toBeNull()
})


it('首次点击较早的已拒绝运行即可打开只读产物，不被运行切换关闭', async () => {
  const latest: RequirementAnalysisTaskRun={runId:'new-run',taskId:'task',status:'waiting_review',currentStage:'extracting_text',stageStatus:'waiting_review',reviewStatus:'pending',checkpointEnabled:true,configJson:{firstStepOutput:extraction},resultYaml:''}
  setup('completed','success',false,{checkpointEnabled:true,stageStatus:'completed',reviewStatus:'rejected',errorMessage:''},[latest])
  const user=userEvent.setup()
  const row=await findRunRow()
  const latestRow=(await screen.findByText('new-run')).closest('tr')
  if(!latestRow)throw new Error('未找到新运行')
  await user.click(within(latestRow).getByRole('button',{name:/^审\s*核$/}))
  await screen.findByRole('button',{name:'审核通过并继续'})
  await user.click(screen.getByRole('button',{name:/^关\s*闭$/}))
  await waitFor(()=>expect(document.querySelector('.requirement-analysis-artifact-tabs')).toBeNull())
  await user.click(within(row).getByRole('button',{name:'需求理解记录'}))
  await waitFor(()=>expect(screen.getAllByRole('dialog').some(node=>node.querySelector('.requirement-analysis-artifact-tabs'))).toBe(true))
  await waitFor(()=>expect(screen.getByRole('region',{name:'材料与需求理解对照'})).toBeVisible())
  expect(screen.queryByRole('button',{name:'审核通过'})).toBeNull()
})


it('需求详情直接打开既有审核工作区，隐藏旧任务页面', async () => {
  setup('feature_understanding', 'success', false, { stageStatus: 'completed', errorMessage: '' }, [], true)
  await screen.findByRole('button', { name: /^审核通过$/ })
  expect(screen.queryByText('返回需求分析')).not.toBeInTheDocument()
  expect(screen.getByRole('region', { name: '业务内容' })).toBeInTheDocument()
})
