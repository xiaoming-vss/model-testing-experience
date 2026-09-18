import { seedOwnerProject } from '@/test/projectAccess'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type ResourceBinding } from '@/services/api'
import { GitlabBindingModal } from './GitlabBindingPanel'
import { RequirementCodeBindingModal } from './RequirementCodeBindingModal'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function renderModal(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  seedOwnerProject(client)
  return { ...render(<QueryClientProvider client={client}>{children}</QueryClientProvider>), client }
}

it('管理权限撤销后禁用已绑定仓库的分支与基线修改', async () => {
  vi.spyOn(api, 'getGitlabProjectBindings').mockResolvedValue(listResponse([]))
  vi.spyOn(api, 'getGitlabConnections').mockResolvedValue(listResponse([]))
  vi.spyOn(api, 'getGitlabRequirementBindings').mockResolvedValue(listResponse([{
    bindingId: 'binding-1', provider: 'gitlab', remoteResourceType: 'repository', remoteResourceId: 'repo-1',
    instanceUrl: 'https://gitlab.example.com', branch: 'dev', baselineBranch: 'main',
  }]))
  const update = vi.spyOn(api, 'updateGitlabRequirementBinding')
  const { client } = renderModal(<RequirementCodeBindingModal open projectId="project-1" requirementId="requirement-1" onClose={() => {}} />)
  await screen.findByText('repo-1')
  const branch = screen.getByText('repo-1').closest('.requirement-code-binding-row')!
  const selectors = branch.querySelectorAll('input[role="combobox"]')
  expect(selectors).toHaveLength(2)
  expect(selectors[0]).toBeEnabled()
  await act(async () => { client.setQueryData(['projectAccess', 'project-1'], { projectId: 'project-1', permissions: ['read', 'write'] }) })
  expect(selectors[0]).toBeDisabled()
  expect(selectors[1]).toBeDisabled()
  expect(update).not.toHaveBeenCalled()
})

it('部分群组绑定成功后刷新成功项，重试仅提交失败项', async () => {
  const bindings: ResourceBinding[] = []
  vi.spyOn(api, 'getGitlabConnections').mockResolvedValue(listResponse([{
    connectionId: 'connection-1', provider: 'gitlab', name: 'GitLab', baseUrl: 'https://gitlab.example.com',
    authType: 'personal_access_token', account: 'tester', status: 'active', hasAccessToken: true,
  }]))
  vi.spyOn(api, 'getGitlabProjectBindings').mockImplementation(async () => listResponse([...bindings]))
  vi.spyOn(api, 'getGitlabGroups').mockResolvedValue({ items: [{ id: 'a', name: '群组A' }, { id: 'b', name: '群组B' }], total: 2 })
  let failB = true
  const create = vi.spyOn(api, 'createGitlabGroupBinding').mockImplementation(async (_, body) => {
    if (body.remoteResourceId === 'b' && failB) throw new Error('群组B暂时失败')
    const binding = { ...body, instanceUrl: 'https://gitlab.example.com', bindingId: body.remoteResourceId, status: 'active' }
    bindings.push(binding)
    return binding
  })
  const user = userEvent.setup()
  renderModal(<GitlabBindingModal open projectId="project-1" onClose={() => {}} />)
  await user.click(await screen.findByRole('button', { name: /群组A/ }))
  await user.click(screen.getByRole('button', { name: /群组B/ }))
  await user.click(screen.getByRole('button', { name: /^绑\s*定$/ }))
  await waitFor(() => expect(screen.getByRole('button', { name: /群组A/ })).toBeDisabled())
  expect(screen.getByRole('button', { name: /群组A/ })).toHaveAttribute('aria-pressed', 'false')
  expect(screen.getByRole('button', { name: /群组B/ })).toHaveAttribute('aria-pressed', 'true')
  failB = false
  await user.click(screen.getByRole('button', { name: /^绑\s*定$/ }))
  await waitFor(() => expect(screen.getByRole('button', { name: /群组B/ })).toBeDisabled())
  expect(create.mock.calls.map(([, body]) => body.remoteResourceId)).toEqual(['a', 'b', 'b'])
})

it('仓库超过500个时可继续加载，并且不再请求已加载完的群组', async () => {
  vi.spyOn(api, 'getGitlabConnections').mockResolvedValue(listResponse([{ connectionId: 'connection-1', provider: 'gitlab', name: '本人GitLab', baseUrl: 'https://gitlab.example.com', status: 'active', authType: 'personal_access_token', account: 'tester', hasAccessToken: true }]))
  vi.spyOn(api, 'getGitlabProjectBindings').mockResolvedValue(listResponse(['large', 'small'].map((id) => ({
    provider: 'gitlab', bindingId: id, instanceUrl: 'https://gitlab.example.com', connectionId: 'connection-1', remoteResourceType: 'group', remoteResourceId: id,
  }))))
  vi.spyOn(api, 'getGitlabRequirementBindings').mockResolvedValue(listResponse([]))
  const repositories = vi.spyOn(api, 'getGitlabGroupRepositories').mockImplementation(async (_, __, groupId, page = 1) => {
    const total = groupId === 'large' ? 501 : 1
    const start = (page - 1) * 100
    return { items: Array.from({ length: Math.max(0, Math.min(100, total - start)) }, (_, index) => ({
      id: `${groupId}-${start + index + 1}`, name: `仓库${groupId}-${start + index + 1}`,
    })), total }
  })
  const user = userEvent.setup()
  renderModal(<RequirementCodeBindingModal open projectId="project-1" requirementId="requirement-1" onClose={() => {}} />)
  await waitFor(() => expect(repositories).toHaveBeenCalledWith('project-1', 'connection-1', 'large', 1, 100))
  for (let page = 2; page <= 6; page += 1) {
    const more = await screen.findByRole('button', { name: /加载更多仓库/ })
    await waitFor(() => expect(more).not.toHaveClass('ant-btn-loading'))
    await user.click(more)
    await waitFor(() => expect(repositories).toHaveBeenCalledWith('project-1', 'connection-1', 'large', page, 100))
  }
  await waitFor(() => expect(screen.queryByRole('button', { name: /加载更多仓库/ })).not.toBeInTheDocument())
  expect(repositories.mock.calls.filter(([, , groupId]) => groupId === 'small')).toHaveLength(1)
  const repositorySearch = screen.getAllByRole('combobox')[1]
  await user.click(repositorySearch)
  await user.type(repositorySearch, 'large-501')
  expect(await screen.findByText('仓库large-501 (large-501) · https://gitlab.example.com')).toBeInTheDocument()
})

it.each([1, 2])('本人有 %i 个同实例可用连接时重新验证正确选择授权', async (count) => {
  const binding: ResourceBinding = {
    bindingId: 'binding-1', provider: 'gitlab', remoteResourceType: 'group', remoteResourceId: 'group-1',
    instanceUrl: 'https://gitlab.example.com', status: 'active',
  }
  vi.spyOn(api, 'getGitlabConnections').mockResolvedValue(listResponse([
    ...Array.from({ length: count }, (_, index) => ({
      connectionId: `mine-${index + 1}`, provider: 'gitlab' as const, name: `本人授权${index + 1}`,
      baseUrl: 'https://gitlab.example.com/', status: 'active', authType: 'personal_access_token' as const,
      account: 'tester', hasAccessToken: true,
    })),
    { connectionId: 'other-instance', provider: 'gitlab', name: '其他实例', baseUrl: 'https://other.example.com', status: 'active', authType: 'personal_access_token', account: 'tester', hasAccessToken: true },
    { connectionId: 'inactive', provider: 'gitlab', name: '失效授权', baseUrl: 'https://gitlab.example.com', status: 'inactive', authType: 'personal_access_token', account: 'tester', hasAccessToken: true },
  ]))
  vi.spyOn(api, 'getGitlabProjectBindings').mockResolvedValue(listResponse([binding]))
  vi.spyOn(api, 'getGitlabGroups').mockResolvedValue({ items: [], total: 0 })
  const revalidate = vi.spyOn(api, 'revalidateGitlabGroupBinding').mockResolvedValue(binding)
  const user = userEvent.setup()
  renderModal(<GitlabBindingModal open projectId="project-1" onClose={() => {}} />)
  await user.click(await screen.findByRole('button', { name: '重新验证' }))
  if (count === 2) {
    expect(revalidate).not.toHaveBeenCalled()
    await user.click(await screen.findByRole('menuitem', { name: '本人授权2' }))
  } else {
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  }
  await waitFor(() => expect(revalidate).toHaveBeenCalledWith('project-1', 'binding-1', `mine-${count}`))
})
