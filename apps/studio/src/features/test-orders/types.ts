import type { FunctionCaseContent } from '@/features/test-cases/types'

export type TestOrder = {
  orderId?: string
  projectId?: string
  sprintId?: string
  name: string
  testedVersion?: string
  entriesTotal?: number
  entriesExecuted?: number
  entriesPassed?: number
  entriesFailed?: number
  entriesBlocked?: number
  entriesSkipped?: number
  status?: string
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type CreateTestOrderPayload = {
  name: string
  testedVersion?: string
  /** 可选：从另一张测试单带入结果非「通过」的条目（重测）。 */
  sourceOrderId?: string
}

export type UpdateTestOrderPayload = Partial<CreateTestOrderPayload>

export type TestOrderEntryStatus = 'pending' | 'passed' | 'failed' | 'blocked' | 'skipped'

export type TestOrderEntry = {
  entryId?: string
  orderId?: string
  caseType?: string
  caseId?: string
  caseTitle?: string
  caseModule?: string
  casePriority?: string
  orderNo?: number
  status?: TestOrderEntryStatus | string
  /** 分配执行人；空串表示未分配，仅项目所有者可分配与改派。 */
  assigneeUserId?: string
  actualResults?: string
  failureReason?: string
  blockReason?: string
  zentaoBugId?: string
  executorUserId?: string
  executedAt?: string
  snapshot?: FunctionCaseContent
  createdAt?: string
  created_at?: string
  updatedAt?: string
  updated_at?: string
}

export type AddTestOrderCasesResult = {
  addedCount?: number
  skippedCount?: number
}

export type UpdateTestOrderEntryPayload = {
  /** 整条用例的结论：passed 通过 / failed 失败 / blocked 阻塞 / skipped 跳过。 */
  status?: string
  actualResults?: string
  failureReason?: string
  blockReason?: string
  zentaoBugId?: string
}
