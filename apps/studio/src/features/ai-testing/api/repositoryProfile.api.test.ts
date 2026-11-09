import { beforeEach, expect, it, vi } from 'vitest'
import { request } from '@/shared/api/request'
import { repositoryProfileApi } from './repositoryProfile.api'

vi.mock('@/shared/api/request', async importOriginal => {
  const actual = await importOriginal<typeof import('@/shared/api/request')>()
  return { ...actual, request: vi.fn() }
})

beforeEach(() => vi.clearAllMocks())

it('仓库画像任务与运行端点使用需求级任务契约', async () => {
  vi.mocked(request).mockResolvedValue({} as never)

  await repositoryProfileApi.getRepositoryProfileTasks('p')
  expect(request).toHaveBeenLastCalledWith('/v1/projects/p/repository-profile-tasks')

  await repositoryProfileApi.createRepositoryProfileTask('p', { requirementId: 'r' })
  expect(request).toHaveBeenLastCalledWith('/v1/projects/p/repository-profile-tasks', {
    method: 'POST',
    body: JSON.stringify({ requirementId: 'r' }),
  })

  await repositoryProfileApi.runRepositoryProfileTask('task', {
    llmConnectionId: 'llm',
    requirementUnderstandingVersionId: 'v1',
    requestId: 'request',
  })
  expect(request).toHaveBeenLastCalledWith('/v1/repository-profile-tasks/task/run', {
    method: 'POST',
    body: JSON.stringify({
      llmConnectionId: 'llm',
      requirementUnderstandingVersionId: 'v1',
      requestId: 'request',
    }),
  })

  await repositoryProfileApi.getRepositoryProfileTaskRuns('task', { page: 2, pageSize: 20 })
  expect(request).toHaveBeenLastCalledWith(
    '/v1/repository-profile-tasks/task/runs?page=2&pageSize=20',
  )

  await repositoryProfileApi.getRepositoryProfileRun('run')
  expect(request).toHaveBeenLastCalledWith('/v1/repository-profile-runs/run')

  await repositoryProfileApi.getRepositoryProfileVersions('task')
  expect(request).toHaveBeenLastCalledWith('/v1/repository-profile-tasks/task/versions')
})
