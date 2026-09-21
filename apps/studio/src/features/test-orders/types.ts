import type { ApiCaseGenerateTaskRunStatus } from '@/features/ai-testing/types'
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

/* 测试单图谱（update-test-case-graph skill）。

   图谱输入是全平台唯一一处 snake_case 契约：它由控制面组装、原样交给 worker 与
   skill，字段名不对会导致 skill 的输入校验失败，因此不要做 camelCase 转换。 */

export type TestOrderGraphInputRequirement = {
  requirement_id?: string
  requirement_title?: string
  requirement_content?: string
}

export type TestOrderGraphInputCase = {
  case_id?: string
  case_module?: string
  case_title?: string
  case_type?: string
  priority?: string
  precondition?: string[]
  test_steps?: string[]
  expected_results?: string[]
}

/** `requirement_id` 为 null 表示这组用例没有绑定本迭代的需求。 */
export type TestOrderGraphInputLink = {
  requirement_id?: string | null
  case_ids?: string[]
}

export type TestOrderGraphInput = {
  requirements?: TestOrderGraphInputRequirement[]
  cases?: TestOrderGraphInputCase[]
  case_requirement_links?: TestOrderGraphInputLink[]
}

export type TestOrderGraphRun = {
  runId?: string
  taskId?: string
  status?: ApiCaseGenerateTaskRunStatus
  stageStatus?: string
  errorMessage?: string
  /** 图谱 JSON 落在这里（不是 configJson）。 */
  resultYaml?: string
  /** 回显的派发配置：节点名称要用里面的 `graphInput.cases`（图谱本身只存 case_id）。 */
  configJson?: string | Record<string, unknown>
  createdAt?: string
  created_at?: string
}

export type TestOrderGraph = {
  orderId?: string
  run?: TestOrderGraphRun | null
}

export type DispatchTestOrderGraphPayload = {
  graphInput: TestOrderGraphInput
  connectionId: string
}
