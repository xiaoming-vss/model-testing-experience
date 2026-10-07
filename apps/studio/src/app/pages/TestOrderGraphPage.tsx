import { useEffect } from 'react'
import { Alert, Button, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { useCurrentUser } from '@/features/auth/hooks/useCurrentUser'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { TestOrderGraphViewer } from '@/features/test-orders/components/TestOrderGraphViewer'
import { TestOrderGraphPageShell } from '@/features/test-orders/components/TestOrderGraphPageShell'
import { api } from '@/services/api'
import { getErrorMessage } from '@/utils/format'

export function TestOrderGraphPage() {
  const { orderId = '' } = useParams<{ orderId: string }>()
  useCurrentUser()
  const currentUserId = useAuthStore((state) => state.user?.userId)
  const orderQuery = useQuery({
    queryKey: ['testOrder', orderId],
    queryFn: () => api.getTestOrder(orderId),
    enabled: Boolean(orderId),
    refetchOnWindowFocus: true,
  })
  const order = orderQuery.data
  const { project, can, loading, error } = useProjectAccess(order?.projectId)
  const sprintQuery = useQuery({
    queryKey: ['sprint', order?.sprintId],
    queryFn: () => api.getSprint(order!.sprintId!),
    enabled: Boolean(order?.sprintId) && can('read'),
  })
  useEffect(() => {
    const previousTitle = document.title
    document.title = `${order?.name ? `${order.name} · ` : ''}用例图谱 · MTX`
    return () => { document.title = previousTitle }
  }, [order?.name])

  let content
  if (orderQuery.isError) {
    content = <Alert type="error" showIcon title={getErrorMessage(orderQuery.error)} action={<Button onClick={() => void orderQuery.refetch()}>重试</Button>} />
  } else if (orderQuery.isPending || loading) {
    content = <Spin aria-label="图谱页面加载中" />
  } else if (error || !can('read')) {
    content = <Alert type="error" showIcon title={error ? '项目权限加载失败，请刷新重试' : '没有查看此测试单图谱的权限'} />
  } else {
    content = <TestOrderGraphViewer orderId={orderId} projectId={order?.projectId} canExecute={can('execute')} currentUserId={currentUserId} isProjectOwner={project?.role === 'owner'} />
  }
  return (
    <TestOrderGraphPageShell order={order} projectName={order?.projectId ? project?.name : undefined} sprintName={sprintQuery.data?.name}>
      {content}
    </TestOrderGraphPageShell>
  )
}
