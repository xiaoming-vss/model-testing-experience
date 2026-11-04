import { Button } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { request } from '@/shared/api/request'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

type RunKind = 'api-case' | 'api-collection' | 'ui-case' | 'ui-suite'

const keys: Record<RunKind, string[]> = {
  'api-case': ['apiCaseRun'],
  'api-collection': ['apiCollectionRun', 'apiCollectionRunReport'],
  'ui-case': ['uiTestCaseRun'],
  'ui-suite': ['uiTestSuiteRun', 'uiTestSuiteRunReport'],
}

export function StopRunButton({ kind, runId, status }: { kind: RunKind; runId?: string; status?: string }) {
  const client = useQueryClient()
  const stop = useMutation({
    mutationFn: () => request<{ status: string }>(`/v1/test-runs/${kind}/${encodeURIComponent(runId ?? '')}/stop`, { method: 'POST' }),
    onSuccess: () => {
      for (const key of keys[kind]) void client.invalidateQueries({ queryKey: [key, runId] })
    },
    onError: (error) => { message.error(getErrorMessage(error)) },
  })
  if (!runId || !status || !['pending', 'queued', 'claimed', 'running', 'stopping'].includes(status)) return null
  return (
    <Button size="small" danger loading={stop.isPending} disabled={status === 'stopping'} onClick={() => stop.mutate()}>
      {status === 'stopping' ? '正在停止' : '停止'}
    </Button>
  )
}
