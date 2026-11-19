import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'

afterEach(() => vi.unstubAllGlobals())

it('passes cancellation to each API and UI execution snapshot request', async () => {
  const fetchMock = vi.fn<typeof fetch>(async () =>
    new Response(JSON.stringify({ code: 0, data: {} }), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  const controller = new AbortController()
  await Promise.all([
    api.getApiCaseRun('run', controller.signal),
    api.getApiCollectionRun('run', controller.signal),
    api.getApiCollectionRunReport('run', controller.signal),
    api.getUiTestCaseRun('run', controller.signal),
    api.getUiTestSuiteRun('run', controller.signal),
    api.getUiTestSuiteRunReport('run', controller.signal),
  ])
  expect(fetchMock).toHaveBeenCalledTimes(6)
  for (const [, options] of fetchMock.mock.calls) {
    expect((options as RequestInit).signal).toBe(controller.signal)
  }
})
