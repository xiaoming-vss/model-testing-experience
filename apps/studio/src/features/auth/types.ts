export type AuthMethod = 'local' | 'ldap'

export type AuthConfig = {
  ldapEnabled: boolean
  registrationEnabled: boolean
  localLoginAdminOnly: boolean
}

export type User = {
  authSource?: AuthMethod
  userId?: string
  user_id?: string
  name: string
  nickname?: string
  email?: string
  isSuperAdmin?: boolean
  is_super_admin?: boolean
  mustChangePassword?: boolean
  must_change_password?: boolean
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type LoginResponse = {
  accessToken: string
  mustChangePassword?: boolean
}
