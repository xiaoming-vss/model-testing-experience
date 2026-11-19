import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { seedOwnerProject } from '@/test/projectAccess'
import { listResponse } from '@/test/listResponse'
import { bugsApi } from '../api/bugs.api'
import type { Bug, BugActivity, BugZentaoPush } from '../types'
import { BugDetailPage } from './BugDetailPage'

vi.mock('@/shared/utils/feedback', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const bug: Bug = {
  id: 37,
  bugId: 'bug-1',
  bugNo: 37,
  projectId: 'project-1',
  title: '登录页崩溃',
  descriptionHtml: '<p>打开登录页后崩溃</p>',
  status: 'active',
  confirmed: false,
  resolution: '',
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
  attachments: [],
  created_at: '2026-09-27T10:00:00Z',
  updated_at: '2026-09-27T10:00:00Z',
}

const activities: BugActivity[] = [{
  activityId: 'activity-1',
  bugId: 'bug-1',
  kind: 'status_change',
  actorUserId: 'user-2',
  action: 'confirm',
  fromStatus: 'active',
  toStatus: 'active',
  content: '已复现',
  detail: { fromConfirmed: false, toConfirmed: true },
  created_at: '2026-09-27T10:05:00Z',
}, {
  activityId: 'activity-2',
  bugId: 'bug-1',
  kind: 'comment',
  actorUserId: 'user-1',
  action: 'comment',
  fromStatus: 'active',
  toStatus: 'active',
  content: '补充复现环境',
  detail: {},
  created_at: '2026-09-27T10:10:00Z',
}]

const project = {
  projectId: 'project-1',
  name: '测试项目',
  role: 'owner' as const,
  permissions: ['read', 'write', 'execute', 'bug_handle'] as const,
}

const zentaoPush: BugZentaoPush = {
  status: 'not_pushed',
  ready: false,
  reason: '尚未配置禅道目标',
  remoteBugId: null,
  target: {},
  errorMessage: '',
  actorUserId: '',
  updatedAt: null,
  warnings: [],
}

function renderPage(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/bugs/bug-1']}>
        <Routes>
          <Route path="/bugs/:bugId" element={<BugDetailPage />} />
          <Route path="/testing" element={<div>Bug 列表占位</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function mockDetailQueries() {
  vi.spyOn(api, 'getBug').mockResolvedValue(bug)
  vi.spyOn(api, 'getBugActivities').mockResolvedValue(listResponse(activities))
  vi.spyOn(api, 'getProject').mockResolvedValue({
    ...project,
    permissions: [...project.permissions],
  })
  vi.spyOn(api, 'getProjectMembers').mockResolvedValue(listResponse([
    { userId: 'user-1', name: '张三', role: 'owner' as const },
    { userId: 'user-2', name: '李四', role: 'member' as const },
  ]))
  const getSprints = vi.spyOn(api, 'getSprints').mockResolvedValue(listResponse([
    { sprintId: 'sprint-1', name: 'V2.3 迭代', status: 'running' as const },
  ]))
  vi.spyOn(bugsApi, 'getBugZentaoPush').mockResolvedValue(zentaoPush)
  return { getSprints }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

it('渲染 Bug 字段、描述、处理记录和关联上下文', async () => {
  const { getSprints } = mockDetailQueries()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  expect(await screen.findByRole('heading', { name: '登录页崩溃', level: 1 })).toBeInTheDocument()
  await waitFor(() => expect(getSprints).toHaveBeenCalledWith('project-1'))
  expect(await screen.findByText('V2.3 迭代')).toBeInTheDocument()
  expect(screen.getByText('BUG-37')).toBeInTheDocument()
  expect(screen.getByText('激活 · 未确认')).toBeInTheDocument()
  expect(screen.getByText('打开登录页后崩溃')).toBeInTheDocument()
  expect(screen.getByText('严重')).toBeInTheDocument()
  expect(screen.getByText('高')).toBeInTheDocument()
  expect(screen.getByText('已复现')).toBeInTheDocument()
  expect(screen.getByText('补充复现环境')).toBeInTheDocument()
  expect(screen.getByText('未关联需求')).toBeInTheDocument()
  expect(await screen.findByText('尚未推送')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '编辑 Bug' })).toBeInTheDocument()
  client.clear()
})

it('提交评论并清空输入框', async () => {
  const { getSprints } = mockDetailQueries()
  const commentBug = vi.spyOn(api, 'commentBug').mockResolvedValue({})
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seedOwnerProject(client)
  renderPage(client)

  const input = await screen.findByLabelText('评论输入框')
  await waitFor(() => expect(getSprints).toHaveBeenCalledWith('project-1'))
  await screen.findByText('V2.3 迭代')
  await waitFor(() => expect(input).toBeEnabled())
  await userEvent.type(input, '补充了浏览器版本')
  await waitFor(() => expect(screen.getByRole('button', { name: '发送评论' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: '发送评论' }))

  await waitFor(() => expect(commentBug).toHaveBeenCalledWith('bug-1', '补充了浏览器版本'))
  await waitFor(() => expect(message.success).toHaveBeenCalledWith('评论已发送'))
  expect(input).toHaveValue('')
  client.clear()
})
