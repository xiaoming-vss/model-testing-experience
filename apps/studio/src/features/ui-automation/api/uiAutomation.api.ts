import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  CreateUiTestCasePayload,
  CreateUiTestSuitePayload,
  UiTestCase,
  UiTestCaseDebugRunPayload,
  UiTestCaseRun,
  RunUiTestSuitePayload,
  UiTestSuiteImportResult,
  UiTestSuite,
  UiTestSuiteRunReport,
  UiTestSuiteRunSummary,
  UpdateUiTestCasePayload,
  UpdateUiTestSuitePayload,
} from '../types'

export const uiAutomationApi = {
  getUiTestSuites: (requirementId: string) =>
    request<ListResponse<UiTestSuite>>(`/v1/requirements/${requirementId}/ui-test-suites`),
  createUiTestSuite: (requirementId: string, body: CreateUiTestSuitePayload) =>
    request<UiTestSuite>(`/v1/requirements/${requirementId}/ui-test-suites`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getUiTestSuite: (suiteId: string) => request<UiTestSuite>(`/v1/ui-test-suites/${suiteId}`),
  updateUiTestSuite: (suiteId: string, body: UpdateUiTestSuitePayload) =>
    request<UiTestSuite>(`/v1/ui-test-suites/${suiteId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteUiTestSuite: (suiteId: string) =>
    request<Record<string, never>>(`/v1/ui-test-suites/${suiteId}`, { method: 'DELETE' }),
  runUiTestSuite: (suiteId: string, body: RunUiTestSuitePayload) =>
    request<UiTestSuiteRunSummary>(`/v1/ui-test-suites/${suiteId}/run`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getUiTestSuiteRuns: (suiteId: string, params: { page?: number; pageSize?: number } = {}) =>
    request<ListResponse<UiTestSuiteRunSummary>>(
      `/v1/ui-test-suites/${suiteId}/runs${buildQuery(params)}`,
    ),
  getUiTestSuiteRun: (suiteRunId: string, signal?: AbortSignal) => request<UiTestSuiteRunSummary>(`/v1/ui-test-suite-runs/${suiteRunId}`, { signal }),
  getUiTestSuiteRunReport: (suiteRunId: string, signal?: AbortSignal) =>
    request<UiTestSuiteRunReport>(
      `/v1/ui-test-suite-runs/${suiteRunId}/report`,
      { signal },
      { normalizeListResponse: false },
    ),
  getUiTestCases: (suiteId: string) => request<ListResponse<UiTestCase>>(`/v1/ui-test-suites/${suiteId}/cases`),
  importUiTestCases: (suiteId: string, file: Blob, filename = 'import.yaml') => {
    const formData = new FormData()
    formData.append('file', file, filename)

    return request<UiTestSuiteImportResult>(`/v1/ui-test-suites/${suiteId}/import`, {
      method: 'POST',
      body: formData,
    })
  },
  createUiTestCase: (suiteId: string, body: CreateUiTestCasePayload) =>
    request<UiTestCase>(`/v1/ui-test-suites/${suiteId}/cases`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getUiTestCase: (caseId: string) => request<UiTestCase>(`/v1/ui-test-cases/${caseId}`),
  updateUiTestCase: (caseId: string, body: UpdateUiTestCasePayload) =>
    request<UiTestCase>(`/v1/ui-test-cases/${caseId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteUiTestCase: (caseId: string) =>
    request<Record<string, never>>(`/v1/ui-test-cases/${caseId}`, { method: 'DELETE' }),
  debugRunUiTestCase: (caseId: string, body: UiTestCaseDebugRunPayload) =>
    request<UiTestCaseRun>(`/v1/ui-test-cases/${caseId}/debug-run`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getUiTestCaseRun: (runId: string, signal?: AbortSignal) => request<UiTestCaseRun>(`/v1/ui-test-case-runs/${runId}`, { signal }),
}
