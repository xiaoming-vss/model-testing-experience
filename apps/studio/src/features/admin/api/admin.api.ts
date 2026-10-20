import { buildQuery, request, type ListResponse } from '@/shared/api/request'
import type { AdminUser, AdminUserListParams } from '../types'

export const adminApi = {
  listUsers: (params: AdminUserListParams = {}) =>
    request<ListResponse<AdminUser>>(
      `/v1/admin/users${buildQuery({
        search: params.search,
        status: params.status,
        page: params.page,
        pageSize: params.pageSize,
      })}`,
    ),
  disableUser: (userId: string, reason = '') =>
    request<AdminUser>(`/v1/admin/users/${userId}/disable`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  enableUser: (userId: string) =>
    request<AdminUser>(`/v1/admin/users/${userId}/enable`, { method: 'POST' }),
  resetPassword: (userId: string, newPassword: string) =>
    request<AdminUser>(`/v1/admin/users/${userId}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ newPassword }),
    }),
  revokeSessions: (userId: string) =>
    request<Record<string, never>>(`/v1/admin/users/${userId}/revoke-sessions`, {
      method: 'POST',
    }),
  updateEmail: (userId: string, email: string) =>
    request<AdminUser>(`/v1/admin/users/${userId}/email`, {
      method: 'PUT',
      body: JSON.stringify({ email }),
    }),
  deleteUser: (userId: string) =>
    request<Record<string, never>>(`/v1/admin/users/${userId}`, { method: 'DELETE' }),
}
