import { useQuery } from '@tanstack/react-query'
import { request } from '@/shared/api/request'

/** Presence is advisory; the queue remains authoritative. */
export function RunWaitingReason({ status }: { status?: string }) {
  const waiting = status === 'pending' || status === 'queued'
  const query = useQuery({
    queryKey: ['testRunAvailability'],
    queryFn: () => request<{ state: string }>('/v1/test-run-availability'),
    enabled: waiting,
    retry: false,
    staleTime: 30_000,
    refetchInterval: waiting ? 30_000 : false,
  })
  if (!waiting) return null
  const label = query.data?.state === 'offline' ? '暂未检测到执行节点'
    : query.data?.state === 'busy' ? '执行节点正忙，任务排队中'
      : query.data?.state === 'available' ? '正在分配执行节点' : '等待执行'
  return <span role="status">{label}</span>
}
