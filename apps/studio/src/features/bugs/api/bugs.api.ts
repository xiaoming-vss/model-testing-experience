import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  Bug,
  BugOptions,
  BugZentaoPush,
  BugZentaoPushOptions,
  BugZentaoPushPayload,
  BugZentaoUpdatePayload,
  BugZentaoJob,
  BugActivity,
  BugListFilters,
  BugTransitionPayload,
  CreateBugPayload,
  UpdateBugPayload,
  ZentaoBugCandidate,
  ZentaoBugImportItemPayload,
  ZentaoBugImportPreview,
  ZentaoBugImportResult,
  ZentaoPullGroupPayload,
  ZentaoPullResult,
  ZentaoRemotePreview,
} from '../types'

export const bugsApi = {
  getBugOptions: (projectId: string) =>
    request<BugOptions>(`/v1/projects/${projectId}/bugs/options`),
  getProjectBugs: (projectId: string, filters: BugListFilters = {}) =>
    request<ListResponse<Bug>>(`/v1/projects/${projectId}/bugs${buildQuery({ ...filters, confirmed: filters.confirmed === undefined ? undefined : String(filters.confirmed) })}`),
  createBug: (projectId: string, body: CreateBugPayload) =>
    request<Bug>(`/v1/projects/${projectId}/bugs`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getBug: (bugId: string) => request<Bug>(`/v1/bugs/${bugId}`),
  getBugZentaoPush: (bugId: string) => request<BugZentaoPush>(`/v1/bugs/${bugId}/zentao-push`),
  getBugZentaoPushOptions: (bugId: string) => request<BugZentaoPushOptions>(`/v1/bugs/${bugId}/zentao-push/options`),
  submitBugZentaoSync: (bugId: string, body: Partial<BugZentaoPushPayload> & { requestId: string }) =>
    request<BugZentaoJob>(`/v1/bugs/${bugId}/zentao-sync-jobs`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  submitBugZentaoFields: (bugId: string, body: BugZentaoUpdatePayload & { requestId: string }) =>
    request<BugZentaoJob>(`/v1/bugs/${bugId}/zentao-field-update-jobs`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  getBugZentaoJob: (bugId: string, jobId: string) =>
    request<BugZentaoJob>(`/v1/bugs/${bugId}/zentao-jobs/${jobId}`),
  reconcileBugZentaoPush: (bugId: string, remoteBugId: number) => request<BugZentaoPush>(`/v1/bugs/${bugId}/zentao-push/reconcile`, {
    method: 'POST', body: JSON.stringify({ remoteBugId }),
  }),
  listZentaoBugCandidates: (
    projectId: string,
    params: { status?: string; keyword?: string; executionId?: number; page?: number; pageSize?: number } = {},
  ) =>
    request<ListResponse<ZentaoBugCandidate>>(
      `/v1/projects/${projectId}/zentao/bug-imports/candidates${buildQuery(params)}`,
    ),
  previewZentaoBugImport: (projectId: string, remoteBugIds: number[]) =>
    request<{ items: ZentaoBugImportPreview[] }>(
      `/v1/projects/${projectId}/zentao/bug-imports/preview`,
      { method: 'POST', body: JSON.stringify({ remoteBugIds }) },
    ),
  importZentaoBugs: (
    projectId: string,
    body: { requestId: string; items: ZentaoBugImportItemPayload[] },
  ) =>
    request<{ items: ZentaoBugImportResult[] }>(`/v1/projects/${projectId}/zentao/bug-imports`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getBugZentaoRemote: (bugId: string) => request<ZentaoRemotePreview>(`/v1/bugs/${bugId}/zentao-remote`),
  pullBugZentao: (bugId: string, body: { remoteDigest: string; groups: ZentaoPullGroupPayload[] }) =>
    request<ZentaoPullResult>(`/v1/bugs/${bugId}/zentao-pull`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateBug: (bugId: string, body: UpdateBugPayload) =>
    request<Bug>(`/v1/bugs/${bugId}`, { method: 'PATCH', body: JSON.stringify(body) }),
  transitionBug: (bugId: string, body: BugTransitionPayload) =>
    request<Bug>(`/v1/bugs/${bugId}/transition`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  transferBug: (bugId: string, assigneeUserId: string) =>
    request<Bug>(`/v1/bugs/${bugId}/transfer`, {
      method: 'POST',
      body: JSON.stringify({ assigneeUserId }),
    }),
  commentBug: (bugId: string, content: string) =>
    request<Record<string, never>>(`/v1/bugs/${bugId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
  getBugActivities: (bugId: string) =>
    request<ListResponse<BugActivity>>(`/v1/bugs/${bugId}/activities`),
  downloadAttachment: (fileId: string) =>
    request<{ url: string; filename: string; size: number }>(`/v1/files/${fileId}/download`),
}
