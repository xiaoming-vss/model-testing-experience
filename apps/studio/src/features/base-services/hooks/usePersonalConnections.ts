import { useQuery } from '@tanstack/react-query'
import { api, listItems } from '@/services/api'
import { normalizeInstanceUrl, personalConnectionForInstance } from '../utils/personalConnections'

export function usePersonalConnections(projectId: string, provider: 'gitlab', selected: Record<string, string>) {
  const query = useQuery({ queryKey: [`${provider}Connections`, projectId], queryFn: () => api.getGitlabConnections(projectId), enabled: Boolean(projectId) })
  const connections = listItems(query.data)
  const resolve = (instance: string) => personalConnectionForInstance(connections, instance, selected[normalizeInstanceUrl(instance)])?.connectionId ?? ''
  return { query, connections, resolve }
}
