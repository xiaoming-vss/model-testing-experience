import { afterEach, expect, it, vi } from 'vitest'
import { functionTestingApi } from './functionTesting.api'

afterEach(() => vi.unstubAllGlobals())

it('preserves partial push status and counts instead of normalizing the response to a list', async () => {
  const data = { status: 'partial_failure', suiteId: 'suite', importedCaseCount: 1,
    items: [{ caseId: 'case', remoteCaseId: 0, status: 'uncertain', errorMessage: '请核对' }] }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 0, data }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  })))
  const result = await functionTestingApi.importFunctionTestCasesToZentao('suite', { productId: 9 })
  expect(result).toEqual(data)
  expect(Array.isArray(result)).toBe(false)
})
