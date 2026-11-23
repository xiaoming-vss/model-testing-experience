import { useQuery } from '@tanstack/react-query'
import { usePaneActive } from '@/shared/ui/paneActivity'
import { bugsApi } from '../api/bugs.api'

/** Bug-only members receive labels, never full sprint or project-member resources. */
export function useBugScope(projectId: string | undefined, enabled: boolean) {
  // 隐藏的标签页不刷新迭代/成员选项，切回来后的下一个周期恢复。
  const paneActive = usePaneActive()
  const optionsQuery = useQuery({
    queryKey: ['bugOptions', projectId],
    queryFn: () => bugsApi.getBugOptions(projectId!),
    enabled: Boolean(projectId) && enabled,
    refetchInterval: enabled && paneActive ? 30_000 : false,
  })
  const sprints = optionsQuery.data?.sprints ?? []
  return {
    optionsQuery,
    members: optionsQuery.data?.members ?? [],
    sprints,
  }
}
