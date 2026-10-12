import { useEffect, useEffectEvent, useRef } from 'react'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

/** A requirement workspace can open the existing task controller's dialogs directly. */
export type TaskRunDialogRequest = {
  taskId: string
  runId: string
  artifact: string
  mode: 'view' | 'review' | 'import'
  onClose: () => void
}

export function useTaskRunDialog(
  request: TaskRunDialogRequest | undefined,
  ready: boolean,
  visible: boolean,
  open: () => void,
  error?: unknown,
) {
  useEffect(() => {
    if (request && error) { message.error(getErrorMessage(error)); request.onClose() }
  }, [request, error])
  const wasVisible = useRef(false)
  const openDialog = useEffectEvent(open)
  useEffect(() => {
    if (!request || !ready || error) return
    // Open after page initialization effects. StrictMode cancels the first replay,
    // so cached data cannot leave a consumed request with no visible dialog.
    let canceled = false
    queueMicrotask(() => { if (!canceled) openDialog() })
    return () => { canceled = true }
  }, [request, ready, error])
  useEffect(() => {
    if (!request) return
    if (visible) wasVisible.current = true
    else if (wasVisible.current) {
      wasVisible.current = false
      request.onClose()
    }
  }, [request, visible])
}
