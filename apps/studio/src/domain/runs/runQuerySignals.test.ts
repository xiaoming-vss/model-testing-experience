import { afterEach, expect, it, vi } from 'vitest'
import { apiAutomationApi } from '@/features/api-automation/api/apiAutomation.api'
import { uiAutomationApi } from '@/features/ui-automation/api/uiAutomation.api'

afterEach(() => vi.unstubAllGlobals())

it('passes cancellation to each API and UI execution snapshot request', async () => {
  const fetchMock = vi.fn<typeof fetch>(async () =>
    new Response(JSON.stringify({ code: 0, data: {} }), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  const controller = new AbortController()
  await Promise.all([
    apiAutomationApi.getApiCaseRun('run', controller.signal),
    apiAutomationApi.getApiCollectionRun('run', controller.signal),
    apiAutomationApi.getApiCollectionRunReport('run', controller.signal),
    uiAutomationApi.getUiTestCaseRun('run', controller.signal),
    uiAutomationApi.getUiTestSuiteRun('run', controller.signal),
    uiAutomationApi.getUiTestSuiteRunReport('run', controller.signal),
  ])
  expect(fetchMock).toHaveBeenCalledTimes(6)
  for (const [, options] of fetchMock.mock.calls) {
    expect((options as RequestInit).signal).toBe(controller.signal)
  }
})
