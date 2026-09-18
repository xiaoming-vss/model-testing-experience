import { request, type ListResponse } from '@/shared/api/request'
import type {
  ApiAssertRule,
  ApiCase,
  ApiCaseRunResult,
  ApiCollection,
  ApiCollectionImportResult,
  ApiCollectionRunReport,
  ApiCollectionRunSummary,
  ApiEnvironment,
  ApiEnvironmentVar,
  ApiExtractRule,
  CreateApiAssertRulePayload,
  CreateApiCasePayload,
  CreateApiCollectionPayload,
  CreateApiEnvironmentPayload,
  CreateApiEnvironmentVarPayload,
  CreateApiExtractRulePayload,
  RunApiCasePayload,
  RunApiCollectionPayload,
  UpdateApiAssertRulePayload,
  UpdateApiCasePayload,
  UpdateApiCollectionPayload,
  UpdateApiEnvironmentPayload,
  UpdateApiEnvironmentVarPayload,
  UpdateApiExtractRulePayload,
} from '../types'

export const apiAutomationApi = {
  getApiCollections: (requirementId: string) =>
    request<ListResponse<ApiCollection>>(`/v1/requirements/${requirementId}/api-collections`),
  createApiCollection: (requirementId: string, body: CreateApiCollectionPayload) =>
    request<ApiCollection>(`/v1/requirements/${requirementId}/api-collections`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getApiCollection: (collectionId: string) => request<ApiCollection>(`/v1/api-collections/${collectionId}`),
  updateApiCollection: (collectionId: string, body: UpdateApiCollectionPayload) =>
    request<ApiCollection>(`/v1/api-collections/${collectionId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteApiCollection: (collectionId: string) =>
    request<Record<string, never>>(`/v1/api-collections/${collectionId}`, { method: 'DELETE' }),
  getApiEnvironments: (projectId: string) => request<ListResponse<ApiEnvironment>>(`/v1/projects/${projectId}/api-environments`),
  createApiEnvironment: (projectId: string, body: CreateApiEnvironmentPayload) =>
    request<ApiEnvironment>(`/v1/projects/${projectId}/api-environments`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getApiEnvironment: (environmentId: string) => request<ApiEnvironment>(`/v1/api-environments/${environmentId}`),
  updateApiEnvironment: (environmentId: string, body: UpdateApiEnvironmentPayload) =>
    request<ApiEnvironment>(`/v1/api-environments/${environmentId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteApiEnvironment: (environmentId: string) =>
    request<Record<string, never>>(`/v1/api-environments/${environmentId}`, { method: 'DELETE' }),
  getApiEnvironmentVars: (environmentId: string) =>
    request<ListResponse<ApiEnvironmentVar>>(`/v1/api-environments/${environmentId}/vars`),
  createApiEnvironmentVar: (environmentId: string, body: CreateApiEnvironmentVarPayload) =>
    request<ApiEnvironmentVar>(`/v1/api-environments/${environmentId}/vars`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getApiEnvironmentVar: (envVarId: string) => request<ApiEnvironmentVar>(`/v1/api-environment-vars/${envVarId}`),
  updateApiEnvironmentVar: (envVarId: string, body: UpdateApiEnvironmentVarPayload) =>
    request<ApiEnvironmentVar>(`/v1/api-environment-vars/${envVarId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteApiEnvironmentVar: (envVarId: string) =>
    request<Record<string, never>>(`/v1/api-environment-vars/${envVarId}`, { method: 'DELETE' }),
  getApiCases: (collectionId: string) => request<ListResponse<ApiCase>>(`/v1/api-collections/${collectionId}/cases`),
  createApiCase: (collectionId: string, body: CreateApiCasePayload) =>
    request<ApiCase>(`/v1/api-collections/${collectionId}/cases`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  importApiCases: (collectionId: string, file: Blob, filename = 'import.yaml') => {
    const formData = new FormData()
    formData.append('file', file, filename)

    return request<ApiCollectionImportResult>(`/v1/api-collections/${collectionId}/import`, {
      method: 'POST',
      body: formData,
    })
  },
  getApiCase: (caseId: string) => request<ApiCase>(`/v1/api-cases/${caseId}`),
  updateApiCase: (caseId: string, body: UpdateApiCasePayload) =>
    request<ApiCase>(`/v1/api-cases/${caseId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteApiCase: (caseId: string) =>
    request<Record<string, never>>(`/v1/api-cases/${caseId}`, { method: 'DELETE' }),
  getApiAssertRules: (caseId: string) => request<ListResponse<ApiAssertRule>>(`/v1/api-cases/${caseId}/assert-rules`),
  createApiAssertRule: (caseId: string, body: CreateApiAssertRulePayload) =>
    request<ApiAssertRule>(`/v1/api-cases/${caseId}/assert-rules`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getApiAssertRule: (assertRuleId: string) => request<ApiAssertRule>(`/v1/api-assert-rules/${assertRuleId}`),
  updateApiAssertRule: (assertRuleId: string, body: UpdateApiAssertRulePayload) =>
    request<ApiAssertRule>(`/v1/api-assert-rules/${assertRuleId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteApiAssertRule: (assertRuleId: string) =>
    request<Record<string, never>>(`/v1/api-assert-rules/${assertRuleId}`, { method: 'DELETE' }),
  getApiExtractRules: (caseId: string) => request<ListResponse<ApiExtractRule>>(`/v1/api-cases/${caseId}/extract-rules`),
  createApiExtractRule: (caseId: string, body: CreateApiExtractRulePayload) =>
    request<ApiExtractRule>(`/v1/api-cases/${caseId}/extract-rules`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getApiExtractRule: (extractRuleId: string) => request<ApiExtractRule>(`/v1/api-extract-rules/${extractRuleId}`),
  updateApiExtractRule: (extractRuleId: string, body: UpdateApiExtractRulePayload) =>
    request<ApiExtractRule>(`/v1/api-extract-rules/${extractRuleId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteApiExtractRule: (extractRuleId: string) =>
    request<Record<string, never>>(`/v1/api-extract-rules/${extractRuleId}`, { method: 'DELETE' }),
  runApiCase: (caseId: string, body: RunApiCasePayload) =>
    request<ApiCaseRunResult>(`/v1/api-cases/${caseId}/run`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getApiCaseRun: (runId: string) =>
    request<ApiCaseRunResult>(`/v1/api-case-runs/${runId}`),
  runApiCollection: (collectionId: string, body: RunApiCollectionPayload) =>
    request<ApiCollectionRunSummary>(`/v1/api-collections/${collectionId}/run`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getApiCollectionRuns: (collectionId: string) =>
    request<ListResponse<ApiCollectionRunSummary>>(`/v1/api-collections/${collectionId}/runs`),
  getApiCollectionRun: (collectionRunId: string) =>
    request<ApiCollectionRunSummary>(`/v1/api-collection-runs/${collectionRunId}`),
  getApiCollectionRunReport: (collectionRunId: string) =>
    request<ApiCollectionRunReport>(`/v1/api-collection-runs/${collectionRunId}/report`),
}
