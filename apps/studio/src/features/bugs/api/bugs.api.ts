import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type {
  Bug,
  BugActivity,
  BugListFilters,
  BugTransitionPayload,
  CreateBugPayload,
  UpdateBugPayload,
} from '../types'

export const bugsApi = {
  getProjectBugs: (projectId: string, filters: BugListFilters = {}) =>
    request<ListResponse<Bug>>(`/v1/projects/${projectId}/bugs${buildQuery({ ...filters })}`),
  createBug: (projectId: string, body: CreateBugPayload) =>
    request<Bug>(`/v1/projects/${projectId}/bugs`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getBug: (bugId: string) => request<Bug>(`/v1/bugs/${bugId}`),
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
