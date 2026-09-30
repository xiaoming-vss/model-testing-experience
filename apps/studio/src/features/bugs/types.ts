/** Bug 领域类型：字段与后端 BugResponse / BugActivityResponse 一一对应（camelCase）。 */

export type BugStatus = 'pending' | 'processing' | 'pending_regression' | 'closed' | 'rejected' | 'reopened'
export type BugSeverity = 'fatal' | 'serious' | 'normal' | 'minor'
export type BugPriority = 'high' | 'medium' | 'low'
export type BugAction = 'confirm' | 'reject' | 'submit_fix' | 'regression_pass' | 'regression_fail' | 'reopen'
export type BugRejectReason = 'by_design' | 'not_reproducible' | 'deferred'
export type BugActivityKind = 'status_change' | 'transfer' | 'comment' | 'edit' | 'attachment'

export type BugAttachment = {
  fileId: string
  filename: string
  size: number
  contentType: string
}

export type Bug = {
  bugId: string
  bugNo: number
  projectId: string
  title: string
  descriptionHtml: string
  status: BugStatus | string
  severity: BugSeverity | string
  priority: BugPriority | string
  reporterUserId: string
  assigneeUserId: string
  foundSprintId: string
  plannedFixSprintId: string
  requirementId: string
  requirementName: string
  sourceOrderId: string
  sourceEntryId: string
  sourceCaseId: string
  sourceOrderName: string
  sourceCaseTitle: string
  attachments?: BugAttachment[]
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type BugActivity = {
  activityId: string
  bugId: string
  kind: BugActivityKind | string
  actorUserId: string
  action: string
  fromStatus: string
  toStatus: string
  content: string
  detail: {
    rejectReason?: string
    rejectReasonLabel?: string
    fromUserId?: string
    toUserId?: string
    changes?: Array<{ field: string; from: string; to: string }>
    removedFiles?: Array<{ fileId: string; filename: string }>
    addedFiles?: Array<{ fileId: string; filename: string }>
  }
  createdAt?: string
  created_at?: string
}

export type BugListFilters = {
  status?: string
  severity?: string
  assigneeUserId?: string
  sprintId?: string
  sprintFilter?: 'found' | 'planned_fix'
  sourceEntryId?: string
  keyword?: string
  page?: number
  pageSize?: number
}

export type CreateBugPayload = {
  title: string
  assigneeUserId: string
  severity: BugSeverity | string
  priority: BugPriority | string
  foundSprintId: string
  plannedFixSprintId?: string
  requirementId?: string
  descriptionHtml?: string
  attachmentFileIds?: string[]
  sourceOrderId?: string
  sourceEntryId?: string
  sourceCaseId?: string
}

export type UpdateBugPayload = {
  removedAttachmentFileIds?: string[]
  title?: string
  severity?: BugSeverity | string
  priority?: BugPriority | string
  plannedFixSprintId?: string
  requirementId?: string
  descriptionHtml?: string
  attachmentFileIds?: string[]
}

export type BugTransitionPayload = {
  action: BugAction
  content?: string
  rejectReason?: string
}

export type BugFormValues = {
  title: string
  assigneeUserId?: string
  severity: string
  priority: string
  foundSprintId?: string
  plannedFixSprintId?: string
  requirementId?: string
  sourceOrderId?: string
  sourceEntryId?: string
}

export type BugFormSource = {
  orderId: string
  entryId: string
  caseId?: string
  requirementId?: string
  defaultTitle?: string
  defaultDescription?: string
}

export type BugFormProps = {
  open: boolean
  bug?: Bug | null
  projectId?: string
  defaultSprintId?: string | null
  /** 从用例执行记录提交时的预填来源。 */
  source?: BugFormSource | null
  onClose: () => void
  onSaved?: (bug: Bug) => void
}

