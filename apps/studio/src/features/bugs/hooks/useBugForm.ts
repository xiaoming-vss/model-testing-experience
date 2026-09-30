import { Form } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { storageCapabilities, uploadStoredFile } from '@/shared/api/files'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { invalidateBug } from '../utils/invalidateBug'
import type { BugFormProps, BugFormValues } from '../types'
import type { BugAttachmentItem } from '../components/BugAttachmentUploader'
function descriptionHasText(html: string): boolean {
  const document = new DOMParser().parseFromString(html, 'text/html')
  return Boolean(document.body.textContent?.trim() || document.querySelector('img[data-file-id]'))
}

export function useBugForm({ open, bug, projectId, defaultSprintId, source, onClose, onSaved }: BugFormProps) {
  const [form] = Form.useForm<BugFormValues>()
  const queryClient = useQueryClient()
  const isEdit = Boolean(bug?.bugId)
  const [descriptionHtml, setDescriptionHtml] = useState('')
  const [attachments, setAttachments] = useState<BugAttachmentItem[]>([])

  const [removedAttachmentFileIds, setRemovedAttachmentFileIds] = useState<string[]>([])

  const activeProjectId = bug?.projectId ?? projectId
  const projectsQuery = useQuery({ queryKey: ['projects'], queryFn: () => api.getProjects(), enabled: open })

  const sprintsQuery = useQuery({
    queryKey: ['sprints', activeProjectId],
    queryFn: () => api.getSprints(activeProjectId!),
    enabled: open && Boolean(activeProjectId),
  })
  const sprints = useMemo(() => listItems(sprintsQuery.data), [sprintsQuery.data])

  const membersQuery = useQuery({
    queryKey: ['projectMembers', activeProjectId],
    queryFn: () => api.getProjectMembers(activeProjectId!),
    enabled: open && Boolean(activeProjectId),
  })
  const memberOptions = useMemo(
    () =>
      listItems(membersQuery.data).map((member) => ({
        label: member.name || member.userId,
        value: member.userId,
      })),
    [membersQuery.data],
  )

  const requirementsQuery = useQuery({
    queryKey: ['requirementsPool', activeProjectId, 'forBug', sprints.map((sprint) => sprint.sprintId)],
    queryFn: async () => {
      const groups = await Promise.all(
        sprints.map((sprint) => api.getRequirements(sprint.sprintId ?? '')),
      )
      return groups.flat()
    },
    enabled: open && Boolean(activeProjectId) && sprints.length > 0,
  })
  const requirementOptions = useMemo(
    () =>
      listItems(requirementsQuery.data).map((requirement) => ({
        label: requirement.name,
        value: requirement.requirementId,
      })),
    [requirementsQuery.data],
  )

  const sourceOrdersQuery = useQuery({
    queryKey: ['testOrders', activeProjectId, 'forBug'],
    queryFn: () => api.getProjectTestOrders(activeProjectId!),
    enabled: open && !isEdit && !source && Boolean(activeProjectId),
  })
  const orderOptions = useMemo(
    () =>
      listItems(sourceOrdersQuery.data).map((order) => ({
        label: order.name,
        value: order.orderId,
      })),
    [sourceOrdersQuery.data],
  )

  const selectedOrderId = Form.useWatch('sourceOrderId', form)
  const entriesQuery = useQuery({
    queryKey: ['testOrderEntries', selectedOrderId, 'forBug'],
    queryFn: () => api.getTestOrderEntries(selectedOrderId!),
    enabled: open && !isEdit && !source && Boolean(selectedOrderId),
  })
  const entryOptions = useMemo(
    () =>
      listItems(entriesQuery.data).map((entry) => ({
        label: entry.caseTitle || entry.caseId,
        value: entry.entryId,
      })),
    [entriesQuery.data],
  )

  useEffect(() => {
    if (!open) return
    const initialDescription = bug?.descriptionHtml ?? source?.defaultDescription ?? ''
    setDescriptionHtml(initialDescription)
    setAttachments([])
    setRemovedAttachmentFileIds([])
    form.setFieldsValue({
      title: bug?.title ?? source?.defaultTitle ?? '',
      assigneeUserId: bug?.assigneeUserId || undefined,
      severity: bug?.severity ?? 'normal',
      priority: bug?.priority ?? 'medium',
      foundSprintId: bug?.foundSprintId ?? defaultSprintId ?? undefined,
      plannedFixSprintId: bug ? bug.plannedFixSprintId || undefined : defaultSprintId || undefined,
      requirementId: bug?.requirementId || source?.requirementId || undefined,
      sourceOrderId: undefined,
      sourceEntryId: undefined,
    })
    form.setFields([{ name: 'plannedFixSprintId', touched: false }])
  }, [open, bug, source, projectId, defaultSprintId, form])

  async function uploadAttachmentFiles(): Promise<string[]> {
    if (attachments.length === 0) return []
    const capabilities = await storageCapabilities()
    if (!capabilities.enabled) {
      throw new Error('文件存储未启用，无法上传附件')
    }
    const fileIds: string[] = []
    for (const item of attachments) {
      fileIds.push(await uploadStoredFile(activeProjectId!, item.file, 'attachment'))
    }
    return fileIds
  }

  const saveMutation = useMutation({
    mutationFn: async (values: BugFormValues) => {
      if (!descriptionHasText(descriptionHtml)) {
        throw new Error('请描述问题现象与复现步骤')
      }
      const attachmentFileIds = await uploadAttachmentFiles()
      if (isEdit && bug) {
        return api.updateBug(bug.bugId, {
          removedAttachmentFileIds: removedAttachmentFileIds.length ? removedAttachmentFileIds : undefined,
          title: values.title.trim(),
          severity: values.severity,
          priority: values.priority,
          plannedFixSprintId: values.plannedFixSprintId ?? '',
          requirementId: values.requirementId ?? '',
          descriptionHtml,
          attachmentFileIds: attachmentFileIds.length > 0 ? attachmentFileIds : undefined,
        })
      }
      return api.createBug(activeProjectId!, {
        title: values.title.trim(),
        assigneeUserId: values.assigneeUserId!,
        severity: values.severity,
        priority: values.priority,
        foundSprintId: values.foundSprintId!,
        plannedFixSprintId: values.plannedFixSprintId ?? '',
        requirementId: values.requirementId ?? '',
        descriptionHtml,
        attachmentFileIds,
        sourceOrderId: source?.orderId ?? values.sourceOrderId ?? '',
        sourceEntryId: source?.entryId ?? values.sourceEntryId ?? '',
        sourceCaseId: source?.caseId ?? '',
      })
    },
    onSuccess: (saved) => {
      message.success(isEdit ? 'Bug 已更新' : 'Bug 已提交')
      void invalidateBug(queryClient, saved.bugId)
      if (onSaved) onSaved(saved)
      else onClose()
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })
  return { removedAttachmentFileIds, setRemovedAttachmentFileIds, form, isEdit, descriptionHtml, setDescriptionHtml, attachments, setAttachments,
    activeProjectId, projectsQuery, sprintsQuery, sprints, memberOptions, membersQuery,
    requirementOptions, requirementsQuery, orderOptions, sourceOrdersQuery, selectedOrderId,
    entryOptions, entriesQuery, saveMutation }
}
