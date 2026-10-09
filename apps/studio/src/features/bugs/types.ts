/** Bug 领域类型：字段与后端 BugResponse / BugActivityResponse 一一对应（camelCase）。 */

export type BugStatus = 'active' | 'resolved' | 'closed'
export type BugResolution = 'fixed' | 'bydesign' | 'duplicate' | 'external' | 'notrepro' | 'postponed' | 'willnotfix' | 'tostory'
export type BugSeverity = 'fatal' | 'serious' | 'normal' | 'minor'
export type BugPriority = 'high' | 'medium' | 'low'
export type BugAction = 'confirm' | 'resolve' | 'close' | 'activate'
export type BugRejectReason = 'by_design' | 'not_reproducible' | 'deferred'
export type BugActivityKind = 'status_change' | 'transfer' | 'comment' | 'edit' | 'attachment'

export type BugAttachment = {
  fileId: string
  filename: string
  size: number
  contentType: string
}

export type Bug = {
  id: number
  bugId: string
  bugNo: number
  projectId: string
  title: string
  descriptionHtml: string
  status: BugStatus | string
  confirmed?: boolean
  resolution?: BugResolution | string
  resolvedBuild?: string
  duplicateBug?: number
  activatedCount?: number
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
    fromConfirmed?: boolean
    toConfirmed?: boolean
    fromResolution?: string
    toResolution?: string
    resolvedBuild?: string
    duplicateBug?: number
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
  confirmed?: boolean
  resolution?: string
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
  resolution?: BugResolution
  resolvedBuild?: string
  duplicateBug?: number
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
export type BugOptions = {
  members: Array<{ userId: string; name: string }>
  sprints: Array<{ sprintId: string; name: string }>
}

export type BugZentaoJob = {
  queueReason?: 'waiting' | 'paused' | 'worker_offline' | 'worker_incompatible' | 'target_busy' | 'runtime_changed' | null
  queueWaitSeconds?: number | null
  jobId: string
  jobStatus: 'queued' | 'claimed' | 'running' | 'succeeded' | 'partial' | 'failed' | 'unknown' | 'canceled' | 'quarantined'
  taskType: 'zentao_bug_sync' | 'zentao_bug_fields_update'
  protocolVersion: number
  result: { steps: Record<string, string> }
}

export type BugZentaoPush = {
  status: 'not_pushed' | 'preparing' | 'creating' | 'succeeded' | 'failed' | 'unknown'
  source?: 'push' | 'import' | string
  ready: boolean
  reason: string
  remoteBugId: number | null
  target: { project?: number; execution?: number; story?: number; projectName?: string; executionName?: string; storyName?: string }
  errorMessage: string
  attachmentStatus?: 'none' | 'pending' | 'syncing' | 'succeeded' | 'failed' | 'unknown'
  descriptionStatus?: 'none' | 'pending' | 'syncing' | 'succeeded' | 'failed' | 'unknown'
  actorUserId: string
  updatedAt: string | null
  warnings: string[]
  openedBuild?: string[]
  assignedTo?: string
  fieldUpdateStatus?: 'none' | 'preparing' | 'updating' | 'succeeded' | 'failed' | 'unknown'
  fieldUpdateError?: string
  executionMode?: 'worker'
  activeJob?: BugZentaoJob | null
  latestJob?: BugZentaoJob | null
}

export type BugZentaoPushOptions = {
  target: BugZentaoPush['target'] & { mcpServiceId?: string; mcpName?: string; instanceUrl?: string }
  builds: Array<{ id: string; name: string }>
  users: Array<{ account: string; name: string }>
  current?: { remoteBugId: number; openedBuild: string[]; assignedTo: string } | null
}

export type BugZentaoPushPayload = {
  openedBuild: string[]
  assignedTo: string
  expectedTarget: BugZentaoPushOptions['target']
}

export type BugZentaoUpdatePayload = BugZentaoPushPayload & {
  expectedRemoteBugId: number
  expectedOpenedBuild: string[]
  expectedAssignedTo: string
}

/** 禅道新建 Bug 导入（后端 ZentaoBugImport* 契约）。 */

export type ZentaoBugCandidate = {
  remoteBugId: number
  title: string
  status: string
  severity: string
  priority: string
  assignedTo: string
  openedBy: string
  openedDate: string
  execution: number
  story: number
  linked: boolean
}

export type ZentaoBugPendingItem = { field: string; reason: string }

export type ZentaoBugImportPreview = {
  remoteBugId: number
  state: 'ready' | 'pending' | 'pending_files' | 'invalid' | string
  title: string
  snapshot: Record<string, unknown>
  converted: {
    severity?: string | null
    priority?: string | null
    status?: string
    confirmed?: boolean
    resolution?: string
    resolvedBuild?: string
    duplicateBugId?: number | null
    foundSprintId?: string
    foundSprintName?: string
    requirementId?: string
    requirementName?: string
  }
  description: { hasImages: boolean; hasContent: boolean }
  pending: ZentaoBugPendingItem[]
  errorMessage: string
}

export type ZentaoBugImportItemPayload = {
  remoteBugId: number
  assigneeUserId: string
  foundSprintId: string
  requirementId?: string
  severity?: string
  priority?: string
}

export type ZentaoBugImportResult = {
  remoteBugId: number
  status: 'success' | 'already_linked' | 'conflict' | 'failed' | string
  bugId: string
  bugNo: number
  title: string
  errorMessage: string
  pending: ZentaoBugPendingItem[]
}

/** 已关联 Bug 从禅道拉取更新（后端 ZentaoRemote* / ZentaoPull* 契约）。 */

export type ZentaoRemoteGroupState =
  | 'synced'
  | 'remote_changed'
  | 'local_changed'
  | 'conflict'
  | 'confirm_baseline'
  | 'pending_files'
  | 'pending_map'
  | 'manual'
  | string

export type ZentaoRemoteGroup = {
  group: 'profile' | 'description' | 'status' | 'assignee' | string
  state: ZentaoRemoteGroupState
  local: Record<string, unknown>
  remote: Record<string, unknown>
  baseline: { local: Record<string, unknown>; remote: Record<string, unknown>; appliedAt?: string } | null
  reason: string
}

export type ZentaoRemotePreview = {
  remoteBugId: number
  remoteDigest: string
  linkedSource: 'push' | 'import' | string
  groups: ZentaoRemoteGroup[]
}

export type ZentaoPullGroupPayload = {
  group: string
  action: 'apply_remote' | 'keep_local'
  assigneeUserId?: string
  severity?: string
  priority?: string
}

export type ZentaoPullResult = { applied: string[]; kept: string[]; notes: string[] }
