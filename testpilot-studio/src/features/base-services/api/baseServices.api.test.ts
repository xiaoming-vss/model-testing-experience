import { beforeEach, describe, expect, it, vi } from 'vitest'
import { request } from '@/shared/api/request'
import { baseServicesApi } from './baseServices.api'

vi.mock('@/shared/api/request', () => ({ request: vi.fn() }))

const requestMock = vi.mocked(request)

describe('GitLab connection API', () => {
  beforeEach(() => requestMock.mockReset())

  it('uses project-scoped list and detail paths', () => {
    baseServicesApi.getGitlabConnections('project / 1')
    baseServicesApi.getGitlabConnection('project / 1', 'connection / 1')

    expect(requestMock).toHaveBeenNthCalledWith(1, '/v1/projects/project%20%2F%201/integrations/gitlab/connections')
    expect(requestMock).toHaveBeenNthCalledWith(2, '/v1/projects/project%20%2F%201/integrations/gitlab/connections/connection%20%2F%201')
  })

  it('creates, updates and deletes connections with the documented methods', () => {
    const createBody = { name: '公司 GitLab', baseUrl: 'https://gitlab.example.com', accessToken: 'glpat-token' }
    baseServicesApi.createGitlabConnection('project-1', createBody)
    baseServicesApi.updateGitlabConnection('project-1', 'connection-1', { name: '新名称' })
    baseServicesApi.deleteGitlabConnection('project-1', 'connection-1')

    expect(requestMock).toHaveBeenNthCalledWith(1, '/v1/projects/project-1/integrations/gitlab/connections', {
      method: 'POST', body: JSON.stringify(createBody),
    })
    expect(requestMock).toHaveBeenNthCalledWith(2, '/v1/projects/project-1/integrations/gitlab/connections/connection-1', {
      method: 'PATCH', body: JSON.stringify({ name: '新名称' }),
    })
    expect(requestMock).toHaveBeenNthCalledWith(3, '/v1/projects/project-1/integrations/gitlab/connections/connection-1', {
      method: 'DELETE',
    })
  })

  it('reauthenticates with the saved token or an optional new token', () => {
    baseServicesApi.reauthGitlabConnection('project-1', 'connection-1')
    baseServicesApi.reauthGitlabConnection('project-1', 'connection-1', { accessToken: 'glpat-new-token' })

    expect(requestMock).toHaveBeenNthCalledWith(1, '/v1/projects/project-1/integrations/gitlab/connections/connection-1/reauth', {
      method: 'POST',
    })
    expect(requestMock).toHaveBeenNthCalledWith(2, '/v1/projects/project-1/integrations/gitlab/connections/connection-1/reauth', {
      method: 'POST', body: JSON.stringify({ accessToken: 'glpat-new-token' }),
    })
  })
})
