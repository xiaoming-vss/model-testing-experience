import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { aiTestingApi } from '../api/aiTesting.api'
import { requirementDesignApi } from '../api/requirementDesign.api'
import { UiGenerationSourcePanel } from './UiGenerationSourcePanel'

vi.mock('../api/aiTesting.api', () => ({ aiTestingApi: { getUiCaseGenerateTask: vi.fn(), uploadUiCaseGenerateTaskSourceArchive: vi.fn() } }))
vi.mock('../api/requirementDesign.api', () => ({ requirementDesignApi: { configure: vi.fn() } }))
const task = { taskId: 'task', name: 'UI', sourceType: 'source_archive' as const, instruction: '',
  sourceArchive: { archiveId: 'archive', fileId: 'file', filename: 'source.zip', sizeBytes: 3, sha256: '', uploadedAt: '' } }
const clients: QueryClient[] = []
beforeEach(() => {
  vi.mocked(aiTestingApi.getUiCaseGenerateTask).mockResolvedValue(task)
  vi.mocked(aiTestingApi.uploadUiCaseGenerateTaskSourceArchive).mockResolvedValue({ ...task, sourceArchive: { ...task.sourceArchive, filename: 'new.zip' } })
  vi.mocked(requirementDesignApi.configure).mockResolvedValue({ taskId: 'task', name: 'UI', sourceType: 'source_archive', sourceContent: '', instruction: '' })
})
afterEach(() => { cleanup(); clients.splice(0).forEach(client => client.clear()); vi.resetAllMocks() })
function mount(props: Partial<React.ComponentProps<typeof UiGenerationSourcePanel>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  const onSaved = vi.fn()
  render(<TestThemeProvider><QueryClientProvider client={client}><UiGenerationSourcePanel requirementId="req" canWrite busy={false} onSaved={onSaved} {...props} /></QueryClientProvider></TestThemeProvider>)
  return { user: userEvent.setup(), onSaved }
}
async function pick(user: ReturnType<typeof userEvent.setup>) {
  const file = new File(['zip'], 'new.zip', { type: 'application/zip' })
  await user.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!, file)
  return file
}
it('未配置时保存源码包创建 UI 设置并上传文件', async () => {
  const { user, onSaved } = mount()
  const file = await pick(user)
  expect(requirementDesignApi.configure).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: '保存源码包' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(requirementDesignApi.configure).toHaveBeenCalledWith('req', 'ui', { requestId: expect.any(String), newConfiguration: false })
  expect(aiTestingApi.uploadUiCaseGenerateTaskSourceArchive).toHaveBeenCalledWith('task', file, expect.any(Function))
  expect(screen.getByRole('status')).toHaveTextContent('源码包已保存')
})
it('已配置时替换当前源码包，保留任务身份', async () => {
  const { user, onSaved } = mount({ taskId: 'task' })
  await screen.findByText('source.zip')
  expect(screen.getByRole('button', { name: '替换源码包' })).toBeEnabled()
  await pick(user)
  await user.click(screen.getByRole('button', { name: '保存源码包' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(requirementDesignApi.configure).not.toHaveBeenCalled()
  expect(screen.getByRole('status')).toHaveTextContent('源码包已保存')
})
it('上传失败可重试，不重复创建设置', async () => {
  vi.mocked(aiTestingApi.uploadUiCaseGenerateTaskSourceArchive).mockRejectedValueOnce(new Error('上传失败'))
  const { user, onSaved } = mount()
  await pick(user)
  await user.click(screen.getByRole('button', { name: '保存源码包' }))
  await screen.findByText('上传失败')
  expect(onSaved).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: '保存源码包' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(requirementDesignApi.configure).toHaveBeenCalledOnce()
  expect(aiTestingApi.uploadUiCaseGenerateTaskSourceArchive).toHaveBeenCalledTimes(2)
})
it('只读成员可查看源码包，没有上传和保存入口', async () => {
  mount({ taskId: 'task', canWrite: false })
  await screen.findByText('source.zip')
  expect(screen.queryByRole('button', { name: /源码包/ })).not.toBeInTheDocument()
})
it('运行期间禁用源码包替换', async () => {
  mount({ taskId: 'task', busy: true })
  await screen.findByText('source.zip')
  expect(screen.getByRole('button', { name: '替换源码包' })).toBeDisabled()
})
