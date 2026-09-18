import type { QueryClient } from '@tanstack/react-query'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'

/** Existing component fixtures represent a signed-in project owner. */
export function seedOwnerProject(client: QueryClient, projectId = 'project-1') {
  useWorkbenchStore.getState().setActiveProjectId(projectId)
  client.setQueryData(['projectAccess', projectId], { projectId, name: '测试项目', role: 'owner', permissions: ['read', 'write', 'execute', 'review', 'manage'] })
}
