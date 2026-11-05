import { TestThemeProvider } from '@/test/TestThemeProvider'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { projectsApi } from '../api/projects.api'
import type { Project } from '../types'
import { ProjectAccessProvider } from './ProjectAccessProvider'
import { ProjectAccessScope } from './ProjectAccessScope'
import { ProjectActionButton } from './ProjectActionButton'

function project(projectId: string, permissions: Project['permissions']): Project {
  return { projectId, name: projectId, role: 'owner', permissions }
}

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <TestThemeProvider>
      <QueryClientProvider client={client}>{ui}</QueryClientProvider>
    </TestThemeProvider>,
  )
  return { ...view, client }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('权限上下文下的整表按钮只请求一次项目详情', async () => {
  const getProject = vi.spyOn(projectsApi, 'getProject').mockResolvedValue(project('project-1', ['read', 'write', 'review']))
  const { client } = renderWithClient(
    <ProjectAccessProvider projectId="project-1">
      {Array.from({ length: 100 }, (_, index) => <ProjectActionButton key={index} action="write" operation="edit" />)}
    </ProjectAccessProvider>,
  )

  await waitFor(() => expect(getProject).toHaveBeenCalledTimes(1))
  expect(getProject).toHaveBeenCalledWith('project-1')
  expect(screen.getAllByRole('button')).toHaveLength(100)
  // 100 个按钮共享同一个上下文 observer，而不是每个按钮各挂一个 query。
  const accessQuery = client.getQueryCache().find({ queryKey: ['projectAccess', 'project-1'] })
  expect(accessQuery?.observers).toHaveLength(1)
})

it('显式 projectId 与上下文不一致时回退到自己的查询', async () => {
  const getProject = vi.spyOn(projectsApi, 'getProject').mockImplementation(async (projectId) =>
    project(projectId, ['read', 'write', 'review']),
  )
  renderWithClient(
    <ProjectAccessProvider projectId="project-1">
      <ProjectActionButton action="write" projectId="project-2" operation="edit" />
    </ProjectAccessProvider>,
  )

  await waitFor(() => expect(getProject).toHaveBeenCalledTimes(2))
  expect(getProject.mock.calls.map(([projectId]) => projectId).sort()).toEqual(['project-1', 'project-2'])
})

it('嵌套资源 scope 用资源项目覆盖外层权限', async () => {
  const getProject = vi.spyOn(projectsApi, 'getProject').mockImplementation(async (projectId) =>
    projectId === 'project-1'
      ? project('project-1', ['read', 'write', 'review'])
      : project('project-2', ['read']),
  )
  renderWithClient(
    <ProjectAccessProvider projectId="project-1">
      <ProjectAccessScope projectId="project-2">
        <ProjectActionButton action="write" operation="edit" aria-label="编辑" />
      </ProjectAccessScope>
    </ProjectAccessProvider>,
  )

  const button = await screen.findByRole('button', { name: '编辑' })
  await waitFor(() => expect(button).toBeDisabled())
  expect(getProject).toHaveBeenCalledWith('project-2')
})
