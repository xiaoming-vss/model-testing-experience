import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { aiTestingApi } from '../api/aiTesting.api'
import { UiGenerationInputsModal } from './UiGenerationInputsModal'
import { UiGenerationSourceTrace } from './UiGenerationSourceTrace'

vi.mock('@/features/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => true }) }))
vi.mock('../api/aiTesting.api', () => ({ aiTestingApi: {
  getUiCaseGenerateTask: vi.fn(), uploadUiCaseGenerateTaskSourceArchive: vi.fn(),
} }))
const task = { name: 'UI', taskId: 'task', sourceType: 'source_archive' as const, instruction: '',
  sourceArchive: { archiveId: 'archive', fileId: 'file', filename: 'source.zip', sizeBytes: 2, sha256: 'hash', uploadedAt: '' } }
const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks() })
beforeEach(() => {
  vi.mocked(aiTestingApi.getUiCaseGenerateTask).mockResolvedValue(task)
  vi.mocked(aiTestingApi.uploadUiCaseGenerateTaskSourceArchive).mockReset()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const path = new URL(String(input), 'http://localhost').pathname
    const rows = path.endsWith('/function-test-suites') ? [{ suiteId: 'suite', name: '功能' }]
      : [{ caseId: 'c1', title: '转换成功' }, { caseId: 'c2', title: '转换失败' }]
    return new Response(JSON.stringify({ code: 0, data: { items: rows, total: rows.length } }), { headers: { 'Content-Type': 'application/json' } })
  })
})
function mount(refreshInputs = false, onSubmit = vi.fn(async () => undefined)) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  const onClose = vi.fn()
  render(<TestThemeProvider><QueryClientProvider client={client}>
    <UiGenerationInputsModal requirementId="req" projectId="project" taskId="task" refreshInputs={refreshInputs}
      source={refreshInputs ? { archive: { filename: 'old.zip' }, cases: [{ caseId: 'c2', title: '历史标题' }] } : undefined}
      onSubmit={onSubmit} onClose={onClose} />
  </QueryClientProvider></TestThemeProvider>)
  return { onClose, onSubmit }
}
it('首次生成默认全选正式用例，调整选择后提交明确的编号', async () => {
  const { onSubmit, onClose } = mount()
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByRole('button', { name: '开始生成' })).toBeEnabled())
  expect(screen.getByText('source.zip')).toBeInTheDocument()
  await user.click(screen.getByRole('checkbox', { name: '选择用例：转换失败' }))
  await user.click(screen.getByRole('button', { name: '开始生成' }))
  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ refreshInputs: false, functionCaseIds: ['c1'] }))
  expect(onClose).toHaveBeenCalled()
})
it('更换输入沿用原选择，上传失败保留选择且不派发，重试成功后再派发', async () => {
  vi.mocked(aiTestingApi.uploadUiCaseGenerateTaskSourceArchive)
    .mockRejectedValueOnce(new Error('源码上传失败'))
    .mockResolvedValueOnce({ ...task, sourceArchive: { ...task.sourceArchive, filename: 'new.zip' } })
  const { onSubmit } = mount(true)
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByRole('button', { name: '从元素控件清单重新生成' })).toBeEnabled())
  expect(screen.getByRole('checkbox', { name: '选择用例：转换成功' })).not.toBeChecked()
  await user.upload(document.querySelector('input[type=file]')!, new File(['zip'], 'new.zip', { type: 'application/zip' }))
  await user.click(screen.getByRole('button', { name: '从元素控件清单重新生成' }))
  expect(await screen.findByText('源码上传失败')).toBeInTheDocument()
  expect(onSubmit).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: '从元素控件清单重新生成' }))
  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ refreshInputs: true, functionCaseIds: ['c2'] }))
})
it('清空选择禁止生成', async () => {
  mount()
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByRole('button', { name: '开始生成' })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: '清空选择' }))
  expect(screen.getByRole('button', { name: '开始生成' })).toBeDisabled()
})
it('追溯展示冻结的文件和用例正文，缺失历史来源不冒充需求材料', async () => {
  const { rerender } = render(<TestThemeProvider><UiGenerationSourceTrace source={{ archive: { filename: 'old.zip', fileId: 'old' },
    cases: [{ caseId: 'c1', title: '旧标题', content: { steps: ['原始操作'] } }] }} /></TestThemeProvider>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '查看源码和功能用例快照' }))
  expect(await screen.findByRole('region', { name: '生成输入快照' })).toHaveTextContent('old.zip')
  expect(screen.getByText(/原始操作/)).toBeInTheDocument()
  rerender(<TestThemeProvider><UiGenerationSourceTrace /></TestThemeProvider>)
  expect(screen.getByText('历史来源未记录')).toBeInTheDocument()
  expect(screen.queryByText('需求材料')).not.toBeInTheDocument()
})
