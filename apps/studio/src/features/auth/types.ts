export type User = {
  userId?: string
  user_id?: string
  name: string
  nickname?: string
  email?: string
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type LoginResponse = {
  accessToken: string
}
