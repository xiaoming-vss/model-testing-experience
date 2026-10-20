import { request } from '@/shared/api/request'
import type { AuthConfig, AuthMethod, LoginResponse, User } from '../types'
import { useAuthStore } from '../store/auth.store'

export function getAuthenticatedUserId() {
  const user = useAuthStore.getState().user
  return user?.userId ?? user?.user_id ?? null
}

export const authApi = {
  getAuthConfig: () => request<AuthConfig>('/v1/auth/config'),
  register: (body: { name: string; password: string; email: string }) =>
    request<User>('/v1/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (body: { name: string; password: string; authMethod?: AuthMethod }) =>
    request<LoginResponse>('/v1/login', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => request<Record<string, never>>('/v1/logout', { method: 'POST' }),
  getUser: () => request<User>('/v1/user'),
  updateUser: (body: Partial<Pick<User, 'email'>>) =>
    request<User>('/v1/user', { method: 'PUT', body: JSON.stringify(body) }),
  changePassword: (body: { oldPassword: string; newPassword: string }) =>
    request<Record<string, never>>('/v1/user/password', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
}
