import type { QueryClient } from '@tanstack/react-query'

export function invalidateBug(client: QueryClient, bugId: string) {
  return Promise.all([
    client.invalidateQueries({ queryKey: ['bugs'] }),
    client.invalidateQueries({ queryKey: ['bug', bugId] }),
    client.invalidateQueries({ queryKey: ['bugActivities', bugId] }),
  ])
}
