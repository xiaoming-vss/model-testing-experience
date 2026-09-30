import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SharedServicesPanel } from './SharedServicesPanel'
import { sharedServicesApi as api, type SharedService, type ServiceProvider } from '../api/sharedServices.api'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))

const resource: SharedService = {
  serviceId: 'service-1', projectId: 'project-1', provider: 'llm', name: '团队模型',
  baseUrl: 'https://example.test/v1', modelId: 'model-1', authorization: { status: 'unauthorized' },
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })
function mount(role: 'owner' | 'viewer', provider: ServiceProvider = 'llm') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(['projectAccess', 'project-1'], {
    projectId: 'project-1', role, permissions: role === 'owner' ? ['read', 'manage'] : ['read'],
  })
  render(<QueryClientProvider client={client}><SharedServicesPanel projectId="project-1" provider={provider} /></QueryClientProvider>)
  return client
}

describe('共享服务和个人授权', () => {
  it('viewer sees shared metadata and can authorize without managing the service', async () => {
    vi.spyOn(api, 'list').mockResolvedValue([resource] as never)
    const authorize = vi.spyOn(api, 'authorize').mockResolvedValue({ ...resource, authorization: { status: 'authorized' } })
    const client = mount('viewer')
    expect(await screen.findByText('团队模型')).toBeInTheDocument()
    expect(screen.getByText('未授权', { selector: '.ant-tag' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /新建服务/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: '编辑 团队模型' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /授权/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('API Key'), { target: { value: 'personal-secret' } })
    fireEvent.click(within(dialog).getByRole('button', { name: '保存我的授权' }))
    await waitFor(() => expect(authorize).toHaveBeenCalledWith('project-1', 'llm', 'service-1', { apiKey: 'personal-secret' }))
    await waitFor(() => expect(screen.queryByLabelText('API Key')).not.toHaveValue('personal-secret'))
    expect(JSON.stringify(client.getQueryCache().getAll().map(q => q.state.data))).not.toContain('personal-secret')
    expect(client.getMutationCache().getAll()).toHaveLength(0)
  })

  it('owner creates public configuration without any credential fields', async () => {
    vi.spyOn(api, 'list').mockResolvedValue([] as never)
    const create = vi.spyOn(api, 'create').mockResolvedValue(resource)
    mount('owner')
    fireEvent.click(await screen.findByRole('button', { name: /新建服务/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByLabelText('API Key')).not.toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('服务名称'), { target: { value: '团队模型' } })
    fireEvent.change(within(dialog).getByLabelText('服务地址'), { target: { value: 'https://example.test/v1' } })
    fireEvent.change(within(dialog).getByLabelText('模型 ID'), { target: { value: 'model-1' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /确.*认|OK|保\s*存/ }))
    await waitFor(() => expect(create).toHaveBeenCalledWith('project-1', 'llm', {
      name: '团队模型', baseUrl: 'https://example.test/v1', modelId: 'model-1',
    }))
  })

  it('revokes only the current user authorization after confirmation', async () => {
    vi.spyOn(api, 'list').mockResolvedValue([{ ...resource, authorization: { status: 'authorized', connectionId: 'mine' } }] as never)
    const revoke = vi.spyOn(api, 'revoke').mockResolvedValue(resource)
    const remove = vi.spyOn(api, 'delete')
    mount('viewer')
    fireEvent.click(await screen.findByRole('button', { name: '撤销我的授权' }))
    fireEvent.click(await screen.findByRole('button', { name: /确.*认|OK|保\s*存/ }))
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('project-1', 'llm', 'service-1'))
    expect(remove).not.toHaveBeenCalled()
  })
})

const mcpResource: SharedService = {
  ...resource, provider: 'mcp', templateId: 'zentao', name: '禅道 MCP', modelId: '',
  baseUrl: 'http://127.0.0.1:9090/zentao/mcp',
}
function mockMcpTemplates() {
  vi.spyOn(api, 'mcpTemplates').mockResolvedValue({ items: [{
    templateId: 'zentao', name: '禅道 MCP', type: 'streamableHttp', authorizationHeader: 'token',
  }], total: 1 } as never)
}

describe('内置禅道 MCP', () => {
  it('shows the built-in entry before configuration and creates metadata only', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([] as never)
    const create = vi.spyOn(api, 'create').mockResolvedValue(mcpResource)
    mount('owner', 'mcp')
    expect(await screen.findByText('未配置服务')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /新建服务|启用|停用/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /配置服务/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('服务名称')).toHaveValue('禅道 MCP')
    expect(within(dialog).queryByLabelText('我的 Token')).not.toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('服务地址'), { target: { value: mcpResource.baseUrl } })
    fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }))
    await waitFor(() => expect(create).toHaveBeenCalledWith('project-1', 'mcp', {
      name: '禅道 MCP', baseUrl: mcpResource.baseUrl, templateId: 'zentao',
    }))
  })

  it('lets a viewer save a personal token without putting it in query caches', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([mcpResource] as never)
    const authorize = vi.spyOn(api, 'authorize').mockResolvedValue(mcpResource)
    const client = mount('viewer', 'mcp')
    expect(await screen.findByText('本人未授权')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '编辑 禅道 MCP' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '授权' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/保存后不会验证远端连接/)).toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('我的 Token'), { target: { value: 'my-mcp-secret' } })
    fireEvent.click(within(dialog).getByRole('button', { name: '保存我的授权' }))
    await waitFor(() => expect(authorize).toHaveBeenCalledWith('project-1', 'mcp', 'service-1', { token: 'my-mcp-secret' }))
    await waitFor(() => expect(screen.queryByLabelText('我的 Token')).not.toHaveValue('my-mcp-secret'))
    expect(JSON.stringify(client.getQueryCache().getAll().map(q => q.state.data))).not.toContain('my-mcp-secret')
  })

  it('keeps the URL immutable and shows saved authorization without claiming connectivity', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([{ ...mcpResource, authorization: { status: 'authorized' } }] as never)
    const rename = vi.spyOn(api, 'rename').mockResolvedValue(mcpResource)
    mount('owner', 'mcp')
    expect(await screen.findByText('本人已配置授权')).toBeInTheDocument()
    expect(screen.getByText('已配置，未验证连接')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '编辑 禅道 MCP' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('服务地址')).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText('服务名称'), { target: { value: '新的名称' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }))
    await waitFor(() => expect(rename).toHaveBeenCalledWith('project-1', 'mcp', 'service-1', '新的名称'))
  })

  it('disables service configuration for viewers and rejects credentials in a public URL', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([] as never)
    const create = vi.spyOn(api, 'create')
    mount('viewer', 'mcp')
    expect(await screen.findByRole('button', { name: /配置服务/ })).toBeDisabled()
    cleanup()
    mount('owner', 'mcp')
    fireEvent.click(await screen.findByRole('button', { name: /配置服务/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('服务地址'), { target: { value: 'https://host.test/mcp?token=secret' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }))
    expect(await within(dialog).findByText(/请输入不含凭据/)).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })
})
