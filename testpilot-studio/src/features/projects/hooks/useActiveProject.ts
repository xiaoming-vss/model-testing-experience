import { useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { normalizeProjectId } from '@/utils/format'
import { useWorkbenchStore } from '../store/workbench.store'

export function useActiveProject() {
  const activeProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const setActiveProjectId = useWorkbenchStore((state) => state.setActiveProjectId)

  const projectsQuery = useQuery({
    queryKey: ['projects'],
    queryFn: api.getProjects,
    refetchInterval: 30_000,
  })

  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data])

  useEffect(() => {
    if (!projectsQuery.isSuccess) return
    if (projects.length === 0) {
      if (activeProjectId) setActiveProjectId(undefined)
      return
    }

    if (!activeProjectId) {
      setActiveProjectId(normalizeProjectId(projects[0]))
      return
    }

    if (!projects.some((project) => normalizeProjectId(project) === activeProjectId)) {
      setActiveProjectId(normalizeProjectId(projects[0]))
    }
  }, [activeProjectId, projects, projectsQuery.isSuccess, setActiveProjectId])

  return {
    activeProjectId,
    projects,
    projectsQuery,
    setActiveProjectId,
  }
}
