import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  CreateMonitoringConnectionPayload,
  CreatePerfCasePayload,
  MonitoringConnection,
  PerfCase,
  PerfCaseSummary,
  PerfRun,
  PerfRunSummary,
  StartPerfRunPayload,
  UpdateMonitoringConnectionPayload,
  UpdatePerfCasePayload,
} from '../types'

export const performanceApi = {
  listPerfCases: (projectId: string) =>
    request<ListResponse<PerfCaseSummary>>(`/v1/projects/${projectId}/perf-cases`),
  getPerfCase: (caseId: string) => request<PerfCase>(`/v1/perf-cases/${caseId}`),
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
    params: { caseId?: string; status?: string; page?: number; pageSize?: number } = {},
  ) => request<ListResponse<PerfRunSummary>>(`/v1/projects/${projectId}/perf-runs${buildQuery(params)}`),
  getPerfRun: (runId: string) => request<PerfRun>(`/v1/perf-runs/${runId}`),
  stopPerfRun: (runId: string) =>
    request<Record<string, never>>(`/v1/perf-runs/${runId}/stop`, { method: 'POST' }),
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
