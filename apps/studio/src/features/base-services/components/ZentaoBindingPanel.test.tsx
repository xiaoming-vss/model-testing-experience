import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { sharedServicesApi, type SharedService } from '../api/sharedServices.api'
import { zentaoMcpApi } from '../api/zentaoMcp.api'
import { ZentaoBindingModal } from './ZentaoBindingPanel'

const permissions = vi.hoisted(() => ({ manage: true }))
vi.mock('@/features/projects/hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => permissions.manage }) }))
vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
const clients: QueryClient[] = []
function list<T>(items: T[]) { return Object.assign([...items], { items: [...items], total: items.length }) }
const service: SharedService = { serviceId: 'mcp1', projectId: 'p1', provider: 'mcp', name: '禅道 MCP', baseUrl: 'http://mcp.test/mcp', modelId: '', templateId: 'zentao', zentaoInstanceUrl: 'http://zentao.test', authorization: { status: 'authorized', connectionId: 'own-mcp' } }
const projectBinding = { bindingId: 'b1', provider: 'zentao', status: 'active', instanceUrl: 'http://zentao.test', remoteResourceId: '101', remoteNameSnapshot: '项目101' }
function mount(requirement = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  clients.push(client)
  render(<QueryClientProvider client={client}><ZentaoBindingModal open onClose={vi.fn()} projectId="p1" targetType={requirement ? 'requirement' : 'project'} resourceId={requirement ? 'r1' : 'p1'} parentProjectId={requirement ? 'p1' : undefined} parentSprintId={requirement ? 's1' : undefined} depth={requirement ? 'story' : 'project'} /></QueryClientProvider>)
  return client
}
beforeEach(() => {
  permissions.manage = true
  vi.spyOn(sharedServicesApi, 'list').mockResolvedValue(list([service]))
  vi.spyOn(api, 'getProjectBindings').mockResolvedValue(list([]))
  vi.spyOn(api, 'getSprintBindings').mockResolvedValue(list([]))
  vi.spyOn(api, 'getRequirementBindings').mockResolvedValue(list([]))
  vi.spyOn(zentaoMcpApi, 'resources').mockImplementation(async (_pid, kind) => list(kind === 'projects' ? [{ id: '101', name: '项目101' }] : kind === 'executions' ? [{ id: '201', name: '执行201' }] : [{ id: '301', title: '需求301' }, { id: '302', title: '需求302' }]))
})
afterEach(() => { cleanup(); clients.forEach(c => c.clear()); clients.length = 0; vi.restoreAllMocks() })

it('creates a binding through the project MCP without selecting an old connection', async () => {
  const old = vi.spyOn(api, 'getZentaoConnections')
  const create = vi.spyOn(api, 'createProjectBinding').mockResolvedValue(projectBinding)
  mount()
  const select = await screen.findByRole('combobox', { name: '禅道项目' })
  await userEvent.click(select)
  await userEvent.click(await screen.findByText('项目101 (101)'))
  await userEvent.click(screen.getByRole('button', { name: '绑 定' }))
  await waitFor(() => expect(create).toHaveBeenCalledWith('p1', { provider: 'zentao', remoteResourceId: '101', mcpServiceId: 'mcp1' }))
  expect(old).not.toHaveBeenCalled()
})

it('updates an existing requirement using inherited parents and no original connection', async () => {
  vi.mocked(api.getProjectBindings).mockResolvedValue(list([projectBinding]))
  vi.mocked(api.getSprintBindings).mockResolvedValue(list([{ ...projectBinding, bindingId: 'b2', remoteResourceId: '201' }]))
  vi.mocked(api.getRequirementBindings).mockResolvedValue(list([{ ...projectBinding, bindingId: 'b3', remoteResourceId: '301', remoteNameSnapshot: '需求301', connectionId: 'old-deleted' }]))
  const update = vi.spyOn(api, 'updateZentaoBinding').mockResolvedValue(projectBinding)
  const client = mount(true)
  const listKey = ['requirementsPool', 'p1', 's1', 1, 20]
  const otherKey = ['requirementsPool', 'other', 's1', 1, 20]
  client.setQueryData(listKey, [])
  client.setQueryData(otherKey, [])
  client.setQueryData(['sprints', 'p1'], [])
  expect(await screen.findByRole('combobox', { name: '禅道项目' })).toBeDisabled()
  expect(screen.getByRole('combobox', { name: '禅道执行' })).toBeDisabled()
  await userEvent.click(screen.getByRole('combobox', { name: '禅道需求' }))
  await userEvent.click(await screen.findByText('需求302 (302)'))
  await userEvent.click(screen.getByRole('button', { name: '重新绑定' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('requirement', 'r1', 'b3', { remoteResourceId: '302' }))
  await waitFor(() => expect(client.getQueryState(listKey)?.isInvalidated).toBe(true))
  expect(client.getQueryState(otherKey)?.isInvalidated).toBe(false)
  expect(client.getQueryState(['sprints', 'p1'])?.isInvalidated).toBe(false)
})

it('解绑需求后使该项目各分页摘要失效', async () => {
  vi.mocked(api.getProjectBindings).mockResolvedValue(list([projectBinding]))
  vi.mocked(api.getSprintBindings).mockResolvedValue(list([{ ...projectBinding, bindingId: 'b2', remoteResourceId: '201' }]))
  vi.mocked(api.getRequirementBindings).mockResolvedValue(list([{ ...projectBinding, bindingId: 'b3', remoteResourceId: '301' }]))
  const remove = vi.spyOn(api, 'deleteRequirementBinding').mockResolvedValue({})
  const client = mount(true)
  const keys = [['requirementsPool', 'p1', 's1', 1, 20], ['requirementsPool', 'p1', undefined, 2, 20]]
  keys.forEach(key => client.setQueryData(key, []))
  await userEvent.click(await screen.findByRole('button', { name: /解\s*绑/ }))
  await userEvent.click(await screen.findByRole('button', { name: /OK|确\s*定/ }))
  await waitFor(() => expect(remove).toHaveBeenCalledWith('r1', 'b3'))
  await waitFor(() => keys.forEach(key => expect(client.getQueryState(key)?.isInvalidated).toBe(true)))
})

it('directs an unauthorized member to MCP configuration and does not query candidates', async () => {
  vi.mocked(sharedServicesApi.list).mockResolvedValue(list([{ ...service, authorization: { status: 'unauthorized' as const } }]))
  mount()
  expect(await screen.findByText('请在基础服务 → MCP 中配置本人的 Token')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '前往配置' })).toHaveAttribute('href', '/base-services?tab=mcp')
  expect(zentaoMcpApi.resources).not.toHaveBeenCalled()
})

it('requires confirmation when the project selection changes the actual instance', async () => {
  vi.mocked(api.getProjectBindings).mockResolvedValue(list([{ ...projectBinding, instanceUrl: 'http://another.test' }]))
  const update = vi.spyOn(api, 'updateZentaoBinding').mockResolvedValue(projectBinding)
  mount()
  const checkbox = await screen.findByRole('checkbox')
  await screen.findByRole('combobox', { name: '禅道项目' })
  expect(screen.getByRole('button', { name: '重新绑定' })).toBeDisabled()
  await userEvent.click(checkbox)
  await userEvent.click(screen.getByRole('button', { name: '重新绑定' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('project', 'p1', 'b1', { remoteResourceId: '101', mcpServiceId: 'mcp1', confirmInstanceSwitch: true }))
})

it('selects a project MCP and fetches candidates using its service ID', async () => {
  vi.mocked(sharedServicesApi.list).mockResolvedValue(list([service, { ...service, serviceId: 'mcp2', name: '另一项 MCP' }]))
  const create = vi.spyOn(api, 'createProjectBinding').mockResolvedValue(projectBinding)
  mount()
  const select = await screen.findByRole('combobox', { name: '项目 MCP 服务' })
  expect(zentaoMcpApi.resources).not.toHaveBeenCalled()
  await userEvent.click(select)
  await userEvent.click(await screen.findByText('另一项 MCP · http://zentao.test'))
  await userEvent.click(await screen.findByRole('combobox', { name: '禅道项目' }))
  await userEvent.click(await screen.findByText('项目101 (101)'))
  await userEvent.click(screen.getByRole('button', { name: '绑 定' }))
  await waitFor(() => expect(create).toHaveBeenCalledWith('p1', { provider: 'zentao', remoteResourceId: '101', mcpServiceId: 'mcp2' }))
  expect(zentaoMcpApi.resources).toHaveBeenCalledWith('p1', 'projects', undefined, 'mcp2')
})

it('inherits the root MCP for requirement candidates without exposing another selector', async () => {
  vi.mocked(sharedServicesApi.list).mockResolvedValue(list([service, { ...service, serviceId: 'mcp2', name: '另一项 MCP' }]))
  vi.mocked(api.getProjectBindings).mockResolvedValue(list([{ ...projectBinding, mcpServiceId: 'mcp2' }]))
  vi.mocked(api.getSprintBindings).mockResolvedValue(list([{ ...projectBinding, bindingId: 'b2', remoteResourceId: '201' }]))
  mount(true)
  await screen.findByRole('combobox', { name: '禅道需求' })
  expect(screen.queryByRole('combobox', { name: '项目 MCP 服务' })).not.toBeInTheDocument()
  await waitFor(() => expect(zentaoMcpApi.resources).toHaveBeenCalledWith('p1', 'stories', '201', 'mcp2'))
})

it('does not replace a deleted selected MCP with another authorized service', async () => {
  vi.mocked(api.getProjectBindings).mockResolvedValue(list([{ ...projectBinding, mcpServiceId: 'deleted' }]))
  mount(true)
  await screen.findByText('项目绑定所选 MCP 已不存在，请在项目绑定中重新选择')
  expect(zentaoMcpApi.resources).not.toHaveBeenCalled()
})
