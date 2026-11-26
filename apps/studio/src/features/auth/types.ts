export type AuthMethod = 'local' | 'ldap'

export type AuthConfig = {
  ldapEnabled: boolean
  registrationEnabled: boolean
  localLoginAdminOnly: boolean
}

export type User = {
  authSource?: AuthMethod
  userId?: string
  name: string
  nickname?: string
  email?: string
  isSuperAdmin?: boolean
  mustChangePassword?: boolean
  createdAt?: string
  updatedAt?: string
}

export type LoginResponse = {
  accessToken: string
  mustChangePassword?: boolean
}
