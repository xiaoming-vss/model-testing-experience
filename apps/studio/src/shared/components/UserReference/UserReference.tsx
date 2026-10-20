import { Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { listItems } from '@/shared/api/request'

export const DELETED_ACCOUNT_LABEL = '已删除账户'

export function DeletedAccountLabel() {
  return <Tag bordered={false}>{DELETED_ACCOUNT_LABEL}</Tag>
}

export function UserDisplayName({ name }: { name: string }) {
  return name === DELETED_ACCOUNT_LABEL ? <DeletedAccountLabel /> : <>{name}</>
}

export function UserReference({
  projectId,
  userId,
  fallback = '-',
}: {
  projectId?: string
  userId?: string
  fallback?: string
}) {
  const membersQuery = useQuery({
    queryKey: ['projectMembers', projectId],
    queryFn: () => api.getProjectMembers(projectId!),
    enabled: Boolean(projectId && userId),
    staleTime: 30_000,
  })
  if (!userId) return <>{fallback}</>
  if (membersQuery.isPending) return <>{userId}</>
  const member = listItems(membersQuery.data).find((item) => item.userId === userId)
  return member ? <>{member.name}</> : <DeletedAccountLabel />
}
