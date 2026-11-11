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
function mount(kind: 'ui' | 'api', onSaved = vi.fn(), initialTaskId?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  const rendered = render(<TestThemeProvider><QueryClientProvider client={client}><RequirementDesignConfigurationModal requirementId="req" kind={kind} tasks={[]} initialTaskId={initialTaskId}
    onClose={vi.fn()} onSaved={onSaved} /></QueryClientProvider></TestThemeProvider>)
  return { ...rendered, onSaved }
}
it('UI 生成设置不再接受源码 ZIP，保存后直接完成配置', async () => {
  const configurations: Record<string, unknown>[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://localhost').pathname
    if (path.endsWith('/configuration')) {
      configurations.push(JSON.parse(String(init?.body)))
      return response({ taskId: 'saved-task', name: 'UI 测试', projectId: 'project', instruction: '覆盖失败状态' })
    }
    return response({ taskId: 'saved-task', projectId: 'project' })
  })
  const user = userEvent.setup()
  const { onSaved } = mount('ui')
  expect(document.querySelector('input[type="file"]')).toBeNull()
  expect(screen.queryByText(/源码 ZIP/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '保存设置' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('saved-task'))
  expect(configurations).toHaveLength(1)
  expect(configurations[0]).toMatchObject({ newConfiguration: false })
  expect(configurations[0].requestId).toEqual(expect.any(String))
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

it('未配置时空任务 ID 不触发读取，允许保存文档', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    if (!init?.method || init.method === 'GET') return response({}, 404)
    return response({ taskId: 'api-task' })
  })
  const user = userEvent.setup()
  const { onSaved } = mount('api', vi.fn(), '')
  await user.type(screen.getByRole('textbox', { name: 'OpenAPI / Swagger 文档' }), 'openapi: 3.0.0')
  expect(screen.getByRole('button', { name: '保存设置' })).toBeEnabled()
  await user.click(screen.getByRole('button', { name: '保存设置' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('api-task'))
  expect(fetchMock).toHaveBeenCalledTimes(1)
})
it('格式化 JSON 后保存', async () => {
  const submitted = vi.fn()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    submitted(JSON.parse(String(init?.body)))
    return response({ taskId: 'api-task' })
  })
  const user = userEvent.setup()
  const { onSaved } = mount('api')
  const editor = screen.getByRole('textbox', { name: 'OpenAPI / Swagger 文档' })
  await user.click(editor)
  await user.paste('{"openapi":"3.0.0"}')
  await user.click(screen.getByRole('button', { name: '格式化' }))
  await user.click(screen.getByRole('button', { name: '保存设置' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalled())
  expect(submitted).toHaveBeenCalledWith(expect.objectContaining({ sourceContent: '{\n  "openapi": "3.0.0"\n}' }))
})

it('文档格式错误时提示并保留原文', async () => {
  const user = userEvent.setup()
  mount('api')
  const editor = screen.getByRole('textbox', { name: 'OpenAPI / Swagger 文档' })
  await user.click(editor)
  await user.paste('{"openapi":}')
  await user.click(screen.getByRole('button', { name: '格式化' }))
  expect(screen.getByText('文档格式不正确，请检查 JSON 或 YAML 后重试')).toBeInTheDocument()
  expect(editor).toHaveTextContent('{"openapi":}')
})
it('格式化 YAML 时保留注释并保存内容', async () => {
  const submitted = vi.fn()
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    submitted(JSON.parse(String(init?.body)))
    return response({ taskId: 'api-task' })
  })
  const user = userEvent.setup()
  const { onSaved } = mount('api')
  await user.click(screen.getByRole('textbox', { name: 'OpenAPI / Swagger 文档' }))
  await user.paste('# API 版本\nopenapi: 3.0.0')
  await user.click(screen.getByRole('button', { name: '格式化' }))
  await user.click(screen.getByRole('button', { name: '保存设置' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalled())
  expect(submitted).toHaveBeenCalledWith(expect.objectContaining({ sourceContent: '# API 版本\nopenapi: 3.0.0\n' }))
})
