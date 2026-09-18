import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ThemeProvider } from '@/app/providers/ThemeProvider'
import type { RequirementAnalysisTaskRun } from '../types'
import { RequirementAnalysisTaskDetailPage } from './RequirementAnalysisTaskDetailPage'

const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks() })
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

it.each(['extracting_text', 'writing_requirement', 'feature_understanding'] as const)('重试 %s 并刷新为等待执行', async stage => {
  const submit = setup(stage)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '重试阶段' }))
  await waitFor(() => expect(submit).toHaveBeenCalledExactlyOnceWith({ stage, llmConnectionId: 'mine' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: '重试阶段' })).toBeNull())
})

it('提交失败后保留重试入口', async () => {
  const submit = setup('extracting_text', 'error', true)
  await userEvent.setup().click(await screen.findByRole('button', { name: '重试阶段' }))
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(screen.getByRole('button', { name: '重试阶段' }).hasAttribute('disabled')).toBe(false))
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
  const button = await screen.findByRole('button', { name: '重试阶段' })
  await user.click(button)
  await waitFor(() => expect(button.hasAttribute('disabled')).toBe(true))
  await user.click(button)
  expect(submit).toHaveBeenCalledTimes(1)
  resolve(response(null, 500))
  await waitFor(() => expect(button.hasAttribute('disabled')).toBe(false))
})


it.each([
  ['extracting_text', ['增强文本']],
  ['writing_requirement', ['增强文本', '需求流程稿']],
  ['feature_understanding', ['增强文本', '需求流程稿', '需求理解记录']],
] as const)('失败在 %s 时只显示已执行到的阶段入口', async (stage, visible) => {
  setup(stage)
  await screen.findByRole('button', { name: '重试阶段' })
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
  const review = screen.getByRole('button', { name: `${label}（审核）` })
  for (const section of ['增强文本', '需求流程稿', '需求理解记录']) {
    expect(Boolean(screen.queryByRole('button', { name: section }))).toBe((previous as readonly string[]).includes(section))
  }
  expect(screen.queryByRole('button', { name: '审核' })).toBeNull()
  await userEvent.setup().click(review)
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
  await user.click(await screen.findByRole('button', { name: '需求流程稿（审核）' }))
  const originalEditor = document.querySelector('.cm-content')
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  expect(screen.queryByRole('button', { name: '保存修改' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '审核通过并继续' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '提交优化' }).closest('.ant-modal-footer')).not.toBeNull()
  expect(screen.getByRole('button', { name: '取消优化' }).closest('.ant-modal-footer')).not.toBeNull()
  expect(screen.queryByRole('button', { name: '继续优化' })).not.toBeInTheDocument()
  expect(document.querySelector('.cm-content')).toBe(originalEditor)
  expect(originalEditor).toHaveTextContent('当前需求流程稿')
  await user.type(screen.getByRole('textbox', { name: '优化指令' }), '补充异常分支')
  await user.click(screen.getByRole('button', { name: '取消优化' }))
  expect(document.querySelector('.cm-content')).toBe(originalEditor)
  expect(screen.getByRole('button', { name: '保存修改' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  expect(screen.getByRole('textbox', { name: '优化指令' })).toHaveValue('补充异常分支')
  expect(screen.getByRole('combobox', { name: '本次使用的模型' })).toBeInTheDocument()
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
  await user.click(await screen.findByRole('button', { name: '需求流程稿（审核）' }))
  const editor = document.querySelector('.cm-content') as HTMLElement
  await user.click(editor)
  await user.keyboard('{Control>}a{/Control}')
  await user.paste('尚未保存的新流程')
  await user.click(screen.getByRole('button', { name: '继续优化' }))
  await user.type(screen.getByRole('textbox', { name: '优化指令' }), '补充异常处理')
  await user.click(screen.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(body).toMatchObject({ llmConnectionId: 'mine', revisionInstruction: '补充异常处理', configJson: { secondStepOutput: '尚未保存的新流程' } }))
})
