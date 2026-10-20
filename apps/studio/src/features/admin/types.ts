export type AdminUser = {
  userId: string
  name: string
  email?: string | null
  status: 'active' | 'disabled' | 'pending_ldap'
  authSource?: 'local' | 'ldap'
  isSuperAdmin: boolean
  mustChangePassword: boolean
  disabledAt?: string | null
  disabledReason?: string
  createdAt?: string | null
  updatedAt?: string | null
}

export type AdminUserListParams = {
  search?: string
  status?: '' | 'active' | 'disabled' | 'pending_ldap'
  page?: number
  pageSize?: number
}
