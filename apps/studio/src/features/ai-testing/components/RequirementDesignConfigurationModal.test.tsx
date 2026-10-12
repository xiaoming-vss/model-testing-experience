import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { RequirementDesignConfigurationModal } from './RequirementDesignConfigurationModal'

vi.mock('@/shared/api/files', () => ({ storageCapabilities: async () => ({ enabled: true, maxBytes: 104857600 }), uploadStoredFile: async () => 'file' }))
const clients: QueryClient[] = []
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks() })
function response(data: unknown, status = 200) { return new Response(JSON.stringify({ code: status === 200 ? 0 : status, message: status === 200 ? 'ok' : '上传失败', data }), { status, headers: { 'Content-Type': 'application/json' } }) }
function mount(kind: 'ui' | 'api', onSaved = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  const rendered = render(<TestThemeProvider><QueryClientProvider client={client}><RequirementDesignConfigurationModal requirementId="req" kind={kind} tasks={[]}
    onClose={vi.fn()} onSaved={onSaved} /></QueryClientProvider></TestThemeProvider>)
  return { ...rendered, onSaved }
}
it('配置已保存但上传失败后保留文件和任务 ID，再次保存复用配置', async () => {
  const configurations: Record<string, unknown>[] = []
  let uploads = 0
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://localhost').pathname
    if (path.endsWith('/configuration')) {
      configurations.push(JSON.parse(String(init?.body)))
      return response({ taskId: 'saved-task', name: 'UI 测试', projectId: 'project', instruction: '覆盖失败状态' })
    }
    if (path.endsWith('/source-archive')) { uploads++; return response({}, uploads === 1 ? 500 : 200) }
    return response({ taskId: 'saved-task', projectId: 'project' })
  })
  const user = userEvent.setup()
  const { onSaved } = mount('ui')
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(fileInput, new File(['zip'], 'source.zip', { type: 'application/zip' }))
  await user.click(screen.getByRole('button', { name: '保存设置' }))
  await screen.findByText('上传失败')
  expect(screen.queryByRole('textbox', { name: '补充指令' })).not.toBeInTheDocument()
  expect(onSaved).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: '保存设置' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('saved-task'))
  expect(configurations).toHaveLength(2)
  expect(configurations[1]).toMatchObject({ taskId: 'saved-task', newConfiguration: false })
  expect(configurations[1].requestId).toBe(configurations[0].requestId)
  expect(uploads).toBe(2)
})
it('首次 API 配置直接保存文档，自动使用当前需求', async () => {
  const submitted = vi.fn()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    submitted(JSON.parse(String(init?.body)))
    return response({ taskId: 'api-task' })
  })
  const user = userEvent.setup()
  const { onSaved } = mount('api')
  await user.click(screen.getByRole('textbox', { name: 'OpenAPI / Swagger 文档' })); await user.paste('{"openapi":"3.0.0"}')
  await user.click(screen.getByRole('button', { name: '保存设置' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('api-task'))
  expect(submitted).toHaveBeenCalledWith(expect.objectContaining({ sourceContent: '{"openapi":"3.0.0"}', requestId: expect.any(String) }))
})
