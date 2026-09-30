import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, listItems } from '@/services/api'
import { saveBlob } from '@/shared/utils/download'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { invalidateBug } from '../utils/invalidateBug'
import type { Bug, BugAction } from '../types'

export function useBugDetail() {
  const { bugId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [transitionAction, setTransitionAction] = useState<BugAction | null>(null)
  const [transferOpen, setTransferOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [comment, setComment] = useState('')

  const bugQuery = useQuery({
    queryKey: ['bug', bugId],
    queryFn: () => api.getBug(bugId),
    enabled: Boolean(bugId),
  })
  const bug: Bug | null = bugQuery.data ?? null

  const activitiesQuery = useQuery({
    queryKey: ['bugActivities', bugId],
    queryFn: () => api.getBugActivities(bugId),
    enabled: Boolean(bugId),
  })
  const activities = listItems(activitiesQuery.data)
  const statusChanges = useMemo(
    () => activities.filter((item) => item.kind === 'status_change'),
    [activities],
  )
  const dynamics = useMemo(
    () => activities.filter((item) => item.kind !== 'status_change'),
    [activities],
  )

  const membersQuery = useQuery({
    queryKey: ['projectMembers', bug?.projectId],
    queryFn: () => api.getProjectMembers(bug!.projectId),
    enabled: Boolean(bug?.projectId),
  })
  const memberNameMap = useMemo(() => {
    const map = new Map<string, string>()
    listItems(membersQuery.data).forEach((member) => map.set(member.userId, member.name))
    return map
  }, [membersQuery.data])
  const resolveUserName = (userId: string) => memberNameMap.get(userId) ?? userId

  const sprintNameMap = useQuery({
    queryKey: ['sprints', bug?.projectId],
    queryFn: () => api.getSprints(bug!.projectId),
    enabled: Boolean(bug?.projectId),
  })
  const sprintNames = useMemo(() => {
    const map = new Map<string, string>()
    listItems(sprintNameMap.data).forEach((sprint) => {
      if (sprint.sprintId) map.set(sprint.sprintId, sprint.name)
    })
    return map
  }, [sprintNameMap.data])

  const projectQuery = useQuery({
    queryKey: ['projectAccess', bug?.projectId],
    queryFn: () => api.getProject(bug!.projectId), enabled: Boolean(bug?.projectId),
  })
  const canWrite = projectQuery.data?.permissions?.includes('write') ?? false

  const commentMutation = useMutation({
    mutationFn: () => api.commentBug(bugId, comment.trim()),
    onSuccess: () => {
      message.success('评论已发送')
      setComment('')
      void invalidateBug(queryClient, bugId)
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  async function downloadAttachment(fileId: string, filename: string) {
    try {
      const ticket = await api.downloadAttachment(fileId)
      const response = await fetch(ticket.url, { credentials: 'omit' })
      if (!response.ok) throw new Error('附件下载失败，请重试')
      saveBlob(await response.blob(), filename)
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  return { navigate, bugQuery, bug, activitiesQuery, statusChanges, dynamics, resolveUserName,
    sprintNames, projectQuery, canWrite, comment, setComment, commentMutation, downloadAttachment,
    transitionAction, setTransitionAction, transferOpen, setTransferOpen, editOpen, setEditOpen }
}
