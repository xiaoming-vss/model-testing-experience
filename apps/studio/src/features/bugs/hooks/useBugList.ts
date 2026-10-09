import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { api, listItems, listTotal } from '@/services/api'
import type { Bug, BugAction } from '../types'
import { bugColumns } from '../components/bugColumns'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { useBugScope } from './useBugScope'
export function useBugList() {
  const navigate = useNavigate()
  const activeProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const access = useProjectAccess(activeProjectId)
  const bugOnly = access.project?.role === 'developer'
  const sprintScope = useActiveSprint(access.can('read'))
  const bugScope = useBugScope(activeProjectId, bugOnly)
  const { activeSprintId, sprints, sprintsQuery, selectSprint, sprintSelectorOptions } =
    bugOnly ? bugScope : sprintScope

  const [status, setStatus] = useState<string>('')
  const [confirmed, setConfirmed] = useState<boolean | undefined>()
  const [resolution, setResolution] = useState('')
  const [severity, setSeverity] = useState<string>('')
  const [assigneeUserId, setAssigneeUserId] = useState<string>('')
  const [keyword, setKeyword] = useState<string>('')
  const [optionalColumns, setOptionalColumns] = useState<string[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [transition, setTransition] = useState<{ bug: Bug; action: BugAction } | null>(null)

  const sprintNameMap = useMemo(() => {
    const map = new Map<string, string>()
    sprints.forEach((sprint) => {
      if (sprint.sprintId) map.set(sprint.sprintId, sprint.name)
    })
    return map
  }, [sprints])

  const projectMembersQuery = useQuery({
    queryKey: ['projectMembers', activeProjectId],
    queryFn: () => api.getProjectMembers(activeProjectId!),
    enabled: Boolean(activeProjectId) && access.can('read'),
  })
  const membersQuery = bugOnly ? { ...bugScope.optionsQuery, data: bugScope.members } : projectMembersQuery
  const memberNameMap = useMemo(() => {
    const map = new Map<string, string>()
    listItems(membersQuery.data).forEach((member) => map.set(member.userId, member.name))
    return map
  }, [membersQuery.data])

  const filters = useMemo(
    () => ({
      sprintId: activeSprintId ?? '',
      sprintFilter: 'found' as const,
      status,
      confirmed,
      resolution,
      severity,
      assigneeUserId,
      keyword: keyword.trim(),
      page,
      pageSize,
    }),
    [activeSprintId, status, confirmed, resolution, severity, assigneeUserId, keyword, page, pageSize],
  )

  const bugsQuery = useQuery({
    queryKey: ['bugs', activeProjectId, filters],
    queryFn: () =>
      api.getProjectBugs(activeProjectId!, filters),
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })
  const bugs = listItems<Bug>(bugsQuery.data)
  const total = listTotal(bugsQuery.data)

  useEffect(() => {
    setPage(1)
  }, [status, confirmed, resolution, severity, assigneeUserId, keyword, activeSprintId, activeProjectId, pageSize])

  function resetFilters() {
    setStatus('')
    setConfirmed(undefined)
    setResolution('')
    setSeverity('')
    setAssigneeUserId('')
    setKeyword('')
  }

  const columns = bugColumns({ memberNameMap, sprintNameMap, optionalColumns,
    onTransition: (bug, action) => setTransition({ bug, action }) })

  return { optionalColumns, setOptionalColumns, navigate, activeProjectId, activeSprintId, sprints, sprintsQuery, selectSprint, sprintSelectorOptions, status, setStatus, confirmed, setConfirmed, resolution, setResolution, severity, setSeverity, assigneeUserId, setAssigneeUserId, keyword, setKeyword, page, setPage, pageSize, setPageSize, createOpen, setCreateOpen, importOpen, setImportOpen, transition, setTransition, membersQuery, bugsQuery, bugs, total, resetFilters, columns }
}
