import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '@/shared/api/request'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { authApi } from '../api/auth.api'
import { useAuthStore } from '../store/auth.store'

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const token = useAuthStore.getState().token
      try {
        await authApi.logout()
      } catch (error) {
        // An expired or already revoked token is also safely logged out.
        if (!(error instanceof ApiError && error.status === 401)) throw error
      }
      return token
    },
    onSuccess: (token) => {
      const currentToken = useAuthStore.getState().token
      if (currentToken && currentToken !== token) return
      useAuthStore.getState().logout()
      queryClient.clear()
    },
    onError: (error) => {
      message.error(`退出登录失败，请重试：${getErrorMessage(error)}`)
    },
    retry: false,
  })
}
