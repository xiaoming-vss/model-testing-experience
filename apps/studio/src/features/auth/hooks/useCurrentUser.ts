import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { useAuthStore } from '../store/auth.store'

export function useCurrentUser() {
  const token = useAuthStore((state) => state.token)
  const setUser = useAuthStore((state) => state.setUser)

  const userQuery = useQuery({
    queryKey: ['user'],
    queryFn: api.getUser,
    enabled: Boolean(token),
  })

  useEffect(() => {
    if (userQuery.data) {
      setUser(userQuery.data)
    }
  }, [setUser, userQuery.data])

  return {
    token,
    userQuery,
  }
}
