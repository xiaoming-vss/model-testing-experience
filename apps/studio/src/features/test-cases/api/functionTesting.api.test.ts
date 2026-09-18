import { beforeEach, describe, expect, it, vi } from 'vitest'
import { request } from '@/shared/api/request'
import { functionTestingApi } from './functionTesting.api'

vi.mock('@/shared/api/request', () => ({ request: vi.fn() }))

const requestMock = vi.mocked(request)

describe('function testing API', () => {
  beforeEach(() => requestMock.mockReset())

  it('imports selected suites with one requirement-scoped request', () => {
    const body = {
      productId: 1,
      moduleId: 0,
      suiteIds: ['suite-1', 'suite-2'],
    }

    functionTestingApi.importFunctionTestSuitesToZentao('req-1', body)

    expect(requestMock).toHaveBeenCalledOnce()
    expect(requestMock).toHaveBeenCalledWith('/v1/requirements/req-1/zentao/testcases/import', {
      method: 'POST',
      body: JSON.stringify(body),
    }, { normalizeListResponse: false })
  })
})
