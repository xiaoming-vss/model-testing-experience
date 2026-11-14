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

  it('serializes interface filters and uses the app-scoped list endpoint', async () => {
    await interfaceLibraryApi.getProjectApiInterfaces('project 1', {
      appId: 'app-1',
      method: 'GET',
      requirementId: 'req-1',
      enabled: false,
      keyword: '订单',
      page: 2,
      pageSize: 20,
    })
    await interfaceLibraryApi.getAppApiInterfaces('app-1', { keyword: 'detail' })

    expect(request).toHaveBeenNthCalledWith(
      1,
      '/v1/projects/project 1/api-interfaces?appId=app-1&method=GET&requirementId=req-1&enabled=false&keyword=%E8%AE%A2%E5%8D%95&page=2&pageSize=20',
    )
    expect(request).toHaveBeenNthCalledWith(
      2,
      '/v1/api-apps/app-1/interfaces?keyword=detail',
    )
  })

  it('keeps app and interface write routes aligned with the control-plane contract', async () => {
    await interfaceLibraryApi.createApiApp('project-1', { name: '订单服务' })
    await interfaceLibraryApi.updateApiApp('app-1', { enabled: false })
    await interfaceLibraryApi.deleteApiApp('app-1')
    await interfaceLibraryApi.createApiInterface('app-1', {
      name: '查询订单',
      method: 'GET',
      path: '/orders/{orderId}',
    })
    await interfaceLibraryApi.updateApiInterface('api-1', { name: '订单详情' })
    await interfaceLibraryApi.deleteApiInterface('api-1')

    expect(vi.mocked(request).mock.calls.map(([url, options]) => [url, options?.method])).toEqual([
      ['/v1/projects/project-1/api-apps', 'POST'],
      ['/v1/api-apps/app-1', 'PATCH'],
      ['/v1/api-apps/app-1', 'DELETE'],
      ['/v1/api-apps/app-1/interfaces', 'POST'],
      ['/v1/api-interfaces/api-1', 'PATCH'],
      ['/v1/api-interfaces/api-1', 'DELETE'],
    ])
  })

  it('uploads the document as multipart for preview', async () => {
    const file = new File(['openapi: 3.0.0'], 'orders.yaml', { type: 'application/yaml' })
    await interfaceLibraryApi.previewOpenApiImport('app-1', file)

    const [url, options] = vi.mocked(request).mock.calls[0]
    expect(url).toBe('/v1/api-apps/app-1/interfaces/import/preview')
    expect(options?.method).toBe('POST')
    const form = options?.body as FormData
    expect((form.get('file') as File).name).toBe('orders.yaml')
    expect((form.get('file') as File).type).toBe('application/yaml')
  })

  it('sends the preview digest, selected keys and expected versions on commit', async () => {
    const file = new File(['openapi: 3.0.0'], 'orders.yaml', { type: 'application/yaml' })
    await interfaceLibraryApi.commitOpenApiImport('app-1', {
      file,
      sourceDigest: 'sha256-digest',
      selectedKeys: ['get:/orders/{orderId}'],
      expectedItems: { 'get:/orders/{orderId}': 3 },
      applyBasePath: true,
      expectedAppVersion: 7,
    })

    const [url, options] = vi.mocked(request).mock.calls[0]
    expect(url).toBe('/v1/api-apps/app-1/interfaces/import')
    const form = options?.body as FormData
    expect((form.get('file') as File).name).toBe('orders.yaml')
    expect(form.get('sourceDigest')).toBe('sha256-digest')
    expect(form.get('selectedKeys')).toBe(JSON.stringify(['get:/orders/{orderId}']))
    expect(form.get('expectedItems')).toBe(JSON.stringify({ 'get:/orders/{orderId}': 3 }))
    expect(form.get('applyBasePath')).toBe('true')
    expect(form.get('expectedAppVersion')).toBe('7')
  })
})
