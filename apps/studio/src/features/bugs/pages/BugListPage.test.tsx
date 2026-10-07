import { seedOwnerProject } from '@/test/projectAccess'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { BugListPage } from './BugListPage'

vi.mock('@/shared/utils/feedback', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/features/projects/hooks/useActiveSprint', () => ({
  useActiveSprint: () => ({
    activeSprintId: 'sprint-1',
    sprints: [{ sprintId: 'sprint-1', name: 'V2.3 迭代' }],
    sprintsQuery: { isLoading: false, error: null },
    selectSprint: vi.fn(),
    sprintSelectorOptions: [
      { label: '全部迭代', value: 'all' },
      { label: 'V2.3 迭代', value: 'sprint-1' },
    ],
  }),
}))

const bug = {
  id: 37,
  bugId: 'bug-1',
  bugNo: 1,
  projectId: 'project-1',
  title: '登录页崩溃',
  descriptionHtml: '<p>现象</p>',
  status: 'active', confirmed: false, resolution: '',
  severity: 'serious',
  priority: 'high',
  reporterUserId: 'user-1',
  assigneeUserId: 'user-2',
  foundSprintId: 'sprint-1',
  plannedFixSprintId: '',
  requirementId: '',
  requirementName: '',
  sourceOrderId: '',
  sourceEntryId: '',
  sourceCaseId: '',
  sourceOrderName: '',
  sourceCaseTitle: '',
  created_at: '2026-09-27T10:00:00Z',
  updated_at: '2026-09-27T10:00:00Z',
}

function listResponse<T>(items: T[]) {
  return Object.assign([...items], { items, total: items.length })
}

function renderPage(client: QueryClient, initialEntries?: string[]) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries ?? ['/testing?tab=bugs']}>
        <BugListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useWorkbenchStore.setState({ activeProjectId: 'project-1', activeSprintId: 'sprint-1' })
  useAuthStore.setState({ user: { userId: 'user-1', name: 'owner' } })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('列出 Bug 并按服务端筛选与分页取数', async () => {
  const getProjectMembers = vi.spyOn(api, 'getProjectMembers').mockImplementation(async () =>
    listResponse([
      { userId: 'user-1', name: 'owner', role: 'owner' },
      { userId: 'user-2', name: ' tester', role: 'member' },
    ]),
  )
  const getProjectBugs = vi
    .spyOn(api, 'getProjectBugs')
    .mockImplementation(async () => listResponse([bug]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  await screen.findByText('登录页崩溃')
  expect(screen.getByRole('columnheader', { name: 'ID' })).toBeInTheDocument()
  expect(screen.getByText('37')).toBeInTheDocument()
  expect(screen.queryByText('BUG-1')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '确认' })).toBeEnabled()
  expect(screen.getByRole('button', { name: '解决' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: /查看|处理|更多/ })).not.toBeInTheDocument()
  expect(getProjectBugs.mock.calls[0][0]).toBe('project-1')
  expect(getProjectBugs.mock.calls[0][1]).toMatchObject({ page: 1, pageSize: 20, sprintId: 'sprint-1' })
  expect(getProjectMembers).toHaveBeenCalled()

  expect(getProjectBugs.mock.calls[0][1]).toMatchObject({ sprintFilter: 'found' })
  expect(screen.queryByRole('group', { name: '快捷筛选' })).not.toBeInTheDocument()
  expect(screen.queryByRole('combobox', { name: '迭代筛选方式' })).not.toBeInTheDocument()
  client.clear()
})

it('行点击进入 Bug 详情页', async () => {
  vi.spyOn(api, 'getProjectMembers').mockImplementation(async () => listResponse([]))
  vi.spyOn(api, 'getProjectBugs').mockImplementation(async () => listResponse([bug]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/testing?tab=bugs']}>
        <Routes>
          <Route path="/testing" element={<BugListPage />} />
          <Route path="/bugs/:bugId" element={<div>Bug 详情占位</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await screen.findByText('登录页崩溃')
  await userEvent.click(screen.getByText('登录页崩溃'))
  expect(await screen.findByText('Bug 详情占位')).toBeInTheDocument()
  client.clear()
})

it('可以访问第二页并显示服务端总数', async () => {
  vi.spyOn(api, 'getProjectMembers').mockResolvedValue(listResponse([]))
  const getProjectBugs = vi.spyOn(api, 'getProjectBugs').mockImplementation(async (_projectId, filters) =>
    Object.assign(listResponse([{ ...bug, bugId: `bug-${filters?.page}`, title: `第 ${filters?.page} 页问题` }]), { total: 60 }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)
  await screen.findByText('第 1 页问题')
  await userEvent.click(screen.getByTitle('2'))
  expect(await screen.findByText('第 2 页问题')).toBeInTheDocument()
  expect(screen.getByText('显示第 21 条 - 第 40 条，共 60 条')).toBeInTheDocument()
  expect(getProjectBugs.mock.calls.at(-1)?.[1]).toMatchObject({ page: 2, pageSize: 20 })
  client.clear()
})

it('从列表按当前状态打开处理表单', async () => {
  vi.spyOn(api, 'getProjectMembers').mockResolvedValue(listResponse([]))
  vi.spyOn(api, 'getProjectBugs').mockResolvedValue(listResponse([{ ...bug, status: 'active', confirmed: false }]))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)
  expect(await screen.findByRole('button', { name: '确认' })).toBeEnabled()
  await userEvent.click(screen.getByRole('button', { name: '解决' }))
  expect(await screen.findByText('解决方案')).toBeInTheDocument()
  client.clear()
})
