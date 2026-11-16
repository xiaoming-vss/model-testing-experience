import { beforeEach, describe, expect, it, vi } from 'vitest'
import { request } from '@/shared/api/request'
import { interfaceLibraryApi } from './interfaceLibrary.api'

vi.mock('@/shared/api/request', async importOriginal => {
  const actual = await importOriginal<typeof import('@/shared/api/request')>()
  return { ...actual, request: vi.fn() }
})

describe('interface library API', () => {
  beforeEach(() => {
    vi.mocked(request).mockReset()
    vi.mocked(request).mockResolvedValue([])
  })

  it('serializes interface filters and uses the software-repository-scoped list endpoint', async () => {
    await interfaceLibraryApi.getProjectApiInterfaces('project 1', {
      softwareRepositoryId: 'repository-1',
      method: 'GET',
      requirementId: 'req-1',
      keyword: '订单',
      page: 2,
      pageSize: 20,
    })
    await interfaceLibraryApi.getSoftwareRepositoryApiInterfaces('repository-1', {
      keyword: 'detail',
    })

    expect(request).toHaveBeenNthCalledWith(
      1,
      '/v1/projects/project 1/api-interfaces?softwareRepositoryId=repository-1&method=GET&requirementId=req-1&keyword=%E8%AE%A2%E5%8D%95&page=2&pageSize=20',
    )
    expect(request).toHaveBeenNthCalledWith(
      2,
      '/v1/software-repositories/repository-1/interfaces?keyword=detail',
    )
  })

  it('keeps software repository and interface write routes aligned with the contract', async () => {
    await interfaceLibraryApi.createSoftwareRepository('project-1', {
      name: '订单服务',
      repository: { connectionId: 'c', groupId: 'g', repositoryId: 'r' },
    })
    await interfaceLibraryApi.updateSoftwareRepository('repository-1', {
      name: '订单服务 V2',
    })
    await interfaceLibraryApi.deleteSoftwareRepository('repository-1')
    await interfaceLibraryApi.createApiInterface('repository-1', {
      name: '查询订单',
      method: 'GET',
      path: '/orders/{orderId}',
    })
    await interfaceLibraryApi.updateApiInterface('api-1', { name: '订单详情' })
    await interfaceLibraryApi.deleteApiInterface('api-1')

    expect(vi.mocked(request).mock.calls.map(([url, options]) => [url, options?.method])).toEqual([
      ['/v1/projects/project-1/software-repositories', 'POST'],
      ['/v1/software-repositories/repository-1', 'PATCH'],
      ['/v1/software-repositories/repository-1', 'DELETE'],
      ['/v1/software-repositories/repository-1/interfaces', 'POST'],
      ['/v1/api-interfaces/api-1', 'PATCH'],
      ['/v1/api-interfaces/api-1', 'DELETE'],
    ])
  })

  it('manages requirement software repository associations', async () => {
    await interfaceLibraryApi.getRequirementSoftwareRepositories('requirement-1')
    await interfaceLibraryApi.createRequirementSoftwareRepository('requirement-1', {
      softwareRepositoryId: 'repository-1',
      branch: 'feature/order',
      baselineBranch: 'main',
    })
    await interfaceLibraryApi.updateRequirementSoftwareRepository(
      'requirement-1',
      'repository-1',
      { branch: 'feature/order-v2' },
    )
    await interfaceLibraryApi.deleteRequirementSoftwareRepository(
      'requirement-1',
      'repository-1',
    )

    expect(vi.mocked(request).mock.calls.map(([url, options]) => [url, options?.method])).toEqual([
      ['/v1/requirements/requirement-1/software-repositories', undefined],
      ['/v1/requirements/requirement-1/software-repositories', 'POST'],
      ['/v1/requirements/requirement-1/software-repositories/repository-1', 'PATCH'],
      ['/v1/requirements/requirement-1/software-repositories/repository-1', 'DELETE'],
    ])
  })

  it('uses batch group routes for create, rename, removal and interface moves', async () => {
    await interfaceLibraryApi.createApiInterfaceGroup('repository-1', {
      groupName: '新分组',
    })
    await interfaceLibraryApi.renameApiInterfaceGroup('repository-1', {
      currentGroupName: '订单',
      newGroupName: '订单管理',
    })
    await interfaceLibraryApi.deleteApiInterfaceGroup('repository-1', {
      groupName: '订单管理',
    })
    await interfaceLibraryApi.moveApiInterfaceToGroup('api-1', {
      groupName: '账户',
    })

    const calls = vi.mocked(request).mock.calls
    expect(calls.map(([url, options]) => [url, options?.method])).toEqual([
      ['/v1/software-repositories/repository-1/interface-groups', 'POST'],
      ['/v1/software-repositories/repository-1/interface-groups/rename', 'POST'],
      ['/v1/software-repositories/repository-1/interface-groups/delete', 'POST'],
      ['/v1/api-interfaces/api-1/group', 'PATCH'],
    ])
    expect(calls.map(([, options]) => JSON.parse(String(options?.body)))).toEqual([
      { groupName: '新分组' },
      { currentGroupName: '订单', newGroupName: '订单管理' },
      { groupName: '订单管理' },
      { groupName: '账户' },
    ])
  })

  it('uploads the document as multipart for preview', async () => {
    const file = new File(['openapi: 3.0.0'], 'orders.yaml', { type: 'application/yaml' })
    await interfaceLibraryApi.previewOpenApiImport('repository-1', file)

    const [url, options] = vi.mocked(request).mock.calls[0]
    expect(url).toBe('/v1/software-repositories/repository-1/interfaces/import/preview')
    expect(options?.method).toBe('POST')
    const form = options?.body as FormData
    expect((form.get('file') as File).name).toBe('orders.yaml')
    expect((form.get('file') as File).type).toBe('application/yaml')
  })

  it('sends the preview digest, selected keys and expected versions on commit', async () => {
    const file = new File(['openapi: 3.0.0'], 'orders.yaml', { type: 'application/yaml' })
    await interfaceLibraryApi.commitOpenApiImport('repository-1', {
      file,
      sourceDigest: 'sha256-digest',
      selectedKeys: ['get:/orders/{orderId}'],
      expectedItems: { 'get:/orders/{orderId}': 3 },
      applyBasePath: true,
      expectedSoftwareRepositoryVersion: 7,
    })

    const [url, options] = vi.mocked(request).mock.calls[0]
    expect(url).toBe('/v1/software-repositories/repository-1/interfaces/import')
    const form = options?.body as FormData
    expect((form.get('file') as File).name).toBe('orders.yaml')
    expect(form.get('sourceDigest')).toBe('sha256-digest')
    expect(form.get('selectedKeys')).toBe(JSON.stringify(['get:/orders/{orderId}']))
    expect(form.get('expectedItems')).toBe(JSON.stringify({ 'get:/orders/{orderId}': 3 }))
    expect(form.get('applyBasePath')).toBe('true')
    expect(form.get('expectedSoftwareRepositoryVersion')).toBe('7')
  })
})
