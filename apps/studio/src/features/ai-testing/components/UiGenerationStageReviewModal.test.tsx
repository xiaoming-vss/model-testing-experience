import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { seedOwnerProject } from '@/test/projectAccess'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import type { UiCaseGenerateTaskRun } from '../types'
import { UiGenerationStageReviewModal } from './UiGenerationStageReviewModal'

vi.mock('@/shared/components/TextCodeEditor/TextCodeEditor', () => ({
  TextCodeEditor: ({ value, onChange, ariaLabel, readOnly }: { value: string; onChange: (value: string) => void; ariaLabel: string; readOnly: boolean }) =>
    <textarea aria-label={ariaLabel} value={value} onChange={event => onChange(event.target.value)} readOnly={readOnly} />,
}))
const surface = { schemaVersion: 'ui_test_surface/1.0', pages: [], controls: [], unknowns: [] }
const initial: UiCaseGenerateTaskRun = {
  runId: 'ui-run', projectId: 'project-1', status: 'waiting_review', checkpointEnabled: true,
  currentStage: 'ui_surface', stageStatus: 'waiting_review', reviewStatus: 'pending', importStatus: 'pending',
  importedTargets: [], importedAt: null,
  configJson: { uiSurface: surface },
}
function response(data: unknown) { return new Response(JSON.stringify({ code: 0, message: 'ok', data }), { status: 200 }) }
function mount(
  run = initial,
  handle?: (url: string, init?: RequestInit) => Response | undefined,
  stage?: 'ui_surface' | 'ui_design' | 'ui_yaml',
  onClose = vi.fn(),
) {
  const requests: { url: string; body: Record<string, unknown> }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (init?.body) requests.push({ url, body: JSON.parse(String(init.body)) })
    const value = handle?.(url, init)
    if (value) return value
    if (url.includes('/integrations/llm/connections')) return response({ items: [{ connectionId: 'llm-1', name: '本人模型', status: 'active' }] })
    return response(run)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  seedOwnerProject(client)
  function Host() {
    const [current, setCurrent] = useState(run)
    return <UiGenerationStageReviewModal open run={current} projectId="project-1" stage={stage}
      onClose={onClose} onUpdated={setCurrent} onDirtyChange={() => {}} />
  }
  render(<TestThemeProvider><QueryClientProvider client={client}><MemoryRouter><Host /></MemoryRouter></QueryClientProvider></TestThemeProvider>)
  return { requests, onClose }
}
async function showRaw(label: 'JSON' | 'YAML' = 'JSON') {
  await userEvent.click(screen.getByRole('radio', { name: label }).closest('label')!)
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('defaults to the visual view and keeps a JSON switch', async () => {
  const richSurface = {
    schemaVersion: 'ui_test_surface/1.0',
    pages: [{ pageId: 'page_retrieval', title: '数据检索', route: '/data-management/retrieval' }],
    controls: [{ controlId: 'ctl_convert', pageId: 'page_retrieval', semanticName: '转换数据', controlType: 'button', sourceRef: 'retrieval/index.vue:822', locatorCandidates: [{ locatorType: 'xpath', locatorValue: "//button[normalize-space(.)='转换数据']" }] }],
    unknowns: [],
  }
  mount({ ...initial, configJson: { uiSurface: richSurface } })
  expect(await screen.findByRole('heading', { name: /数据检索/ })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '转换数据' })).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: '元素控件清单 JSON' })).not.toBeInTheDocument()
  await showRaw()
  expect(await screen.findByRole('textbox', { name: '元素控件清单 JSON' })).toBeInTheDocument()
  await userEvent.click(screen.getByRole('radio', { name: '可视化' }).closest('label')!)
  expect(screen.queryByRole('textbox', { name: '元素控件清单 JSON' })).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '转换数据' })).toBeInTheDocument()
})

it('shows JSON directly and saves only the current stage artifact', async () => {
  const { requests } = mount()
  await showRaw()
  const editor = await screen.findByRole('textbox', { name: '元素控件清单 JSON' })
  expect(editor).toHaveValue(JSON.stringify(surface, null, 2))
  expect(screen.queryByText('结构化预览')).not.toBeInTheDocument()
  const edited = { ...surface, unknowns: [{ topic: '按钮定位待补' }] }
  fireEvent.change(editor, { target: { value: JSON.stringify(edited) } })
  await userEvent.click(screen.getByRole('button', { name: /^保\s*存$/ }))
  await waitFor(() => expect(requests[0]).toEqual({ url: '/v1/ui-case-generate-task-runs/ui-run/stage-output', body: { stage: 'ui_surface', configJson: { uiSurface: edited } } }))
})

it('keeps the review comment and stage actions in the modal footer', async () => {
  mount()
  const modal = await screen.findByRole('dialog')
  const footer = within(modal.querySelector<HTMLElement>('.ant-modal-footer')!)
  expect(footer.getByRole('textbox', { name: '审核备注' })).toBeInTheDocument()
  for (const name of [/^关\s*闭$/, /^保\s*存$/, '继续优化', '审核不通过', '审核通过并继续']) {
    expect(footer.getByRole('button', { name })).toBeInTheDocument()
  }
  expect(modal.querySelector('.ant-modal-body')?.querySelector('textarea[aria-label="审核备注"]')).toBeNull()
  expect(modal.querySelector('.ui-generation-stage-actions')).toBeNull()
})

it('waits for explicit approval and a chosen personal model before continuing', async () => {
  const next = { ...initial, currentStage: 'ui_design', status: 'pending' }
  const { requests } = mount(initial, (url) => url.endsWith('/review-stage') ? response(next) : undefined)
  expect(requests).toHaveLength(0)
  await userEvent.click(await screen.findByRole('button', { name: '审核通过并继续' }))
  expect(requests).toHaveLength(0)
  await userEvent.click(await screen.findByText('本人模型'))
  await userEvent.click(screen.getByRole('button', { name: '确认运行' }))
  await waitFor(() => expect(requests[0]?.body).toEqual({ stage: 'ui_surface', reviewComment: '', llmConnectionId: 'llm-1', action: 'approve' }))
  await showRaw()
  expect(await screen.findByRole('textbox', { name: 'UI 用例设计 JSON' })).toHaveValue('')
})

it('rejects invalid JSON locally before saving', async () => {
  const { requests } = mount()
  await showRaw()
  fireEvent.change(await screen.findByRole('textbox', { name: '元素控件清单 JSON' }), { target: { value: '{invalid' } })
  await userEvent.click(screen.getByRole('button', { name: /^保\s*存$/ }))
  expect(requests).toHaveLength(0)
  expect(screen.getByRole('alert')).toBeInTheDocument()
})

it('shows YAML with missingFields directly for final review', async () => {
  const raw = '- name: 示例\n  stepsJson:\n    - missingFields: []\n'
  mount({ ...initial, status: 'success', currentStage: 'completed', resultYaml: raw })
  await showRaw('YAML')
  expect(await screen.findByRole('textbox', { name: '用例 YAML YAML' })).toHaveValue(raw)
  expect(screen.getByRole('button', { name: '批准 YAML' })).toBeEnabled()
})

it('offers retry only for the failed current stage', async () => {
  mount({ ...initial, status: 'failed', currentStage: 'ui_design', errorMessage: '模型超时' })
  expect(await screen.findByRole('button', { name: '重试本阶段' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: '审核通过并继续' })).not.toBeInTheDocument()
})

it('still explains a failure when the worker returned no reason', async () => {
  mount({ ...initial, status: 'failed', currentStage: 'ui_design', errorMessage: '' })
  expect(await screen.findByText('阶段执行失败，Worker 未返回具体原因')).toBeInTheDocument()
})

it('opens the stage requested by the artifact entry instead of the current stage', async () => {
  mount({ ...initial, currentStage: 'ui_design', configJson: { uiSurface: surface, uiDesign: { schemaVersion: 'ui_test_scenarios/2.0' } } }, undefined, 'ui_surface')
  await showRaw()
  expect(await screen.findByRole('textbox', { name: '元素控件清单 JSON' })).toHaveValue(JSON.stringify(surface, null, 2))
  expect(screen.queryByRole('button', { name: '审核通过并继续' })).not.toBeInTheDocument()
  expect(screen.getByText('元素控件清单', { selector: '.ant-modal-title' })).toBeInTheDocument()
})

it('uses the revision side panel without image attachments for UI stages', async () => {
  const { requests } = mount()
  await userEvent.click(await screen.findByRole('button', { name: '继续优化' }))
  expect(await screen.findByRole('complementary', { name: '继续优化' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '添加图片' })).not.toBeInTheDocument()
  await userEvent.type(screen.getByRole('textbox', { name: '优化指令' }), '补充登录按钮定位')
  await userEvent.click(screen.getByRole('button', { name: '提交优化' }))
  await waitFor(() => expect(requests[0]?.body).toEqual({
    stage: 'ui_surface',
    reviewComment: '',
    llmConnectionId: 'llm-1',
    configJson: { uiSurface: surface },
    revisionInstruction: '补充登录按钮定位',
  }))
})

it('shows the rejection reason and offers no further stage action', async () => {
  mount({ ...initial, status: 'canceled', reviewComment: '定位证据不足' })
  expect(await screen.findByText('本阶段已拒绝')).toBeInTheDocument()
  expect(screen.getByText('定位证据不足')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '审核通过并继续' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '重试本阶段' })).not.toBeInTheDocument()
})


it('shows advisory findings without blocking approval and offers explicit revision', async () => {
  const yaml = '- name: 登录\n  enabled: true\n  orderNo: 1\n  stepsJson: []\n'
  const run = { ...initial, currentStage: 'completed', status: 'success', resultYaml: yaml,
    resultSummaryJson: { uiSemanticReview: { status: 'completed', modules: [{ module: '登录模块', status: 'completed', issues: [
      { caseIndex: 1, caseName: '登录', stepIndex: 1, evidence: '原目标要求核对用户名', repair: '保留用户名断言' },
    ] }] } } }
  mount(run)
  expect(await screen.findByText('AI 复核提出 1 条建议，由你决定是否修改')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '批准 YAML' })).toBeEnabled()
  fireEvent.click(screen.getByText('查看复核详情'))
  await userEvent.click(screen.getByRole('button', { name: '带入继续优化' }))
  expect((screen.getByDisplayValue(/请核查以下 AI 复核意见/) as HTMLTextAreaElement).value).toContain('保留用户名断言')
})

it('marks advisory evidence stale while editing and preserves the candidate on incomplete review', async () => {
  const yaml = '- name: 登录\n  enabled: true\n  orderNo: 1\n  stepsJson: []\n'
  mount({ ...initial, currentStage: 'completed', status: 'success', resultYaml: yaml,
    resultSummaryJson: { uiSemanticReview: { status: 'incomplete', modules: [{ module: '登录模块', status: 'incomplete', errorCode: 'timeout', issues: [] }] } } })
  expect(await screen.findByText('AI 复核未完成，已保留用例草稿')).toBeInTheDocument()
  await showRaw('YAML')
  const editor = screen.getByRole('textbox', { name: /YAML/ })
  expect(editor).toHaveValue(yaml)
  fireEvent.change(editor, { target: { value: yaml + '# 修改' } })
  expect(await screen.findByText('草稿已修改，以下复核意见仅供参考')).toBeInTheDocument()
})
