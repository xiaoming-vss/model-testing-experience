import { useEffect } from 'react'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

export function useQueryErrorToast(error: unknown, key: string) {
  useEffect(() => {
    if (error) message.error({ key, content: getErrorMessage(error) })
  }, [error, key])
}
