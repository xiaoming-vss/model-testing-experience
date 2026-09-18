import { request } from '@/shared/api/request'
import type { LoginResponse, User } from '../types'

export const authApi = {
  register: (body: { name: string; password: string; email?: string }) =>
    request<Record<string, never>>('/v1/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (body: { name: string; password: string }) =>
    request<LoginResponse>('/v1/login', { method: 'POST', body: JSON.stringify(body) }),
  getUser: () => request<User>('/v1/user'),
  updateUser: (body: Partial<Pick<User, 'name' | 'email'>>) =>
    request<Record<string, never>>('/v1/user', { method: 'PUT', body: JSON.stringify(body) }),
  deleteUser: () => request<Record<string, never>>('/v1/user', { method: 'DELETE' }),
}
