import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  CreateFunctionTestCasePayload,
  CreateFunctionTestSuitePayload,
  FunctionCaseLibraryFilters,
  FunctionCaseLibraryItem,
  FunctionTestCase,
  FunctionTestCaseImportResult,
  FunctionTestCaseZentaoImportResult,
  FunctionTestSuitesZentaoImportResult,
  FunctionTestSuite,
  ImportFunctionTestCasesToZentaoPayload,
  ImportFunctionTestSuitesToZentaoPayload,
  UpdateFunctionTestCasePayload,
  UpdateFunctionTestSuitePayload,
} from '../types'

export const functionTestingApi = {
  getFunctionTestSuites: (requirementId: string) =>
    request<ListResponse<FunctionTestSuite>>(`/v1/requirements/${requirementId}/function-test-suites`),
  // 项目范围：一次取回该项目下（可按迭代/需求筛选）的全部测试集，替代按需求逐个请求。
  getProjectFunctionTestSuites: (
    projectId: string,
    filters: { sprintId?: string; requirementId?: string } = {},
  ) =>
    request<ListResponse<FunctionTestSuite>>(
      `/v1/projects/${projectId}/function-test-suites${buildQuery({ ...filters })}`,
    ),
  // 项目范围：用例库检索，服务端筛选并分页。
  getProjectFunctionTestCases: (projectId: string, filters: FunctionCaseLibraryFilters = {}) =>
    request<ListResponse<FunctionCaseLibraryItem>>(
      `/v1/projects/${projectId}/function-test-cases${buildQuery({ ...filters })}`,
    ),
  createFunctionTestSuite: (requirementId: string, body: CreateFunctionTestSuitePayload) =>
    request<FunctionTestSuite>(`/v1/requirements/${requirementId}/function-test-suites`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getFunctionTestSuite: (suiteId: string) => request<FunctionTestSuite>(`/v1/function-test-suites/${suiteId}`),
  updateFunctionTestSuite: (suiteId: string, body: UpdateFunctionTestSuitePayload) =>
    request<FunctionTestSuite>(`/v1/function-test-suites/${suiteId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteFunctionTestSuite: (suiteId: string) =>
    request<Record<string, never>>(`/v1/function-test-suites/${suiteId}`, { method: 'DELETE' }),
  getFunctionTestCases: (suiteId: string) =>
    request<ListResponse<FunctionTestCase>>(`/v1/function-test-suites/${suiteId}/cases`),
  importFunctionTestCases: (suiteId: string, file: Blob, filename = 'import.json') => {
    const formData = new FormData()
    formData.append('file', file, filename)
    return request<FunctionTestCaseImportResult>(`/v1/function-test-suites/${suiteId}/cases/import`, {
      method: 'POST',
      body: formData,
    })
  },
  importFunctionTestCasesToZentao: (suiteId: string, body: ImportFunctionTestCasesToZentaoPayload) =>
    request<FunctionTestCaseZentaoImportResult>(`/v1/function-test-suites/${suiteId}/zentao/testcases/import`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  importFunctionTestSuitesToZentao: (requirementId: string, body: ImportFunctionTestSuitesToZentaoPayload) =>
    request<FunctionTestSuitesZentaoImportResult>(`/v1/requirements/${requirementId}/zentao/testcases/import`, {
      method: 'POST',
      body: JSON.stringify(body),
    }, { normalizeListResponse: false }),
  createFunctionTestCase: (suiteId: string, body: CreateFunctionTestCasePayload) =>
    request<FunctionTestCase>(`/v1/function-test-suites/${suiteId}/cases`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getFunctionTestCase: (caseId: string) => request<FunctionTestCase>(`/v1/function-test-cases/${caseId}`),
  updateFunctionTestCase: (caseId: string, body: UpdateFunctionTestCasePayload) =>
    request<FunctionTestCase>(`/v1/function-test-cases/${caseId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  batchDeleteFunctionTestCases: (suiteId: string, caseIds: string[]) =>
    request<{ deletedIds: string[]; deletedCount: number }>(`/v1/function-test-suites/${suiteId}/cases/batch-delete`, {
      method: 'POST',
      body: JSON.stringify({ caseIds }),
    }),
  deleteFunctionTestCase: (caseId: string) =>
    request<Record<string, never>>(`/v1/function-test-cases/${caseId}`, { method: 'DELETE' }),
}
