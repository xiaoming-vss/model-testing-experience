import { request, type ListResponse } from '@/shared/api/request'
import type { ZentaoRemoteOption } from '../types'

export const zentaoMcpApi = {
  resources: (projectId: string, kind: 'projects' | 'executions' | 'stories', parentId?: string, mcpServiceId?: string) => {
    const query = new URLSearchParams()
    if (parentId) query.set('parentId', parentId)
    if (mcpServiceId) query.set('mcpServiceId', mcpServiceId)
    return request<ListResponse<ZentaoRemoteOption>>(`/v1/projects/${encodeURIComponent(projectId)}/zentao/mcp/${kind}${query.size ? `?${query}` : ''}`)
  },
}
