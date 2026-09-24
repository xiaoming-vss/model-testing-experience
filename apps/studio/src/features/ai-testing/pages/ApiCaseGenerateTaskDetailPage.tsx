import { saveBlob } from '@/shared/utils/download'
import { useDeleteTaskRun, useStartTaskRun } from '@/features/ai-testing/hooks/useTaskRunActions'
import { formatStructuredContent, toRecord, toRecordArray } from '@/shared/utils/value'
import { ActionButton } from '@/shared/components/ActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ArrowLeftOutlined, CodeOutlined, CopyOutlined, DownOutlined, FileTextOutlined, HistoryOutlined, RightOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Form, Input, Modal, Popconfirm, Select, Spin, Tabs, Tag, Tooltip } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { parse } from 'yaml'
import { ApiCaseGenerateTaskDrawer, type ApiCaseGenerateTaskFormValues } from '../components/ApiCaseGenerateTaskDrawer'
import { ApiImportConflictModal } from '../components/ApiImportConflictModal'
import { RunHistoryTable, RunMigrationWarningIcon, RunRowActions, type RunMenuAction } from '../components/RunHistoryTable'
import { confirmDeleteRun, isRunDeletable } from '../utils/runDeletion'
import { TaskDetailInstructionEditor, TaskDetailNavItem, TaskDetailNavPanel, TaskDetailRunMetrics, TaskDetailToolbar } from '../components/TaskDetailShell'
import { RunArtifacts, RunPipelineStatus } from '../components/RunPipelineStatus'
import { LlmConnectionSelectModal } from '../components/LlmConnectionSelectModal'
import type {
  ApiCaseGenerateTaskRunImportConflict,
  ImportApiCaseGenerateTaskRunPayload,
  ReviewApiCaseGenerateTaskRunPayload,
} from '../types'
import { isRunnableApiCaseGenerateTaskRun, normalizeGenerateTaskReviewStatus, renderApiCaseGenerateTaskRunStatusTag, summarizeRunStatuses } from '../utils/taskStatus'
import '@/shared/styles/surface-tokens.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-review.css'
import '@/features/ai-testing/styles/api-config-result.css'
import '@/features/ai-testing/styles/run-result.css'
import '@/features/ai-testing/styles/task-detail-v2.css'
import { useCurrentUser } from '@/features/auth/hooks/useCurrentUser'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { formatTime, getErrorMessage, normalizeRequirementId, normalizeSprintId, normalizeUserName, pickUpdatedAt } from '@/utils/format'

const runResultSectionDefinitions = [
  { key: 'configJson', label: '中间配置' },
  { key: 'resultYaml', label: '结果 YAML' },
  { key: 'errorMessage', label: '错误信息' },
] as const

type RunResultSectionKey = (typeof runResultSectionDefinitions)[number]['key']

type RunResultModalState = {
  key: RunResultSectionKey
  label: string
} | null

type ImportConflictState = {
  runId: string
  collectionId: string
  conflicts: ApiCaseGenerateTaskRunImportConflict[]
} | null

type ApiConfigRule = {
  name: string
  detail: string
}

type ApiConfigCaseView = {
  key: string
  name: string
  orderNo?: number
  method: string
  path: string
  headers?: unknown
  query?: unknown
  body?: unknown
  response?: unknown
  extractRules: ApiConfigRule[]
  assertRules: ApiConfigRule[]
  usedVariables: string[]
  extractedVariables: string[]
}

type ApiConfigDiagramData = {
  cases: ApiConfigCaseView[]
  totalExtractRules: number
  totalAssertRules: number
  authHeaderCount: number
}

function toDisplayText(value: unknown) {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function pickText(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const text = toDisplayText(record[key])
    if (text) return text
  }
  return ''
}

function pickValue(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = record[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return undefined
}

function parseJsonLikeValue(value: unknown) {
  if (typeof value !== 'string') return value
  const trimmed = value.trim()
  if (!trimmed) return value
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return value
  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function stringifyCompact(value: unknown) {
  if (value === undefined || value === null || value === '') return ''
  const parsed = parseJsonLikeValue(value)
  if (typeof parsed === 'string') return parsed
  try {
    return JSON.stringify(parsed, null, 2)
  } catch {
    return String(parsed)
  }
}

function collectTemplateVariables(value: unknown) {
  const source = stringifyCompact(value)
  if (!source) return []
  const variables = new Set<string>()
  const pattern = /\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}|\{\s*([A-Za-z_][\w.-]*)\s*\}/g
  let match: RegExpExecArray | null

  while ((match = pattern.exec(source)) !== null) {
    const variable = match[1] || match[2]
    if (variable) variables.add(variable)
  }

  return [...variables]
}

function formatRule(rule: Record<string, unknown>, fallback: string): ApiConfigRule {
  const name = pickText(rule, ['name', 'ruleName', 'varKey', 'targetExpr', 'sourceExpr']) || fallback
  const detailCandidates = [
    pickText(rule, ['sourceExpr', 'targetExpr', 'assertSource']),
    pickText(rule, ['comparator', 'operator']),
    pickText(rule, ['expectedValue', 'value', 'source']),
  ].filter(Boolean)

  return {
    name,
    detail: detailCandidates.join(' / ') || stringifyCompact(rule),
  }
}

function normalizeApiConfigCases(content?: string): ApiConfigDiagramData | null {
  if (!content?.trim()) return null

  try {
    const parsed = parse(content)
    const entries: Array<{ key: string; value: unknown; index: number }> = []

    if (Array.isArray(parsed)) {
      parsed.forEach((value, index) => entries.push({ key: `case-${index + 1}`, value, index }))
    } else if (parsed && typeof parsed === 'object') {
      const record = parsed as Record<string, unknown>
      const cases = Array.isArray(record.cases) ? record.cases : Array.isArray(record.apiCases) ? record.apiCases : null
      if (cases) {
        cases.forEach((value, index) => entries.push({ key: `case-${index + 1}`, value, index }))
      } else {
        Object.entries(record).forEach(([key, value], index) => entries.push({ key, value, index }))
      }
    }

    const cases = entries
      .map((entry): ApiConfigCaseView | null => {
        const record = toRecord(entry.value)
        if (!record) return null

        const method = pickText(record, ['method', 'httpMethod']).toUpperCase() || 'API'
        const path = pickText(record, ['path', 'urlTemplate', 'url', 'endpoint']) || '-'
        const headers = parseJsonLikeValue(pickValue(record, ['headers', 'headersJson', 'requestHeaders']))
        const query = parseJsonLikeValue(pickValue(record, ['query', 'queryJson', 'params', 'queryParams']))
        const body = parseJsonLikeValue(pickValue(record, ['json', 'bodyJson', 'body', 'bodyText', 'requestBody']))
        const response = parseJsonLikeValue(pickValue(record, ['response', 'responseJson', 'responseBody']))
        const extractRules = toRecordArray(pickValue(record, ['extractRules', 'extract_rules', 'extractors', 'extractions']))
          .map((rule, index) => formatRule(rule, `提取规则 ${index + 1}`))
        const assertRules = toRecordArray(pickValue(record, ['assertRules', 'assert_rules', 'assertions', 'checks']))
          .map((rule, index) => formatRule(rule, `断言规则 ${index + 1}`))
        const extractedVariables = extractRules
          .map((rule) => rule.name)
          .filter(Boolean)
        const usedVariables = [
          ...collectTemplateVariables(path),
          ...collectTemplateVariables(headers),
          ...collectTemplateVariables(query),
          ...collectTemplateVariables(body),
        ]
        const orderText = pickText(record, ['orderNo', 'order', 'sort'])
        const orderNo = Number(orderText)

        return {
          key: `${entry.key}-${entry.index}`,
          name: pickText(record, ['name', 'caseName', 'title']) || entry.key,
          ...(Number.isFinite(orderNo) ? { orderNo } : {}),
          method,
          path,
          ...(headers !== undefined && headers !== null && headers !== '' ? { headers } : {}),
          ...(query !== undefined && query !== null && query !== '' ? { query } : {}),
          ...(body !== undefined && body !== null && body !== '' ? { body } : {}),
          ...(response !== undefined && response !== null && response !== '' ? { response } : {}),
          extractRules,
          assertRules,
          usedVariables: [...new Set(usedVariables)],
          extractedVariables: [...new Set(extractedVariables)],
        }
      })
      .filter((item): item is ApiConfigCaseView => Boolean(item))
      .sort((left, right) => (left.orderNo ?? Number.MAX_SAFE_INTEGER) - (right.orderNo ?? Number.MAX_SAFE_INTEGER))

    if (cases.length === 0) return null

    return {
      cases,
      totalExtractRules: cases.reduce((sum, item) => sum + item.extractRules.length, 0),
      totalAssertRules: cases.reduce((sum, item) => sum + item.assertRules.length, 0),
      authHeaderCount: cases.filter((item) => {
        const headers = toRecord(parseJsonLikeValue(item.headers))
        return Boolean(headers && Object.keys(headers).some((key) => key.toLowerCase().includes('authorization')))
      }).length,
    }
  } catch {
    return null
  }
}

function getMethodTagColor(method: string) {
  const normalizedMethod = method.toUpperCase()
  if (normalizedMethod === 'GET') return 'blue'
  if (normalizedMethod === 'POST') return 'green'
  if (normalizedMethod === 'PUT' || normalizedMethod === 'PATCH') return 'orange'
  if (normalizedMethod === 'DELETE') return 'red'
  return 'default'
}

function ApiConfigPreviewField({ label, value }: { label: string; value: unknown }) {
  const text = stringifyCompact(value)
  if (!text) return null

  return (
    <div className="api-config-visual-field">
      <span>{label}</span>
      <pre>{text}</pre>
    </div>
  )
}

function ApiConfigRuleList({ title, rules, emptyText }: { title: string; rules: ApiConfigRule[]; emptyText: string }) {
  return (
    <div className="api-config-visual-rule-group">
      <div className="api-config-visual-rule-title">
        <span>{title}</span>
        <Tag color={rules.length > 0 ? 'cyan' : 'default'}>{rules.length}</Tag>
      </div>
      {rules.length > 0 ? (
        <div className="api-config-visual-rule-list">
          {rules.map((rule, index) => (
            <div key={`${rule.name}-${index}`} className="api-config-visual-rule">
              <strong>{rule.name}</strong>
              {rule.detail ? <span>{rule.detail}</span> : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="api-config-visual-empty">{emptyText}</div>
      )}
    </div>
  )
}

function ApiConfigDiagramView({ content, defaultCollapsed = false }: { content: string; defaultCollapsed?: boolean }) {
  const diagramData = useMemo(() => normalizeApiConfigCases(content), [content])
  const [collapsedCaseKeys, setCollapsedCaseKeys] = useState<Set<string>>(
    () => new Set(defaultCollapsed ? diagramData?.cases.map((apiCase) => apiCase.key) : []),
  )

  useEffect(() => {
    setCollapsedCaseKeys(new Set(defaultCollapsed ? diagramData?.cases.map((apiCase) => apiCase.key) : []))
  }, [defaultCollapsed, diagramData])

  if (!diagramData) {
    return <div className="ai-task-run-result-popover-empty">当前中间配置无法解析为 API 链路</div>
  }

  return (
    <div className="api-config-visual-view">
      <div className="api-config-visual-stats">
        <Tag color="blue">接口 {diagramData.cases.length}</Tag>
        <Tag color="cyan">提取 {diagramData.totalExtractRules}</Tag>
        <Tag color="purple">断言 {diagramData.totalAssertRules}</Tag>
        <Tag color="green">认证头 {diagramData.authHeaderCount}</Tag>
      </div>
      <div className="api-config-visual-chain">
        {diagramData.cases.map((apiCase, index) => {
          const collapsed = collapsedCaseKeys.has(apiCase.key)
          const toggleCase = () => {
            setCollapsedCaseKeys((current) => {
              const next = new Set(current)
              if (next.has(apiCase.key)) next.delete(apiCase.key)
              else next.add(apiCase.key)
              return next
            })
          }

          return (
          <div key={apiCase.key} className="api-config-visual-step">
            <article className={`api-config-visual-card${collapsed ? ' collapsed' : ''}`}>
              <button
                type="button"
                className="api-config-visual-card-head"
                aria-expanded={!collapsed}
                aria-label={`${collapsed ? '展开' : '折叠'} ${apiCase.method} ${apiCase.name}`}
                onClick={toggleCase}
              >
                <div className="api-config-visual-method-line">
                  <span className="api-config-visual-collapse-icon" aria-hidden>
                    {collapsed ? <RightOutlined /> : <DownOutlined />}
                  </span>
                  <Tag color={getMethodTagColor(apiCase.method)}>{apiCase.method}</Tag>
                  <strong>{apiCase.name}</strong>
                </div>
                {apiCase.orderNo ? <span className="api-config-visual-order">#{apiCase.orderNo}</span> : null}
              </button>
              {!collapsed ? (
                <div className="api-config-visual-card-body">
                  <div className="api-config-visual-path">{apiCase.path}</div>
                  <div className="api-config-visual-variable-row">
                    {apiCase.usedVariables.map((variable) => (
                      <Tag key={`used-${variable}`} color="gold">使用 {variable}</Tag>
                    ))}
                    {apiCase.extractedVariables.map((variable) => (
                      <Tag key={`extract-${variable}`} color="success">提取 {variable}</Tag>
                    ))}
                    {apiCase.usedVariables.length === 0 && apiCase.extractedVariables.length === 0 ? (
                      <span className="api-config-visual-muted">无变量依赖</span>
                    ) : null}
                  </div>
                  <div className="api-config-visual-grid">
                    <ApiConfigPreviewField label="Headers" value={apiCase.headers} />
                    <ApiConfigPreviewField label="Query" value={apiCase.query} />
                    <ApiConfigPreviewField label="Body" value={apiCase.body} />
                    <ApiConfigPreviewField label="Response" value={apiCase.response} />
                  </div>
                  <div className="api-config-visual-rules">
                    <ApiConfigRuleList title="提取规则" rules={apiCase.extractRules} emptyText="暂无提取规则" />
                    <ApiConfigRuleList title="断言规则" rules={apiCase.assertRules} emptyText="暂无断言规则" />
                  </div>
                </div>
              ) : null}
            </article>
            {index < diagramData.cases.length - 1 ? <div className="api-config-visual-connector" /> : null}
          </div>
          )
        })}
      </div>
    </div>
  )
}

function ApiConfigResultView({ content }: { content: string }) {
  const canRenderDiagram = Boolean(normalizeApiConfigCases(content))
  const [activeView, setActiveView] = useState<'diagram' | 'json'>('diagram')

  return (
    <div className="api-config-result-tabs">
      <div className="api-config-result-tablist" role="tablist" aria-label="中间配置查看方式">
        <button
          id="api-config-preview-tab"
          type="button"
          role="tab"
          aria-selected={activeView === 'diagram'}
          aria-controls="api-config-result-panel"
          className={activeView === 'diagram' ? 'is-active' : undefined}
          onClick={() => setActiveView('diagram')}
        >
          预览
        </button>
        <button
          id="api-config-json-tab"
          type="button"
          role="tab"
          aria-selected={activeView === 'json'}
          aria-controls="api-config-result-panel"
          className={activeView === 'json' ? 'is-active' : undefined}
          onClick={() => setActiveView('json')}
        >
          json
        </button>
      </div>
      <div
        id="api-config-result-panel"
        className="api-config-result-panel"
        role="tabpanel"
        aria-labelledby={activeView === 'diagram' ? 'api-config-preview-tab' : 'api-config-json-tab'}
      >
        {activeView === 'diagram' ? (
          canRenderDiagram ? (
            <ApiConfigDiagramView content={content} />
          ) : (
            <div className="ai-task-run-result-popover-empty">当前中间配置无法解析为 API 链路</div>
          )
        ) : (
          <TextCodeEditor
            ariaLabel="中间配置 JSON"
            value={content}
            readOnly
            language="json"
            height="100%"
            minHeight={0}
          />
        )}
      </div>
    </div>
  )
}

function ApiCandidateResultView({ content }: { content: string }) {
  if (!normalizeApiConfigCases(content)) {
    return <div className="ai-task-run-result-popover-empty">当前候选结果无法解析为 API 用例</div>
  }

  return <ApiConfigDiagramView content={content} defaultCollapsed />
}

export function ApiCaseGenerateTaskDetailPage() {
  const { taskId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerSprintId, setDrawerSprintId] = useState<string | undefined>(undefined)
  const [llmSelectOpen, setLlmSelectOpen] = useState(false)
  const [expandedSection, setExpandedSection] = useState<'instruction' | 'sourceContent' | 'runHistory' | null>('runHistory')
  const [instructionDraft, setInstructionDraft] = useState('')
  const [instructionDirty, setInstructionDirty] = useState(false)
  const [selectedRunRecordId, setSelectedRunRecordId] = useState<string | null>(null)
  const [runResultModal, setRunResultModal] = useState<RunResultModalState>(null)
  const [reviewModalRunId, setReviewModalRunId] = useState<string | null>(null)
  const [discardCandidateConfirmOpen, setDiscardCandidateConfirmOpen] = useState(false)
  const [importModalRunId, setImportModalRunId] = useState<string | null>(null)
  const [importConflict, setImportConflict] = useState<ImportConflictState>(null)
  const [reviewSubmitAction, setReviewSubmitAction] = useState<'approve' | 'reject' | null>(null)
  const [candidateModalView, setCandidateModalView] = useState<'preview' | 'edit'>('preview')
  const [candidateYaml, setCandidateYaml] = useState('')
  const [form] = Form.useForm<ApiCaseGenerateTaskFormValues>()
  const [reviewForm] = Form.useForm<{ reviewComment?: string }>()
  const [importForm] = Form.useForm<{ collectionId: string }>()
  useCurrentUser()
  const currentUser = useAuthStore((state) => state.user)

  const taskQuery = useQuery({
    queryKey: ['apiCaseGenerateTask', taskId],
    queryFn: () => api.getApiCaseGenerateTask(taskId),
    enabled: Boolean(taskId),
  })

  const task = taskQuery.data
  const { can } = useProjectAccess(task?.projectId ?? '')
  const runsQuery = useQuery({
    queryKey: ['apiCaseGenerateTaskRuns', taskId],
    queryFn: () => api.getApiCaseGenerateTaskRuns(taskId),
    enabled: Boolean(taskId),
    refetchInterval: expandedSection === 'runHistory' ? 5000 : false,
  })
  const sprintsQuery = useQuery({
    queryKey: ['sprints', 'aiTestingDetail', task?.projectId],
    queryFn: async () => {
      const projectId = task?.projectId
      if (!projectId) return []
      return api.getSprints(projectId)
    },
    enabled: Boolean(task?.projectId),
  })
  const sprintOptions = useMemo(
    () => listItems(sprintsQuery.data).map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) })),
    [sprintsQuery.data],
  )
  const requirementsQuery = useQuery({
    queryKey: ['requirements', 'aiTestingDetail', drawerSprintId],
    queryFn: () => api.getRequirements(drawerSprintId!),
    enabled: Boolean(drawerSprintId),
  })
  const requirementOptions = useMemo(
    () =>
      listItems(requirementsQuery.data).map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    [requirementsQuery.data],
  )
  const apiCollectionsQuery = useQuery({
    queryKey: ['apiCollections', 'aiTestingReview', task?.requirementId],
    queryFn: async () => {
      const requirementId = task?.requirementId
      if (!requirementId) return []
      return api.getApiCollections(requirementId)
    },
    enabled: Boolean(task?.requirementId),
  })
  const sprintNameMap = useMemo(
    () => new Map(listItems(sprintsQuery.data).map((sprint) => [normalizeSprintId(sprint), sprint.name])),
    [sprintsQuery.data],
  )
  const requirementNameMap = useMemo(
    () => new Map(listItems(requirementsQuery.data).map((requirement) => [normalizeRequirementId(requirement), requirement.name])),
    [requirementsQuery.data],
  )

  const runRecords = useMemo(
    () =>
      [...listItems(runsQuery.data)].sort((left, right) => {
        const leftTime = new Date(left.createdAt || left.startedAt || left.updatedAt || '').getTime()
        const rightTime = new Date(right.createdAt || right.startedAt || right.updatedAt || '').getTime()
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
      }),
    [runsQuery.data],
  )
  const latestRunRecord = runRecords[0]

  const selectedRunId = selectedRunRecordId ?? runRecords[0]?.runId ?? ''
  const selectedRunQuery = useQuery({
    queryKey: ['apiCaseGenerateTaskRun', selectedRunId],
    queryFn: () => api.getApiCaseGenerateTaskRun(selectedRunId),
    enabled: Boolean(selectedRunId),
    refetchInterval: expandedSection === 'runHistory' && selectedRunId ? 5000 : false,
  })
  const selectedRun = selectedRunQuery.data
  const selectedRunResultSections = useMemo(
    () =>
      selectedRun
        ? runResultSectionDefinitions
            .map((section) => {
              const rawValue = selectedRun[section.key]
              return { ...section, value: formatStructuredContent(rawValue) }
            })
            .filter((item) => item.value)
      : [],
    [selectedRun],
  )
  const apiCollectionOptions = useMemo(
    () =>
      listItems(apiCollectionsQuery.data).map((collection) => ({
        label: collection.name,
        value: collection.collectionId ?? collection.collection_id ?? '',
      })),
    [apiCollectionsQuery.data],
  )
  const apiCollectionNameMap = useMemo(
    () =>
      new Map(
        listItems(apiCollectionsQuery.data).map((collection) => [
          collection.collectionId ?? collection.collection_id ?? '',
          collection.name,
        ]),
      ),
    [apiCollectionsQuery.data],
  )

  useEffect(() => {
    if (!task) return
    setDrawerSprintId(task.sprintId)
    form.setFieldsValue({
      name: task.name,
      sprintId: task.sprintId,
      requirementId: task.requirementId,
      sourceType: task.sourceType,
      sourceContent: task.sourceContent,
      instruction: task.instruction,
    })
  }, [form, task])

  useEffect(() => {
    setExpandedSection('runHistory')
  }, [taskId])

  // 指令草稿跟着任务数据走；保存成功后任务数据更新，草稿与脏标记一起复位。
  useEffect(() => {
    setInstructionDraft(task?.instruction ?? '')
    setInstructionDirty(false)
  }, [task?.instruction, task?.taskId])

  function handleSaveInstruction() {
    if (!task) return
    updateTaskMutation.mutate({
      name: task.name,
      sprintId: task.sprintId ?? '',
      requirementId: task.requirementId ?? '',
      sourceType: task.sourceType,
      sourceContent: task.sourceContent,
      instruction: instructionDraft,
    })
  }

  const updateTaskMutation = useMutation({
    mutationFn: (values: ApiCaseGenerateTaskFormValues) => api.updateApiCaseGenerateTask(taskId, values),
    onSuccess: (updatedTask) => {
      message.success('任务已更新')
      setDrawerOpen(false)
      queryClient.setQueryData(['apiCaseGenerateTask', taskId], updatedTask)
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTasks', updatedTask.projectId] })
    },
  })

  const runTaskMutation = useStartTaskRun({
    kind: 'api',
    taskId,
    projectId: task?.projectId,
    startRun: (connectionId: string) => api.runApiCaseGenerateTask(taskId, connectionId),
    onStarted: (run) => {
      setLlmSelectOpen(false)
      setExpandedSection('runHistory')
      setSelectedRunRecordId(run.runId ?? null)
    },
  })

  const deleteTaskMutation = useMutation({
    mutationFn: () => api.deleteApiCaseGenerateTask(taskId),
    onSuccess: () => {
      message.success('任务已删除')
      queryClient.removeQueries({ queryKey: ['apiCaseGenerateTask', taskId], exact: true })
      if (task?.projectId) {
        queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTasks', task.projectId] })
      }
      navigate('/ai-testing?tab=tasks')
    },
  })

  const deleteRunMutation = useDeleteTaskRun({
    kind: 'api',
    taskId,
    selectedRunId: selectedRunRecordId,
    onSelectedRunDeleted: () => {
      setSelectedRunRecordId(null)
    },
  })

  const reviewRunMutation = useMutation({
    mutationFn: (payload: {
      runId: string
      body: ReviewApiCaseGenerateTaskRunPayload
    }) => api.reviewApiCaseGenerateTaskRun(payload.runId, payload.body),
    onSuccess: (updatedRun, payload) => {
      message.success(payload.body.action === 'approve' ? '候选结果已批准' : '候选结果已拒绝')
      setReviewModalRunId(null)
      setReviewSubmitAction(null)
      reviewForm.resetFields()
      setSelectedRunRecordId(updatedRun.runId ?? payload.runId)
      queryClient.setQueryData(['apiCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTaskRuns', taskId] })
    },
  })

  const updateRunResultMutation = useMutation({
    mutationFn: (payload: { runId: string; resultYaml: string }) =>
      api.updateApiCaseGenerateTaskRunResult(payload.runId, { resultYaml: payload.resultYaml }),
    onSuccess: (updatedRun, payload) => {
      const savedYaml = updatedRun.resultYaml ?? payload.resultYaml
      setCandidateYaml(savedYaml)
      queryClient.setQueryData(['apiCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTaskRuns', taskId] })
      message.success('候选结果已保存')
    },
  })

  const importRunMutation = useMutation({
    mutationFn: (payload: { runId: string } & ImportApiCaseGenerateTaskRunPayload) =>
      api.importApiCaseGenerateTaskRun(payload.runId, {
        collectionId: payload.collectionId,
        confirmOverwrite: payload.confirmOverwrite ?? false,
      }),
    onSuccess: (result, payload) => {
      queryClient.invalidateQueries({ queryKey: ['apiCaseGenerateTaskRuns', taskId] })
      if (result.requiresConfirmation) {
        queryClient.setQueryData(['apiCaseGenerateTaskRun', payload.runId], (current: typeof selectedRun) => ({
          ...current,
          ...result.run,
          runId: result.run.runId ?? current?.runId ?? payload.runId,
        }))
        setImportModalRunId(null)
        setImportConflict({
          runId: payload.runId,
          collectionId: payload.collectionId,
          conflicts: result.conflicts,
        })
        return
      }
      queryClient.setQueryData(['apiCaseGenerateTaskRun', payload.runId], result.run)
      setImportModalRunId(null)
      setImportConflict(null)
      importForm.resetFields()
      message.success('已导入 API 集合')
    },
  })

  const creatorName = useMemo(() => normalizeUserName(currentUser), [currentUser])
  const runnableTask = isRunnableApiCaseGenerateTaskRun(latestRunRecord?.status)

  useEffect(() => {
    if (runRecords.length === 0) {
      setSelectedRunRecordId(null)
      return
    }
    setSelectedRunRecordId((current) =>
      current && runRecords.some((record) => record.runId === current) ? current : (runRecords[0].runId ?? null),
    )
  }, [runRecords])

  useEffect(() => {
    setRunResultModal(null)
  }, [selectedRunId])

  useEffect(() => {
    if (!reviewModalRunId) return
    reviewForm.setFieldsValue({
      reviewComment: undefined,
    })
  }, [reviewForm, reviewModalRunId])

  const selectedRunResultSectionMap = useMemo(
    () => new Map(selectedRunResultSections.map((section) => [section.key, section.value])),
    [selectedRunResultSections],
  )
  const runResultModalContent = runResultModal ? selectedRunResultSectionMap.get(runResultModal.key) : undefined
  const selectedRunReviewStatus = normalizeGenerateTaskReviewStatus(selectedRun?.reviewStatus)
  const reviewAvailable = Boolean(selectedRun) && selectedRunReviewStatus === 'pending' && selectedRun?.status === 'success'
  const canReviewSelectedRun = can('review') && reviewAvailable
  const candidateDirty = candidateYaml !== (selectedRun?.resultYaml ?? '')
  const selectedRunCandidateStats = useMemo(
    () => normalizeApiConfigCases(selectedRun?.resultYaml)?.cases ?? [],
    [selectedRun?.resultYaml],
  )
  const candidateRequirementName = task?.requirementId
    ? requirementNameMap.get(task.requirementId) ?? task.requirementId
    : '-'
  const resolveRunRecord = (record: (typeof runRecords)[number]) =>
    record.runId === selectedRunId && selectedRun ? selectedRun : record
  const runHistoryRefreshing = runsQuery.isFetching || selectedRunQuery.isFetching

  function handleRunTask() {
    if (runsQuery.isLoading) {
      message.warning('运行记录加载中，请稍后再试')
      return
    }
    if (!runnableTask) {
      message.warning('任务执行中，暂时不能重复运行')
      return
    }
    setLlmSelectOpen(true)
  }

  function handleLlmSelectConfirm(connectionId: string) {
    runTaskMutation.mutate(connectionId)
  }

  function handleRefreshRuns() {
    void runsQuery.refetch()
    if (selectedRunId) {
      void selectedRunQuery.refetch()
    }
  }

  function openReviewModal(runId?: string) {
    if (!runId) return
    setSelectedRunRecordId(runId)
    setCandidateYaml(selectedRun?.runId === runId ? (selectedRun.resultYaml ?? '') : '')
    setReviewModalRunId(runId)
    setReviewSubmitAction(null)
    setCandidateModalView('preview')
  }

  function closeReviewModal() {
    setReviewModalRunId(null)
    setReviewSubmitAction(null)
    setCandidateYaml(selectedRun?.resultYaml ?? '')
  }

  function requestCloseReviewModal() {
    if (!candidateDirty || !canReviewSelectedRun) {
      closeReviewModal()
      return
    }
    setDiscardCandidateConfirmOpen(true)
  }

  function handleSaveCandidateResult() {
    if (!reviewModalRunId) return
    updateRunResultMutation.mutate({ runId: reviewModalRunId, resultYaml: candidateYaml })
  }

  async function handleImportRun() {
    if (!importModalRunId) return
    const values = await importForm.validateFields()
    importRunMutation.mutate({
      runId: importModalRunId,
      collectionId: values.collectionId,
      confirmOverwrite: false,
    })
  }

  function handleConfirmImportOverwrite() {
    if (!importConflict) return
    importRunMutation.mutate({
      runId: importConflict.runId,
      collectionId: importConflict.collectionId,
      confirmOverwrite: true,
    })
  }

  async function handleCopyExpandedRunResult() {
    const content = runResultModalContent
    if (!content) return
    try {
      await navigator.clipboard.writeText(content)
      message.success('已复制内容')
    } catch {
      message.error('复制失败，请手动复制')
    }
  }

  function handleDownloadExpandedRunResult() {
    const content = runResultModalContent
    if (!content) return
    const title = runResultModal?.label || '运行结果'
    const safeTitle = title.replace(/[\\/:*?"<>|]/g, '_')
    const extension = title.toLowerCase().includes('yaml') ? 'yaml' : 'txt'
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    saveBlob(blob, `${safeTitle}.${extension}`)
    message.success('已下载内容')
  }

  async function handleApproveReview() {
    if (!reviewModalRunId) return
    if (!canReviewSelectedRun) {
      message.warning('当前运行状态不允许批准候选结果')
      return
    }
    const values = await reviewForm.validateFields(['reviewComment'])
    setReviewSubmitAction('approve')
    reviewRunMutation.mutate({
      runId: reviewModalRunId,
      body: {
        action: 'approve',
        reviewComment: values.reviewComment?.trim() || undefined,
      },
    })
  }

  function handleRejectReview() {
    if (!reviewModalRunId) return
    if (!canReviewSelectedRun) {
      message.warning('当前运行状态不允许拒绝候选结果')
      return
    }
    const values = reviewForm.getFieldsValue()
    setReviewSubmitAction('reject')
    reviewRunMutation.mutate({
      runId: reviewModalRunId,
      body: {
        action: 'reject',
        reviewComment: values.reviewComment?.trim() || undefined,
      },
    })
  }

  return (<ProjectAccessScope resourceError={taskQuery.error} projectId={task?.projectId ?? ''}>{(
    <div className="workbench-page ai-testing-page tp-list-surface ai-task-detail-page tp-surface">
      <div className="workbench-tabs">
      {taskQuery.error ? <Alert showIcon type="error" title={getErrorMessage(taskQuery.error)} /> : null}
      {runsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(runsQuery.error)} /> : null}

      {!task && taskQuery.isLoading ? (
        <Spin />
      ) : task ? (
        <div className="ai-task-detail-layout">
          <TaskDetailToolbar
            back={(
              <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/ai-testing?tab=tasks')}>
                返回生成任务
              </Button>
            )}
            fields={[
              { label: '任务名称', value: task.name || '未命名任务', kind: 'name', separator: 'line' },
              { label: '迭代', value: task.sprintId ? sprintNameMap.get(task.sprintId) ?? task.sprintId : '-', kind: 'chip-accent' },
              { label: '需求', value: task.requirementId ? requirementNameMap.get(task.requirementId) ?? task.requirementId : '-' },
              { label: '来源类型', value: task.sourceType, kind: 'chip-muted' },
              { label: '创建人', value: creatorName },
              { label: '更新时间', value: formatTime(pickUpdatedAt(task)), kind: 'time', separator: 'dot' },
            ]}
            actions={(
              <>
                <ProjectActionButton action="execute"
                  className="action-btn-run"
                  operation="run"
                  disabled={runsQuery.isLoading || !runnableTask}
                  loading={runTaskMutation.isPending}
                  onClick={handleRunTask}
                >
                  运行
                </ProjectActionButton>
                <ProjectActionButton action="write"
                  className="action-btn-update"
                  operation="edit"
                  onClick={() => setDrawerOpen(true)}
                >
                  编辑
                </ProjectActionButton>
                <Popconfirm title="确认删除该任务？" onConfirm={() => deleteTaskMutation.mutate()}>
                  <ProjectActionButton action="write" danger className="action-btn-delete" operation="delete" loading={deleteTaskMutation.isPending}>
                    删除
                  </ProjectActionButton>
                </Popconfirm>
              </>
            )}
          />

          <div className="ai-task-detail-split">
            <TaskDetailNavPanel tip="点击左侧条目在右侧查看内容，运行时记录自动刷新。">
              <div className="ai-task-detail-nav-label">输入</div>
              <TaskDetailNavItem
                title="来源内容"
                sub={task.sourceContent ? '已配置来源内容' : '暂无来源内容'}
                icon={<FileTextOutlined />}
                active={expandedSection === 'sourceContent'}
                onClick={() => setExpandedSection('sourceContent')}
              />
              <TaskDetailNavItem
                title="生成指令"
                sub={task.instruction?.trim() || '暂无补充指令'}
                icon={<CodeOutlined />}
                active={expandedSection === 'instruction'}
                onClick={() => setExpandedSection('instruction')}
              />
              <div className="ai-task-detail-nav-label">输出</div>
              <TaskDetailNavItem
                title="运行记录"
                sub={`共 ${runRecords.length} 条运行记录`}
                icon={<HistoryOutlined />}
                active={expandedSection === 'runHistory'}
                badge={runRecords.length}
                onClick={() => setExpandedSection('runHistory')}
              />
            </TaskDetailNavPanel>

            <section className="ai-task-detail-main-panel">
              {expandedSection === 'sourceContent' ? (
                <>
                  <div className="ai-task-detail-main-head">
                    <span className="ai-task-detail-main-head-title">来源内容</span>
                  </div>
                  <div className="ai-task-detail-main-body">
                    <pre className="ai-task-code-block">{task.sourceContent || '-'}</pre>
                  </div>
                </>
              ) : expandedSection === 'instruction' ? (
                <>
                  <div className="ai-task-detail-main-head">
                    <span className="ai-task-detail-main-head-title">生成指令</span>
                  </div>
                  <div className="ai-task-detail-main-body">
                    <TaskDetailInstructionEditor
                      value={instructionDraft}
                      dirty={instructionDirty}
                      saving={updateTaskMutation.isPending}
                      onChange={(value) => {
                        setInstructionDraft(value)
                        setInstructionDirty(true)
                      }}
                      onSave={handleSaveInstruction}
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="ai-task-detail-main-head">
                    <span className="ai-task-detail-main-head-title">运行记录</span>
                    <div className="ai-task-detail-main-head-extra">
                      <div className="ai-task-run-history-toolbar">
                        <span className="ai-task-run-history-auto-refresh">每 5 秒自动刷新</span>
                        <ActionButton size="small" operation="refresh" loading={runHistoryRefreshing} onClick={handleRefreshRuns}>刷新</ActionButton>
                      </div>
                    </div>
                  </div>
                  <div className="ai-task-detail-main-body">
                  {runsQuery.isLoading ? (
                    <div className="ai-task-run-history-placeholder">
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="运行记录加载中..." />
                    </div>
                  ) : runRecords.length > 0 ? (
                    <>
                      <TaskDetailRunMetrics
                        {...summarizeRunStatuses(runRecords)}
                        latestStatus={renderApiCaseGenerateTaskRunStatusTag(runRecords[0].status)}
                      />
                      <RunHistoryTable
                        rows={runRecords}
                        getRunId={(record) => record.runId}
                        selectedRunId={selectedRunId}
                        resolveRow={resolveRunRecord}
                        onSelect={(runId) => setSelectedRunRecordId(runId ?? null)}
                        renderStatus={(row) => <RunPipelineStatus run={resolveRunRecord(row)} />}
                        renderArtifacts={(row) => {
                          const data = resolveRunRecord(row)
                          const runSucceeded = String(data.status ?? '').toLowerCase() === 'success'
                          const runAwaitingReview = runSucceeded && normalizeGenerateTaskReviewStatus(data.reviewStatus) === 'pending'
                          return (
                            <RunArtifacts
                              artifacts={[
                                { key: 'configJson', label: '中间配置', available: true },
                                { key: 'resultYaml', label: '结果 YAML', available: !runAwaitingReview },
                              ]}
                              onOpen={(key) => {
                                const section = runResultSectionDefinitions.find((item) => item.key === key)
                                if (!section) return
                                setSelectedRunRecordId(row.runId ?? null)
                                setRunResultModal({ key: section.key, label: section.label })
                              }}
                            />
                          )
                        }}
                        getReviewedAt={(row) => resolveRunRecord(row).reviewedAt}
                        getReviewComment={(row) => resolveRunRecord(row).reviewComment}
                        getImportedAt={(row) => resolveRunRecord(row).importedAt}
                        renderActions={(row) => {
                          const data = resolveRunRecord(row)
                          const runSucceeded = String(data.status ?? '').toLowerCase() === 'success'
                          const recordFailed = ['failed', 'error'].includes(String(data.status ?? '').toLowerCase())
                          const reviewStatus = normalizeGenerateTaskReviewStatus(data.reviewStatus)
                          const importedTargetId = (data.importedTargets ?? []).find(
                            (target) => target.targetType === 'api_collection',
                          )?.targetId ?? ''
                          const importedTargetName = importedTargetId
                            ? (apiCollectionNameMap.get(importedTargetId) ?? importedTargetId)
                            : ''
                          const menuItems: RunMenuAction[] = [
                            ...(can('execute') && data.status === 'success' && reviewStatus === 'approved' && data.importStatus === 'pending'
                              ? [{ key: 'importCollection', label: '导入 API 集合', disabled: importRunMutation.isPending }]
                              : []),
                            ...(data.importStatus === 'imported' && importedTargetId
                              ? [{ key: 'openCollection', label: '查看目标集合' }]
                              : []),
                            ...(row.runId && can('write')
                              ? [{
                                  key: 'deleteRun',
                                  label: '删除运行记录',
                                  danger: true,
                                  disabled: !isRunDeletable(data.status) || deleteRunMutation.isPending,
                                }]
                              : []),
                          ]
                          return (
                            <RunRowActions
                              inline={
                                <>
                                  {/* 审核是本行最需要用户处理的动作，直接放在操作列，「更多」只留状态变更类操作。 */}
                                  {runSucceeded && reviewStatus === 'pending' && can('read') ? (
                                    <Button
                                      size="small"
                                      type="primary"
                                      onClick={(event) => {
                                        event.stopPropagation()
                                        openReviewModal(row.runId)
                                      }}
                                    >
                                      {can('review') ? '审核结果' : '查看候选结果'}
                                    </Button>
                                  ) : null}
                                  {recordFailed && data.errorMessage?.trim() ? (
                                    <button
                                      type="button"
                                      className="ai-task-run-result-popover-btn"
                                      onClick={(event) => {
                                        event.stopPropagation()
                                        setSelectedRunRecordId(row.runId ?? null)
                                        setRunResultModal({ key: 'errorMessage', label: '错误信息' })
                                      }}
                                    >
                                      错误信息
                                    </button>
                                  ) : null}
                                  {data.importStatus === 'imported' && importedTargetName ? (
                                    <span className="ai-task-run-history-record-field">导入：{importedTargetName}</span>
                                  ) : null}
                                  {!data.importMigrationComplete ? <RunMigrationWarningIcon /> : null}
                                </>
                              }
                              menuItems={menuItems}
                              onMenuAction={(key) => {
                                if (key === 'importCollection') {
                                  setImportModalRunId(row.runId ?? null)
                                  return
                                }
                                if (key === 'openCollection' && importedTargetId) {
                                  navigate(`/api-automation/collections/${importedTargetId}`)
                                  return
                                }
                                if (key === 'deleteRun' && row.runId) {
                                  const runId = row.runId
                                  confirmDeleteRun(() => deleteRunMutation.mutate(runId))
                                }
                              }}
                            />
                          )
                        }}
                      />
                      {selectedRunQuery.isLoading && !selectedRun ? (
                        <div className="ai-task-run-history-placeholder compact">
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="运行详情加载中..." />
                        </div>
                      ) : null}
                      {selectedRun && selectedRunResultSections.length === 0 ? (
                        <div className="ai-task-run-history-hint compact">
                          当前选中记录暂无可展示结果
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <div className="ai-task-run-history-placeholder">
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="当前还没有运行记录"
                      />
                      <div className="ai-task-run-history-hint">
                        点击上方“运行”后，任务状态和最近一次执行信息会展示在这里。
                      </div>
                    </div>
                  )}
                  </div>
                </>
              )}
            </section>
          </div>
        </div>
      ) : (
        <Alert showIcon type="warning" title="未找到对应任务" />
      )}

      <ApiCaseGenerateTaskDrawer
        title="编辑 API 用例生成任务"
        open={drawerOpen}
        form={form}
        loading={updateTaskMutation.isPending}
        error={updateTaskMutation.error}
        sprintOptions={sprintOptions}
        requirementOptions={requirementOptions}
        onSprintChange={(value) => {
          setDrawerSprintId(value)
          form.setFieldValue('requirementId', undefined)
        }}
        onClose={() => setDrawerOpen(false)}
        onFinish={(values) => updateTaskMutation.mutate(values)}
      />

      <Modal
        mask={{ closable: false }}
        className="ai-task-import-result-modal"
        title={canReviewSelectedRun ? '审核结果' : 'API 用例候选结果'}
        open={Boolean(reviewModalRunId)}
        onCancel={requestCloseReviewModal}
        footer={
          reviewAvailable
            ? [
                <Button key="cancel" onClick={requestCloseReviewModal}>
                  取消
                </Button>,
                <ProjectActionButton action="review"
                  key="reject"
                  danger
                  ghost
                  loading={reviewRunMutation.isPending && reviewSubmitAction === 'reject'}
                  disabled={candidateDirty || updateRunResultMutation.isPending || reviewRunMutation.isPending}
                  onClick={handleRejectReview}
                >
                  拒绝
                </ProjectActionButton>,
                <ProjectActionButton action="review"
                  key="approve"
                  type="primary"
                  loading={reviewRunMutation.isPending && reviewSubmitAction === 'approve'}
                  disabled={candidateDirty || updateRunResultMutation.isPending || reviewRunMutation.isPending}
                  onClick={handleApproveReview}
                >
                  批准
                </ProjectActionButton>,
              ]
            : [
                <Button key="close" type="primary" onClick={requestCloseReviewModal}>
                  关闭
                </Button>,
              ]
        }
        destroyOnHidden
        width="min(1620px, calc(100vw - 72px))"
        centered
      >
        <Form form={reviewForm} layout="vertical" className="ai-task-import-result-form">
          <div className="ai-task-import-target-summary">
            <div className="ai-task-import-target-copy">
              <strong>候选结果</strong>
              <span title={candidateRequirementName}>关联需求：{candidateRequirementName}</span>
            </div>
            <div className="ai-task-import-target-stats">
              <Tag color="blue">接口 {selectedRunCandidateStats.length}</Tag>
              <Tag color="cyan">
                提取 {selectedRunCandidateStats.reduce((sum, item) => sum + item.extractRules.length, 0)}
              </Tag>
              <Tag color="purple">
                断言 {selectedRunCandidateStats.reduce((sum, item) => sum + item.assertRules.length, 0)}
              </Tag>
            </div>
          </div>
          <Tabs
            activeKey={candidateModalView}
            onChange={(key) => setCandidateModalView(key as 'preview' | 'edit')}
            items={[
              {
                key: 'preview',
                label: '预览候选',
                children: (
                  <div className="ai-task-review-modal-content ai-task-result-preview-modal-content ai-task-import-result-preview-content single-column">
                    <div className="ai-task-review-modal-section">
                      <div className="ai-task-review-modal-preview ai-task-import-result-preview">
                        {selectedRunQuery.isLoading ? (
                          <div className="ai-task-run-result-popover-loading">
                            <Spin />
                          </div>
                        ) : selectedRun?.resultYaml ? (
                          <ApiCandidateResultView content={selectedRun.resultYaml} />
                        ) : (
                          <div className="ai-task-run-result-popover-empty">当前记录暂无结果</div>
                        )}
                      </div>
                    </div>
                  </div>
                ),
              },
              {
                key: 'edit',
                label: '编辑候选',
                children: (
                  <div className="ai-task-review-modal-content single-column">
                    <TextCodeEditor
                      ariaLabel="候选结果 YAML"
                      value={candidateYaml}
                      onChange={setCandidateYaml}
                      readOnly={!canReviewSelectedRun}
                      language="yaml"
                      foldable
                      minHeight={520}
                    />
                    {updateRunResultMutation.error ? (
                      <Alert showIcon type="error" title={getErrorMessage(updateRunResultMutation.error)} />
                    ) : null}
                    {reviewAvailable ? (
                      <ProjectActionButton action="write"
                        type="primary"
                        loading={updateRunResultMutation.isPending}
                        disabled={!candidateDirty || reviewRunMutation.isPending}
                        onClick={handleSaveCandidateResult}
                      >
                        保存候选结果
                      </ProjectActionButton>
                    ) : null}
                  </div>
                ),
              },
            ]}
          />
          {reviewRunMutation.error ? <Alert showIcon type="error" title={getErrorMessage(reviewRunMutation.error)} /> : null}
          <Form.Item label="审核备注" name="reviewComment" htmlFor="api-review-comment">
            <Input.TextArea
              id="api-review-comment"
              rows={4}
              placeholder="请输入审核备注或拒绝原因"
              disabled={!canReviewSelectedRun}
            />
          </Form.Item>
        </Form>
      </Modal>

      <ProjectActionModal action="write"
        mask={{ closable: false }}
        title="修改尚未保存，确定放弃吗？"
        open={discardCandidateConfirmOpen}
        okText="放弃修改"
        cancelText="继续编辑"
        onCancel={() => setDiscardCandidateConfirmOpen(false)}
        onOk={() => {
          setDiscardCandidateConfirmOpen(false)
          closeReviewModal()
        }}
        destroyOnHidden
      >
        放弃后将恢复为最近一次保存的候选结果。
      </ProjectActionModal>

      <ProjectActionModal action="execute"
        mask={{ closable: false }}
        title="导入 API 集合"
        open={Boolean(importModalRunId)}
        onCancel={() => {
          setImportModalRunId(null)
          importForm.resetFields()
        }}
        onOk={handleImportRun}
        okText="开始导入"
        cancelText="取消"
        confirmLoading={importRunMutation.isPending}
        destroyOnHidden
      >
        {importRunMutation.error ? (
          <Alert showIcon type="error" title={getErrorMessage(importRunMutation.error)} />
        ) : null}
        <Form form={importForm} layout="vertical">
          <Form.Item
            label="目标 API 集合"
            name="collectionId"
            rules={[{ required: true, message: '请选择目标 API 集合' }]}
            extra={!apiCollectionsQuery.isLoading && apiCollectionOptions.length === 0 ? '当前需求下还没有可用的 API 集合' : undefined}
          >
            <Select
              showSearch
              placeholder={apiCollectionsQuery.isLoading ? 'API 集合加载中...' : '请选择 API 集合'}
              options={apiCollectionOptions}
              loading={apiCollectionsQuery.isLoading}
              optionFilterProp="label"
            />
          </Form.Item>
        </Form>
      </ProjectActionModal>

      <ApiImportConflictModal
        open={Boolean(importConflict)}
        conflicts={importConflict?.conflicts ?? []}
        loading={importRunMutation.isPending}
        error={importConflict ? importRunMutation.error : undefined}
        onCancel={() => setImportConflict(null)}
        onConfirm={handleConfirmImportOverwrite}
      />

      <Modal
        mask={{ closable: false }}
        title={
          <div className="ai-task-run-result-expanded-title">
            <span>{runResultModal?.label ?? '运行结果'}</span>
            <div className="ai-task-run-result-expanded-actions">
              <Tooltip title="复制内容">
                <Button type="text" size="small" icon={<CopyOutlined />} onClick={handleCopyExpandedRunResult} />
              </Tooltip>
              <Tooltip title="下载内容">
                <ActionButton type="text" size="small" operation="download" iconOnly onClick={handleDownloadExpandedRunResult} />
              </Tooltip>
            </div>
          </div>
        }
        open={Boolean(runResultModal)}
        onCancel={() => setRunResultModal(null)}
        footer={null}
        width="min(1620px, calc(100vw - 72px))"
        className="ai-task-run-result-modal api-task-run-result-modal"
        wrapClassName="api-task-run-result-modal-wrap"
        centered
        destroyOnHidden
      >
        <div className="ai-task-run-result-modal-content api-task-run-result-modal-content">
          {selectedRunQuery.isLoading ? (
            <div className="ai-task-run-result-popover-loading">
              <Spin />
            </div>
          ) : runResultModalContent ? (
            runResultModal?.key === 'configJson' ? (
              <ApiConfigResultView content={runResultModalContent} />
            ) : (
              <pre className="ai-task-code-block">{runResultModalContent}</pre>
            )
          ) : (
            <div className="ai-task-run-result-popover-empty">暂无内容</div>
          )}
        </div>
      </Modal>

      <LlmConnectionSelectModal
        open={llmSelectOpen}
        projectId={task?.projectId}
        onClose={() => setLlmSelectOpen(false)}
        onConfirm={handleLlmSelectConfirm}
        loading={runTaskMutation.isPending}
      />
      </div>
    </div>
  )}</ProjectAccessScope>)
}
