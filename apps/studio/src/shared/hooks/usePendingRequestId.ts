import { useRef } from 'react'
import { randomId } from '@/shared/utils/crypto'

/** Reuse the same identity after an ambiguous failure, and rotate it after success. */
export function usePendingRequestId() {
  const pending = useRef<{ key: string; id: string } | undefined>(undefined)
  return {
    forInput(key: string) {
      if (pending.current?.key !== key) pending.current = { key, id: randomId() }
      return pending.current.id
    },
    clear() { pending.current = undefined },
  }
}
