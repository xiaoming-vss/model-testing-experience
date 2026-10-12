import { ConfigProvider } from 'antd'
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
  render(<QueryClientProvider client={client}><ConfigProvider theme={{ token: { motion: false } }}><SharedServicesPanel projectId="project-1" provider={provider} /></ConfigProvider></QueryClientProvider>)
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
    fireEvent.click(within(dialog).getByRole('button', { name: '保存授权' }))
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
  ...resource, provider: 'mcp', templateId: 'zentao', name: 'ZenTao-MCP', modelId: '',
  baseUrl: 'http://127.0.0.1:9090/zentao/mcp',
}
function mockMcpTemplates() {
  vi.spyOn(api, 'mcpTemplates').mockResolvedValue({ items: [{
    templateId: 'zentao', name: 'ZenTao-MCP', type: 'streamableHttp', authorizationHeader: 'token',
  }], total: 1 } as never)
}

describe('新增禅道 MCP', () => {
  it('creates a named MCP with a selected type and lets the member authorize afterwards', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([] as never)
    const named = { ...mcpResource, name: '项目测试禅道' }
    const create = vi.spyOn(api, 'create').mockResolvedValue(named)
    const client = mount('owner', 'mcp')
    expect(await screen.findByText('暂无 MCP，先新增 MCP，再配置本人授权')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /新增 MCP/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('服务名称')).toBeEnabled()
    fireEvent.change(within(dialog).getByLabelText('服务名称'), { target: { value: '项目测试禅道' } })
    expect(within(dialog).getByRole('combobox', { name: 'MCP 类型' })).toBeEnabled()
    expect(within(dialog).getByText('禅道（ZenTao）')).toBeInTheDocument()
    expect(within(dialog).queryByLabelText('我的 Token')).not.toBeInTheDocument()
    expect(within(dialog).getByLabelText('MCP 服务地址')).toBeEnabled()
    fireEvent.change(within(dialog).getByLabelText('MCP 服务地址'), { target: { value: 'https://mcp.test/project-a/mcp/' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }))
    await waitFor(() => expect(create).toHaveBeenCalledWith('project-1', 'mcp', {
      name: '项目测试禅道', baseUrl: 'https://mcp.test/project-a/mcp/', templateId: 'zentao',
    }))
    vi.mocked(api.list).mockResolvedValue([named] as never)
    await client.invalidateQueries({ queryKey: ['sharedServices', 'project-1', 'mcp'] })
    expect(await screen.findByText('项目测试禅道')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /新增 MCP/ })).toBeEnabled()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(screen.getByRole('button', { name: '授权' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: '授权' }))
    await waitFor(() => expect(screen.getByLabelText('我的 Token')).toBeVisible())
    expect(screen.getByLabelText('我的 Token')).toBeEnabled()
  })

  it('lets a viewer save a personal token without putting it in query caches', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([mcpResource] as never)
    const authorize = vi.spyOn(api, 'authorize').mockResolvedValue(mcpResource)
    const client = mount('viewer', 'mcp')
    expect(await screen.findByText('本人未授权')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '编辑 ZenTao-MCP' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '授权' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/禅道访问权限在业务操作时校验/)).toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('我的 Token'), { target: { value: 'my-mcp-secret' } })
    fireEvent.click(within(dialog).getByRole('button', { name: '保存授权' }))
    await waitFor(() => expect(authorize).toHaveBeenCalledWith('project-1', 'mcp', 'service-1', { token: 'my-mcp-secret' }))
    await waitFor(() => expect(screen.queryByLabelText('我的 Token')).not.toHaveValue('my-mcp-secret'))
    expect(JSON.stringify(client.getQueryCache().getAll().map(q => q.state.data))).not.toContain('my-mcp-secret')
  })

  it('lets the owner change the endpoint without claiming business authorization', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([{ ...mcpResource, authorization: { status: 'authorized' } }] as never)
    const rename = vi.spyOn(api, 'rename').mockResolvedValue(mcpResource)
    mount('owner', 'mcp')
    expect(await screen.findByText('已配置授权')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '编辑 ZenTao-MCP' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('MCP 服务地址')).toBeEnabled()
    fireEvent.change(within(dialog).getByLabelText('MCP 服务地址'), { target: { value: 'http://new.test:9092/zentao/mcp' } })
    expect(within(dialog).getByLabelText('服务名称')).toBeEnabled()
    expect(within(dialog).getByLabelText('服务名称')).toHaveValue('ZenTao-MCP')
    await waitFor(() => expect(within(dialog).getByRole('button', { name: /保\s*存/ })).toBeDisabled())
    fireEvent.click(await within(dialog).findByRole('checkbox'))
    await waitFor(() => expect(within(dialog).getByRole('button', { name: /保\s*存/ })).toBeEnabled())
    fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }))
    await waitFor(() => expect(rename).toHaveBeenCalledWith('project-1', 'mcp', 'service-1', 'ZenTao-MCP', 'http://new.test:9092/zentao/mcp', true))
  })

  it('disables service configuration for viewers and rejects credentials in a public URL', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([] as never)
    const create = vi.spyOn(api, 'create')
    mount('viewer', 'mcp')
    expect(await screen.findByRole('button', { name: /新增 MCP/ })).toBeDisabled()
    cleanup()
    mount('owner', 'mcp')
    await waitFor(() => expect(screen.getByRole('button', { name: /新增 MCP/ })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: /新增 MCP/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('MCP 服务地址'), { target: { value: 'https://host.test/mcp?token=secret' } })
    fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }))
    expect(await within(dialog).findByText(/请输入不含凭据/)).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })
})


describe('编辑配置时切换禅道', () => {
  const changed: SharedService = { ...mcpResource, instanceResetRequired: true,
    pendingInstanceUrl: 'https://new-zentao.test', connectionStatus: 'error',
    authorization: { status: 'authorized' } }

  it('owner switches by checking the editor confirmation and saving once', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([changed] as never)
    const rename = vi.spyOn(api, 'rename').mockResolvedValue(mcpResource)
    const client = mount('owner', 'mcp')
    client.setQueryData(['resourceBindings', 'project-1'], { old: true })
    expect(await screen.findByText('需更新配置')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /查看切换详情|切换禅道并清除旧绑定/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '编辑 ZenTao-MCP' }))
    const dialog = await screen.findByRole('dialog')
    const save = within(dialog).getByRole('button', { name: /保\s*存/ })
    expect(save).toBeDisabled()
    expect(rename).not.toHaveBeenCalled()
    expect(within(dialog).getByText(/原禅道数据保留/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('checkbox'))
    await waitFor(() => expect(save).toBeEnabled())
    fireEvent.click(save)
    await waitFor(() => expect(rename).toHaveBeenCalledWith('project-1', 'mcp', 'service-1', 'ZenTao-MCP', mcpResource.baseUrl, true))
    await waitFor(() => expect(client.getQueryState(['resourceBindings', 'project-1'])?.isInvalidated).toBe(true))
  })

  it('requires checking again when the MCP endpoint changes after confirmation', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([changed] as never)
    const rename = vi.spyOn(api, 'rename').mockResolvedValue(mcpResource)
    mount('owner', 'mcp')
    fireEvent.click(await screen.findByRole('button', { name: '编辑 ZenTao-MCP' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('checkbox'))
    fireEvent.change(within(dialog).getByLabelText('MCP 服务地址'), { target: { value: 'https://another.test/mcp' } })
    expect(within(dialog).getByRole('checkbox')).not.toBeChecked()
    await waitFor(() => expect(within(dialog).getByRole('button', { name: /保\s*存/ })).toBeDisabled())
    expect(rename).not.toHaveBeenCalled()
  })

  it('member sees the pending instance without a separate switching button', async () => {
    mockMcpTemplates()
    vi.spyOn(api, 'list').mockResolvedValue([changed] as never)
    mount('viewer', 'mcp')
    expect(await screen.findByText('https://new-zentao.test')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '编辑 ZenTao-MCP' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /查看切换详情|切换禅道并清除旧绑定/ })).not.toBeInTheDocument()
  })
})
