import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  CreateMonitoringConnectionPayload,
  CreatePerfCasePayload,
  CreatePerfSuitePayload,
  MonitoringConnection,
  PerfCase,
  PerfRun,
  PerfRunSummary,
  PerfSuite,
  PerfSuiteRun,
  PerfSuiteRunSummary,
  PerfSuiteSummary,
  StartPerfRunPayload,
  StartPerfSuiteRunPayload,
  UpdateMonitoringConnectionPayload,
  UpdatePerfCasePayload,
  UpdatePerfSuitePayload,
} from '../types'

export const performanceApi = {
  batchInvalidatePerfCases: (projectId: string, caseIds: string[], invalidated: boolean) =>
    request<{ caseIds: string[]; updatedCount: number }>(
      `/v1/projects/${projectId}/perf-cases/batch-invalidation`,
      { method: 'POST', body: JSON.stringify({ caseIds, invalidated }) },
    ),
  createPerfCase: (projectId: string, body: CreatePerfCasePayload) =>
    request<PerfCase>(`/v1/projects/${projectId}/perf-cases`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updatePerfCase: (caseId: string, body: UpdatePerfCasePayload) =>
    request<PerfCase>(`/v1/perf-cases/${caseId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deletePerfCase: (caseId: string) =>
    request<Record<string, never>>(`/v1/perf-cases/${caseId}`, { method: 'DELETE' }),
  startPerfRun: (caseId: string, body: StartPerfRunPayload) =>
    request<PerfRun>(`/v1/perf-cases/${caseId}/runs`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  listPerfRuns: (
    projectId: string,
    params: {
      caseId?: string
      status?: string
      triggerType?: 'manual' | 'suite'
      page?: number
      pageSize?: number
    } = {},
  ) => request<ListResponse<PerfRunSummary>>(`/v1/projects/${projectId}/perf-runs${buildQuery(params)}`),
  getPerfRun: (runId: string) => request<PerfRun>(`/v1/perf-runs/${runId}`),
  stopPerfRun: (runId: string) =>
    request<Record<string, never>>(`/v1/perf-runs/${runId}/stop`, { method: 'POST' }),
  listPerfSuites: (projectId: string) =>
    request<ListResponse<PerfSuiteSummary>>(`/v1/projects/${projectId}/perf-suites`),
  getPerfSuite: (suiteId: string) => request<PerfSuite>(`/v1/perf-suites/${suiteId}`),
  createPerfSuite: (projectId: string, body: CreatePerfSuitePayload) =>
    request<PerfSuite>(`/v1/projects/${projectId}/perf-suites`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updatePerfSuite: (suiteId: string, body: UpdatePerfSuitePayload) =>
    request<PerfSuite>(`/v1/perf-suites/${suiteId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deletePerfSuite: (suiteId: string) =>
    request<Record<string, never>>(`/v1/perf-suites/${suiteId}`, { method: 'DELETE' }),
  startPerfSuiteRun: (suiteId: string, body: StartPerfSuiteRunPayload) =>
    request<PerfSuiteRun>(`/v1/perf-suites/${suiteId}/runs`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  listPerfSuiteRuns: (
    projectId: string,
    params: { suiteId?: string; status?: string; page?: number; pageSize?: number } = {},
  ) =>
    request<ListResponse<PerfSuiteRunSummary>>(
      `/v1/projects/${projectId}/perf-suite-runs${buildQuery(params)}`,
    ),
  getPerfSuiteRun: (suiteRunId: string) =>
    request<PerfSuiteRun>(`/v1/perf-suite-runs/${suiteRunId}`),
  stopPerfSuiteRun: (suiteRunId: string) =>
    request<Record<string, never>>(`/v1/perf-suite-runs/${suiteRunId}/stop`, { method: 'POST' }),
  listMonitoringConnections: (projectId: string) =>
    request<ListResponse<MonitoringConnection>>(`/v1/projects/${projectId}/monitoring-connections`),
  createMonitoringConnection: (projectId: string, body: CreateMonitoringConnectionPayload) =>
    request<MonitoringConnection>(`/v1/projects/${projectId}/monitoring-connections`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateMonitoringConnection: (connectionId: string, body: UpdateMonitoringConnectionPayload) =>
    request<MonitoringConnection>(`/v1/monitoring-connections/${connectionId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteMonitoringConnection: (connectionId: string) =>
    request<Record<string, never>>(`/v1/monitoring-connections/${connectionId}`, {
      method: 'DELETE',
    }),
}
