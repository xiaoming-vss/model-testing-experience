import { ActionButton } from '@/shared/components/ActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { usePersonalLlmChoice } from '../hooks/usePersonalLlmChoice'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ArrowLeftOutlined, CheckCircleFilled, DownOutlined, FileTextOutlined, LeftOutlined, PictureOutlined, PlayCircleOutlined, RightOutlined, SearchOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, Empty, Form, Input, Modal, Popconfirm, Select, Spin, Tabs, Tag } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toBlob } from 'html-to-image'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FunctionalCaseGenerateTaskDrawer, type FunctionalCaseGenerateTaskFormValues } from '../components/FunctionalCaseGenerateTaskDrawer'
import { RevisionDivider, RevisionSidePanel } from '../components/RevisionSidePanel'
import { buildRevisionTemplate, getRevisionQuestions } from '../utils/functionalRevision'
import { FunctionalImportConflictModal } from '../components/FunctionalImportConflictModal'
import { RunArtifacts, RunPipelineStatus } from '../components/RunPipelineStatus'
import { RunHistoryTable, RunMigrationWarningIcon, RunRowActions } from '../components/RunHistoryTable'
import { getRunPipelineModel, type RunPipelineFilterKey } from '../utils/runPipeline'
import { LlmConnectionSelectModal } from '../components/LlmConnectionSelectModal'
import type { FunctionalCaseGenerateTaskRun, FunctionalCaseGenerateTaskRunImportConflict } from '../types'
import { getApiCaseGenerateTaskRunStatusMeta, isRunnableApiCaseGenerateTaskRun } from '../utils/taskStatus'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { useThemeStore } from '@/shared/store/theme.store'
import { message } from '@/shared/utils/feedback'
import '@/features/ai-testing/styles/index.css'
import '../styles/functional-import-confirm.css'
import { RequirementDocumentPreviewContent } from '@/features/requirements/components/RequirementDocumentPreviewModal'
import { hasRequirementEnhancedText, hasRequirementDocument } from '@/features/requirements/utils/requirementDocument'
import { ApiError } from '@/shared/api/request'
import { api, listItems } from '@/services/api'
import { formatTime, getErrorMessage, normalizeRequirementId, normalizeSprintId, pickUpdatedAt } from '@/utils/format'

const runResultSectionDefinitions = [
  { key: 'enhancedText', label: '增强文本' },
  { key: 'requirementAnalysis', label: '需求分析' },
  { key: 'caseNames', label: '测试点' },
  { key: 'caseRelations', label: '图谱分析' },
  { key: 'errorMessage', label: '错误信息' },
] as const

type CaseNamesViewMode = 'json' | 'tree'
type RequirementAnalysisViewMode = 'json' | 'diagram'

type CaseNameTreeNode = {
  id: string
  title: string
  kind: 'root' | 'model' | 'testModel' | 'point'
  children: CaseNameTreeNode[]
}

type RunResultSectionKey = (typeof runResultSectionDefinitions)[number]['key']

type RunResultModalState = {
  key: RunResultSectionKey
  label: string
} | null

type GeneratedCaseImportStats = {
  moduleCount: number
  caseCount: number
  moduleNames: string[]
}

const functionalStageMetaMap: Record<string, { label: string; color: string }> = {
  enhanced_text: { label: '增强文档输出', color: 'cyan' },
  requirement_analysis: { label: '测试需求/风险/测试点输出', color: 'blue' },
  case_names: { label: '测试用例名称/测试点输出', color: 'geekblue' },
  detailed_cases: { label: '详细测试用例输出', color: 'purple' },
  relation_analysis: { label: '图谱分析', color: 'volcano' },
  completed: { label: '已完成', color: 'success' },
}

const stageConfigFieldMap: Record<string, { key: string; label: string }> = {
  enhanced_text: { key: 'enhancedText', label: '增强文本 enhancedText' },
  requirement_analysis: { key: 'requirementAnalysis', label: '需求分析 requirementAnalysis' },
  case_names: { key: 'caseNames', label: '测试点 caseNames' },
}

function formatStructuredContent(value?: unknown) {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function parseJsonLikeContent(value?: unknown) {
  if (value === undefined || value === null || value === '') return undefined
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return undefined
  }
}

function getOutputRepairProgress(summary: unknown): string | null {
  const parsed = parseJsonLikeContent(summary)
  const progress = parsed && typeof parsed === 'object' ? parsed.outputValidation : undefined
  if (!progress || progress.status !== 'repairing' || !Number.isInteger(progress.repairAttempt) || progress.repairAttempt < 1) return null
  const stage = { requirement_analysis: '需求分析', case_names: '测试点', detailed_cases: '详细用例', relation_analysis: '图谱分析' }[progress.stage as 'requirement_analysis' | 'case_names' | 'detailed_cases' | 'relation_analysis']
  if (!stage) return null
  return `${stage}${typeof progress.module === 'string' && progress.module ? ` / ${progress.module}` : ''}：输出校验未通过，正在进行第 ${progress.repairAttempt}/2 次自动修复`
}

function getGeneratedCaseImportStats(content?: unknown): GeneratedCaseImportStats {
  const parsed = parseJsonLikeContent(content)
  const cases = Array.isArray(parsed)
    ? parsed
    : parsed && typeof parsed === 'object' && Array.isArray((parsed as Record<string, unknown>).cases)
      ? (parsed as Record<string, unknown>).cases as unknown[]
      : []
  const moduleNames = new Set<string>()

  cases.forEach((item) => {
    if (!item || typeof item !== 'object') {
      moduleNames.add('未分组')
      return
    }
    const moduleName = toDisplayText((item as Record<string, unknown>).case_module) || '未分组'
    moduleNames.add(moduleName)
  })

  return {
    moduleCount: moduleNames.size,
    caseCount: cases.length,
    moduleNames: [...moduleNames],
  }
}

function getConfigStageFieldContent(configJson?: unknown, fieldKey?: string) {
  if (!fieldKey) return ''
  const parsed = parseJsonLikeContent(configJson)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return ''
  const record = parsed as Record<string, unknown>
  const directFieldContent = record[fieldKey]
  if (directFieldContent !== undefined && directFieldContent !== null && directFieldContent !== '') {
    return formatStructuredContent(directFieldContent)
  }

  if (isDirectStageConfigContent(record, fieldKey)) {
    return formatStructuredContent(record)
  }

  return ''
}

function isDirectStageConfigContent(record: Record<string, unknown>, fieldKey: string) {
  if (fieldKey === 'caseNames') {
    return Array.isArray(record.categories)
  }

  if (fieldKey === 'requirementAnalysis') {
    return Boolean(
      record.Platform_core_functions ||
        record.Target_understanding ||
        record.Risk_point_prediction ||
        record.function_flow ||
        record.Scene_Design ||
        record.functionalOverview ||
        record.businessRules ||
        record.scenarioFactors ||
        record.scenarioBreakdown ||
        record.openQuestions,
    )
  }

  return false
}

function isJsonText(content?: string) {
  if (!content?.trim()) return false
  try {
    JSON.parse(content)
    return true
  } catch {
    return false
  }
}

function toDisplayText(value: unknown) {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const record = value as Record<string, unknown>
    const namedValue = record.case_name ?? record.test_point ?? record.name ?? record.title
    if (namedValue !== undefined && namedValue !== null && namedValue !== '') return toDisplayText(namedValue)
  }
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function toTextList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(toDisplayText).filter(Boolean)
  }
  const text = toDisplayText(value)
  return text ? [text] : []
}

function toCaseNamePointList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(toDisplayText).filter(Boolean)
  }
  const text = toDisplayText(value)
  return text ? [text] : []
}

type RequirementAnalysisSection = {
  functionalOverview?: unknown
  businessRules?: unknown
  scenarioFactors?: unknown
  scenarioBreakdown?: unknown
  openQuestions?: unknown
  Platform_core_functions?: unknown
  Target_understanding?: unknown
  Risk_point_prediction?: unknown
  function_flow?: unknown
  Scene_Design?: unknown
}

function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function toRecordArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
}

function formatTextList(value: unknown) {
  return toTextList(value).join('\n')
}

function formatRoleConcerns(value: unknown) {
  return toRecordArray(value)
    .map((item) => {
      const role = toDisplayText(item.role)
      const concern = toDisplayText(item.concern)
      if (role && concern) return `${role}：${concern}`
      return role || concern || toDisplayText(item)
    })
    .filter(Boolean)
    .join('\n')
}

type GeneratedTestCase = {
  moduleName: string
  displayName: string
  tagFields: Array<{ key: string; label: string; value: string }>
  detailFields: Array<{ key: string; label: string; value: string }>
}

type GeneratedCaseModuleGroup = {
  moduleName: string
  cases: GeneratedTestCase[]
}

const MODULE_FIELD_CANDIDATES = ['case_module', 'module', 'module_name', 'moduleName', 'group', 'category']
const NAME_FIELD_CANDIDATES = ['Case Title', 'case_title', 'case_name', 'name', 'title', 'caseName', 'test_point', 'testPoint', 'scenario', 'description']
const TAG_FIELD_CANDIDATES = ['case_id', 'caseId', 'priority', 'case_type', 'caseType', 'type', 'level', 'severity']
const CASE_ID_FIELDS = ['case_id', 'caseId']

// 平台分配的编号是 UUID，卡片上只展示前缀，完整值保留在 title 上。
function formatCaseIdTag(value: string) {
  return value.length > 8 ? `${value.slice(0, 8)}…` : value
}

const FIELD_LABEL_MAP: Record<string, string> = {
  case_id: '用例编号',
  caseId: '用例编号',
  case_name: '用例名称',
  case_title: '用例名称',
  'Case Title': '用例名称',
  name: '用例名称',
  title: '用例名称',
  caseName: '用例名称',
  test_point: '测试点',
  testPoint: '测试点',
  scenario: '场景',
  description: '描述',
  preconditions: '前置条件',
  precondition: '前置条件',
  preCondition: '前置条件',
  steps: '测试步骤',
  test_steps: '测试步骤',
  testSteps: '测试步骤',
  operation: '操作步骤',
  expected_results: '预期结果',
  expectedResult: '预期结果',
  expectedResults: '预期结果',
  expected_result: '预期结果',
  priority: '优先级',
  case_type: '用例类型',
  caseType: '用例类型',
  type: '类型',
  level: '级别',
  severity: '严重程度',
  case_module: '模块',
  module: '模块',
  module_name: '模块',
  moduleName: '模块',
  group: '分组',
  category: '分类',
  order: '序号',
  orderNo: '序号',
  remark: '备注',
  note: '备注',
}

function pickFirstField(record: Record<string, unknown>, candidates: string[]): string {
  for (const key of candidates) {
    const val = toDisplayText(record[key])
    if (val) return val
  }
  return ''
}

function isTagField(key: string, value: string): boolean {
  if (TAG_FIELD_CANDIDATES.includes(key)) return true
  if (value.length <= 12 && /^P[1-4]$/.test(value)) return true
  if (value.length <= 8 && /^\d+$/.test(value)) return true
  return false
}

function formatFieldLabel(key: string): string {
  if (FIELD_LABEL_MAP[key]) return FIELD_LABEL_MAP[key]
  return key.replace(/[_-]/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/\b\w/g, (c) => c.toUpperCase())
}

function parseGeneratedCases(content?: string): GeneratedCaseModuleGroup[] {
  if (!content?.trim()) return []
  try {
    const parsed = JSON.parse(content)
    const rawCases: unknown[] = Array.isArray(parsed)
      ? parsed
      : parsed && typeof parsed === 'object' && Array.isArray((parsed as Record<string, unknown>).cases)
        ? (parsed as Record<string, unknown>).cases as unknown[]
        : []
    if (rawCases.length === 0) return []

    const moduleMap = new Map<string, GeneratedTestCase[]>()
    rawCases.forEach((item) => {
      if (!item || typeof item !== 'object') {
        const group = moduleMap.get('未分组') ?? []
        group.push({ moduleName: '未分组', displayName: toDisplayText(item) || '未命名用例', tagFields: [], detailFields: [] })
        moduleMap.set('未分组', group)
        return
      }
      const record = item as Record<string, unknown>
      const moduleName = pickFirstField(record, MODULE_FIELD_CANDIDATES) || '未分组'
      const displayName = pickFirstField(record, NAME_FIELD_CANDIDATES) || '未命名用例'

      const tagFields: Array<{ key: string; label: string; value: string }> = []
      const detailFields: Array<{ key: string; label: string; value: string }> = []
      const nameKey = NAME_FIELD_CANDIDATES.find((k) => toDisplayText(record[k]))
      const moduleKey = MODULE_FIELD_CANDIDATES.find((k) => toDisplayText(record[k]))

      Object.entries(record).forEach(([key, rawValue]) => {
        if (key === nameKey || key === moduleKey) return
        const value = toDisplayText(rawValue)
        if (!value) return
        if (isTagField(key, value)) {
          tagFields.push({ key, label: formatFieldLabel(key), value })
        } else {
          detailFields.push({ key, label: formatFieldLabel(key), value })
        }
      })

      const testCase: GeneratedTestCase = { moduleName, displayName, tagFields, detailFields }
      const group = moduleMap.get(moduleName) ?? []
      group.push(testCase)
      moduleMap.set(moduleName, group)
    })

    return [...moduleMap.entries()].map(([moduleName, cases]) => ({ moduleName, cases }))
  } catch {
    return []
  }
}

function parseRequirementAnalysisContent(content: string): RequirementAnalysisSection | null {
  if (!content.trim()) return null

  try {
    const parsed = JSON.parse(content)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed as RequirementAnalysisSection
  } catch {
    return null
  }
}

function RequirementAnalysisCollapsibleSection({
  title,
  count,
  color,
  children,
}: {
  title: string
  count: number
  color: string
  children: ReactNode
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <section className="ai-requirement-analysis-section">
      <button
        type="button"
        className="ai-requirement-analysis-section-head"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className="ai-requirement-analysis-section-title">
          {expanded ? <DownOutlined aria-hidden /> : <RightOutlined aria-hidden />}
          <span>{title}</span>
        </span>
        <Tag color={color}>{count}</Tag>
      </button>
      {expanded ? children : null}
    </section>
  )
}

const analysisDetailLabels: Record<string, string> = {
  purpose: '功能目的', actors: '参与角色', applicableObjects: '适用对象',
  explicitExclusions: '明确排除范围', category: '规则分类', trigger: '触发操作',
  preconditions: '前置条件', applicableObject: '适用对象', expectedBehavior: '预期行为',
  prohibitedOrSkippedBehavior: '禁止或跳过的行为', observableOutcome: '可观察结果',
  confirmationStatus: '确认状态', sourceReferences: '来源依据', relatedRuleIds: '关联规则',
  relatedQuestionIds: '关联待确认项', confirmedValues: '已确认取值', defaultValue: '默认值',
  clarificationNeeded: '待澄清内容', conditions: '场景条件', derivationType: '推导类型',
  verificationObjective: '验证目标', blockingReason: '阻塞原因',
  question: '待确认问题', blockedWork: '阻塞工作', affectedScope: '影响范围',
}

function AnalysisDetails({ item, fields }: { item: Record<string, unknown>; fields: string[] }) {
  return fields.map((field) => (
    <div className="ai-requirement-analysis-field" key={field}>
      <span>{analysisDetailLabels[field]}</span>
      <p>{formatTextList(item[field]) || (Array.isArray(item[field]) ? '无' : '未明确')}</p>
    </div>
  ))
}

function StructuredAnalysisSections({ parsed }: { parsed: RequirementAnalysisSection }) {
  const overview = toRecord(parsed.functionalOverview)
  const sections = [
    { title: '业务规则', color: 'blue', items: toRecordArray(parsed.businessRules), id: 'ruleId',
      fields: ['category', 'applicableObject', 'preconditions', 'trigger', 'expectedBehavior', 'prohibitedOrSkippedBehavior', 'observableOutcome', 'confirmationStatus', 'sourceReferences', 'relatedQuestionIds'] },
    { title: '场景因素', color: 'cyan', items: toRecordArray(parsed.scenarioFactors), id: 'factorId',
      fields: ['confirmedValues', 'defaultValue', 'clarificationNeeded'] },
    { title: '场景拆解', color: 'purple', items: toRecordArray(parsed.scenarioBreakdown), id: 'scenarioId',
      fields: ['conditions', 'trigger', 'verificationObjective', 'derivationType', 'relatedRuleIds', 'relatedQuestionIds', 'blockingReason'] },
    { title: '待确认项', color: 'orange', items: toRecordArray(parsed.openQuestions), id: 'questionId',
      fields: ['question', 'affectedScope', 'blockedWork'] },
  ]
  return (
    <>
      {overview && (
        <RequirementAnalysisCollapsibleSection title="功能概览" count={1} color="geekblue">
          <article className="ai-requirement-analysis-card">
            <AnalysisDetails item={overview} fields={['purpose', 'actors', 'applicableObjects', 'explicitExclusions']} />
            <div className="ai-requirement-analysis-field"><span>功能入口</span></div>
            <div className="ai-requirement-analysis-grid two-col">
              {toRecordArray(overview.entryPoints).map((entry, index) => (
                <article className="ai-requirement-analysis-card nested" key={index}>
                  <div className="ai-requirement-analysis-card-title">{toDisplayText(entry.function) || `入口 ${index + 1}`}</div>
                  <div className="ai-requirement-analysis-field"><span>入口路径</span><p>{toDisplayText(entry.path) || '未明确'}</p></div>
                  <div className="ai-requirement-analysis-field"><span>操作</span><p>{toDisplayText(entry.action) || '未明确'}</p></div>
                </article>
              ))}
            </div>
          </article>
        </RequirementAnalysisCollapsibleSection>
      )}
      {sections.map(({ title, color, items, id, fields }) => items.length > 0 && (
        <RequirementAnalysisCollapsibleSection key={id} title={title} count={items.length} color={color}>
          <div className="ai-requirement-analysis-grid two-col">
            {items.map((item, index) => (
              <article className="ai-requirement-analysis-card" key={`${toDisplayText(item[id])}-${index}`}>
                <div className="ai-requirement-analysis-card-title">
                  <Tag color={color}>{toDisplayText(item[id]) || `${index + 1}`}</Tag>
                  {toDisplayText(item.name) || (id === 'scenarioId' ? `场景 ${index + 1}` : title)}
                </div>
                {id === 'scenarioId' && (
                  <div><Tag color={item.readyForTestPointGeneration === true ? 'green' : 'orange'}>
                    {item.readyForTestPointGeneration === true ? '可生成测试点' : item.readyForTestPointGeneration === false ? '暂不可生成测试点' : '生成就绪状态未明确'}
                  </Tag></div>
                )}
                <AnalysisDetails item={item} fields={fields} />
              </article>
            ))}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ))}
    </>
  )
}

function RequirementAnalysisDiagramView({ content }: { content: string }) {
  const parsed = useMemo(() => parseRequirementAnalysisContent(content), [content])

  if (!parsed) {
    return isJsonText(content) ? (
      <JsonEditor value={content} readOnly foldable minHeight={640} />
    ) : (
      <pre className="ai-task-code-block">{content}</pre>
    )
  }

  const coreFunctions = toRecordArray(parsed.Platform_core_functions)
  const targetUnderstanding = toRecord(parsed.Target_understanding)
  const legacyTargets = toRecordArray(parsed.Target_understanding)
  const targetSections = targetUnderstanding
    ? [
        { key: 'business_goal', title: '业务目标', content: formatTextList(targetUnderstanding.business_goal) },
        { key: 'test_goal', title: '测试目标', content: formatTextList(targetUnderstanding.test_goal) },
        { key: 'user_roles_and_concerns', title: '用户角色与关注点', content: formatRoleConcerns(targetUnderstanding.user_roles_and_concerns) },
        { key: 'quality_attributes', title: '质量属性', content: formatTextList(targetUnderstanding.quality_attributes) },
      ].filter((item) => item.content)
    : []
  const risks = toRecordArray(parsed.Risk_point_prediction)
  const flows = toRecordArray(parsed.function_flow)
  const scenes = toRecordArray(parsed.Scene_Design)

  const hasStructuredContent = toRecord(parsed.functionalOverview) ||
    [parsed.businessRules, parsed.scenarioFactors, parsed.scenarioBreakdown, parsed.openQuestions]
      .some((value) => toRecordArray(value).length > 0)
  if (!hasStructuredContent && !coreFunctions.length && !targetSections.length && !legacyTargets.length && !risks.length && !flows.length && !scenes.length) {
    return <Empty description="暂无可展示的需求分析内容，请在 json 页签查看原始数据" />
  }

  return (
    <div className="ai-requirement-analysis-view">
      <StructuredAnalysisSections parsed={parsed} />
      {coreFunctions.length > 0 ? (
        <RequirementAnalysisCollapsibleSection title="平台核心功能" count={coreFunctions.length} color="blue">
          <div className="ai-requirement-analysis-grid two-col">
            {coreFunctions.map((item, index) => (
              <article key={`core-${index}`} className="ai-requirement-analysis-card">
                <div className="ai-requirement-analysis-card-title">{toDisplayText(item.function_name ?? item.function) || `功能 ${index + 1}`}</div>
                <div className="ai-requirement-analysis-field">
                  <span>能力说明</span>
                  <p>{toDisplayText(item.function_description ?? item.description) || '-'}</p>
                </div>
                <div className="ai-requirement-analysis-field accent">
                  <span>业务价值</span>
                  <p>{toDisplayText(item.business_value) || '-'}</p>
                </div>
              </article>
            ))}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ) : null}

      {targetSections.length > 0 || legacyTargets.length > 0 ? (
        <RequirementAnalysisCollapsibleSection title="目标理解" count={targetSections.length || legacyTargets.length} color="cyan">
          <div className="ai-requirement-analysis-list">
            {targetSections.length > 0 ? targetSections.map((item, index) => (
              <article key={`target-${item.key}`} className="ai-requirement-analysis-row-card">
                <div className="ai-requirement-analysis-row-index">{index + 1}</div>
                <div className="ai-requirement-analysis-row-body">
                  <div className="ai-requirement-analysis-card-title">{item.title}</div>
                  <p>{item.content}</p>
                </div>
              </article>
            )) : legacyTargets.map((item, index) => (
              <article key={`target-${index}`} className="ai-requirement-analysis-row-card">
                <div className="ai-requirement-analysis-row-index">{index + 1}</div>
                <div className="ai-requirement-analysis-row-body">
                  <div className="ai-requirement-analysis-card-title">{toDisplayText(item.target) || `目标 ${index + 1}`}</div>
                  <p>{toDisplayText(item.description) || '-'}</p>
                </div>
              </article>
            ))}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ) : null}

      {risks.length > 0 ? (
        <RequirementAnalysisCollapsibleSection title="风险点预测" count={risks.length} color="volcano">
          <div className="ai-requirement-analysis-grid two-col">
            {risks.map((item, index) => (
              <article key={`risk-${index}`} className="ai-requirement-analysis-card risk">
                <div className="ai-requirement-analysis-card-title">{toDisplayText(item.risk_category ?? item.risk_area) || `风险 ${index + 1}`}</div>
                <div className="ai-requirement-analysis-field">
                  <span>风险说明</span>
                  <p>{formatTextList(item.risk_points ?? item.risk_description) || '-'}</p>
                </div>
                <div className="ai-requirement-analysis-field accent danger">
                  <span>影响链路</span>
                  <p>{formatTextList(item.affected_links ?? item.impact) || '-'}</p>
                </div>
              </article>
            ))}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ) : null}

      {flows.length > 0 ? (
        <RequirementAnalysisCollapsibleSection title="功能流程" count={flows.length} color="geekblue">
          <div className="ai-requirement-analysis-flow-list">
            {flows.map((item, index) => (
              <article key={`flow-${index}`} className="ai-requirement-analysis-flow-card">
                <div className="ai-requirement-analysis-flow-step">0{index + 1}</div>
                <div className="ai-requirement-analysis-flow-body">
                  <div className="ai-requirement-analysis-card-title">{toDisplayText(item.flow_name) || `流程 ${index + 1}`}</div>
                  <div className="ai-requirement-analysis-field">
                    <span>流程和依赖链</span>
                    <p>{toDisplayText(item.description) || '-'}</p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ) : null}

      {scenes.length > 0 ? (
        <RequirementAnalysisCollapsibleSection title="场景设计" count={scenes.length} color="purple">
          <div className="ai-requirement-analysis-scene-groups">
            {scenes.map((scene, index) => {
              const subCategories = toRecordArray(scene.subcategories ?? scene.sub_category)
              return (
                <article key={`scene-${index}`} className="ai-requirement-analysis-scene-group">
                  <div className="ai-requirement-analysis-scene-head">
                    <div className="ai-requirement-analysis-card-title">{toDisplayText(scene.scene_type) || `场景 ${index + 1}`}</div>
                    <Tag color="default">{subCategories.length} 项</Tag>
                  </div>
                  <div className="ai-requirement-analysis-grid two-col">
                    {subCategories.map((item, subIndex) => (
                      <article key={`scene-${index}-sub-${subIndex}`} className="ai-requirement-analysis-card nested">
                        <div className="ai-requirement-analysis-card-title">{toDisplayText(item.name ?? item.scene_type) || `子场景 ${subIndex + 1}`}</div>
                        <div className="ai-requirement-analysis-field">
                          <span>场景说明</span>
                          <p>{toDisplayText(item.description) || '-'}</p>
                        </div>
                      </article>
                    ))}
                  </div>
                </article>
              )
            })}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ) : null}
    </div>
  )
}

function RequirementAnalysisView({ content }: { content: string }) {
  const [activeView, setActiveView] = useState<RequirementAnalysisViewMode>('diagram')
  const parsed = useMemo(() => parseRequirementAnalysisContent(content), [content])
  const isDiagramAvailable = Boolean(parsed)

  return (
    <Tabs
      className="ai-requirement-analysis-tabs"
      size="small"
      activeKey={activeView}
      onChange={(key) => setActiveView(key as RequirementAnalysisViewMode)}
      items={[
        {
          key: 'diagram',
          label: '可视化',
          children: isDiagramAvailable ? (
            <RequirementAnalysisDiagramView content={content} />
          ) : (
            <div className="ai-task-run-result-popover-empty">当前内容无法解析为结构化需求分析</div>
          ),
        },
        {
          key: 'json',
          label: 'json',
          children: isJsonText(content) ? (
            <JsonEditor value={content} readOnly foldable minHeight={640} />
          ) : (
            <pre className="ai-task-code-block">{content}</pre>
          ),
        },
      ]}
    />
  )
}

function getGeneratedCaseReviewCategory(testCase: GeneratedTestCase): string {
  for (const key of ['case_type', 'caseType', 'type']) {
    const value = testCase.tagFields.find((field) => field.key === key)?.value.trim()
    if (value) return value
  }
  return '未分类'
}

function getGeneratedCaseFieldLines(value: string): string[] {
  try {
    const parsed = JSON.parse(value)
    if (Array.isArray(parsed)) return parsed.map(toDisplayText).filter(Boolean)
  } catch {
    // 普通文本按换行展示，避免在预览中暴露 JSON 字符串形式。
  }
  return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
}

function isExpectedResultField(key: string) {
  return ['expected_results', 'expectedResult', 'expectedResults', 'expected_result'].includes(key)
}

function GeneratedCasesReviewView({ content }: { content: string }) {
  const moduleGroups = useMemo(() => parseGeneratedCases(content), [content])
  const [query, setQuery] = useState('')
  const [activeFilter, setActiveFilter] = useState<string | null>(null)
  const [selectedModule, setSelectedModule] = useState('')
  const totalCases = useMemo(() => moduleGroups.reduce((sum, group) => sum + group.cases.length, 0), [moduleGroups])
  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>()
    moduleGroups.forEach((group) => group.cases.forEach((testCase) => {
      const category = getGeneratedCaseReviewCategory(testCase)
      counts.set(category, (counts.get(category) ?? 0) + 1)
    }))
    return counts
  }, [moduleGroups])
  const currentFilter = activeFilter !== null && categoryCounts.has(activeFilter) ? activeFilter : null
  const filters = [
    { key: null, label: '全部', count: totalCases },
    ...Array.from(categoryCounts, ([key, count]) => ({ key, label: key, count })),
  ]
  const visibleGroups = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return moduleGroups.map((group) => ({
      ...group,
      cases: group.cases.filter((testCase) => {
        const matchesFilter = currentFilter === null || getGeneratedCaseReviewCategory(testCase) === currentFilter
        const matchesQuery = !normalizedQuery || group.moduleName.toLowerCase().includes(normalizedQuery) || testCase.displayName.toLowerCase().includes(normalizedQuery)
        return matchesFilter && matchesQuery
      }),
    })).filter((group) => group.cases.length > 0)
  }, [currentFilter, moduleGroups, query])
  const visibleCaseCount = visibleGroups.reduce((sum, group) => sum + group.cases.length, 0)

  useEffect(() => {
    if (visibleGroups.length === 0) {
      setSelectedModule('')
      return
    }
    if (!visibleGroups.some((group) => group.moduleName === selectedModule)) {
      setSelectedModule(visibleGroups[0].moduleName)
    }
  }, [selectedModule, visibleGroups])

  if (moduleGroups.length === 0) {
    return isJsonText(content) ? (
      <JsonEditor value={content} readOnly foldable minHeight={520} />
    ) : (
      <pre className="ai-task-code-block">{content}</pre>
    )
  }

  const activeGroup = visibleGroups.find((group) => group.moduleName === selectedModule) ?? visibleGroups[0]
  const activeGroupIndex = activeGroup ? visibleGroups.indexOf(activeGroup) : -1
  const caseStartIndex = activeGroup
    ? visibleGroups.slice(0, activeGroupIndex).reduce((sum, group) => sum + group.cases.length, 0)
    : 0

  return (
    <div className="ai-generated-cases-review">
      <aside className="ai-generated-cases-review-sidebar">
        <div className="ai-generated-cases-review-sidebar-head">
          <strong>用例分组</strong>
          <Input
            allowClear
            prefix={<SearchOutlined aria-hidden />}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索模块或场景"
            aria-label="搜索模块或场景"
          />
          <div className="ai-generated-cases-review-filters" aria-label="用例类型筛选">
            {filters.map((filter) => {
              return (
                <button
                  key={filter.key === null ? 'all' : `type:${filter.key}`}
                  type="button"
                  className={currentFilter === filter.key ? 'active' : ''}
                  aria-pressed={currentFilter === filter.key}
                  onClick={() => setActiveFilter(filter.key)}
                >
                  {filter.label} <span>{filter.count}</span>
                </button>
              )
            })}
          </div>
        </div>
        <div className="ai-generated-cases-review-groups">
          {visibleGroups.length > 0 ? visibleGroups.map((group) => (
            <button
              key={group.moduleName}
              type="button"
              className={group.moduleName === activeGroup?.moduleName ? 'active' : ''}
              aria-current={group.moduleName === activeGroup?.moduleName ? 'true' : undefined}
              onClick={() => setSelectedModule(group.moduleName)}
            >
              <span className="ai-generated-cases-review-group-name"><RightOutlined aria-hidden />{group.moduleName}</span>
              <span className="ai-generated-cases-review-count">{group.cases.length}</span>
            </button>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的用例分组" />}
        </div>
      </aside>

      <section className="ai-generated-cases-review-detail">
        {activeGroup ? (
          <>
            <header className="ai-generated-cases-review-detail-head">
              <div>
                <strong>{activeGroup.moduleName}</strong>
                <span>第 {caseStartIndex + 1}–{caseStartIndex + activeGroup.cases.length} 条，共 {visibleCaseCount} 条</span>
              </div>
              <div className="ai-generated-cases-review-pager">
                <Button
                  aria-label="上一个用例分组"
                  icon={<LeftOutlined />}
                  disabled={activeGroupIndex <= 0}
                  onClick={() => setSelectedModule(visibleGroups[activeGroupIndex - 1].moduleName)}
                />
                <Button
                  aria-label="下一个用例分组"
                  icon={<RightOutlined />}
                  disabled={activeGroupIndex >= visibleGroups.length - 1}
                  onClick={() => setSelectedModule(visibleGroups[activeGroupIndex + 1].moduleName)}
                />
              </div>
            </header>
            <div className="ai-generated-cases-review-card-list">
              {activeGroup.cases.map((testCase, caseIndex) => (
                <article key={`${activeGroup.moduleName}-${caseIndex}`} className="ai-generated-cases-review-card">
                  <header>
                    <span className="ai-generated-cases-review-index">{String(caseStartIndex + caseIndex + 1).padStart(2, '0')}</span>
                    {testCase.tagFields.map((tag) => {
                      const isCaseId = CASE_ID_FIELDS.includes(tag.key)
                      return (
                        <Tag key={tag.key} color="orange" title={isCaseId ? tag.value : undefined}>
                          {isCaseId ? formatCaseIdTag(tag.value) : tag.value}
                        </Tag>
                      )
                    })}
                    <strong>{testCase.displayName}</strong>
                  </header>
                  <div className="ai-generated-cases-review-fields">
                    {testCase.detailFields.map((field) => {
                      const expected = isExpectedResultField(field.key)
                      const lines = getGeneratedCaseFieldLines(field.value)
                      return (
                        <section key={field.key} className={expected ? 'expected' : ''}>
                          <div className="ai-generated-cases-review-field-title">
                            {expected ? <CheckCircleFilled aria-hidden /> : field.label === '测试步骤' ? <PlayCircleOutlined aria-hidden /> : <FileTextOutlined aria-hidden />}
                            <strong>{field.label}</strong>
                          </div>
                          {lines.length > 1 ? (
                            <ol>{lines.map((line, lineIndex) => <li key={`${field.key}-${lineIndex}`}>{line}</li>)}</ol>
                          ) : <p>{lines[0] || '-'}</p>}
                        </section>
                      )
                    })}
                  </div>
                </article>
              ))}
            </div>
          </>
        ) : <Empty description="请选择用例分组" />}
      </section>
    </div>
  )
}

function parseCaseNameRows(value: unknown, inheritedModel = '', inheritedTestModel = ''): Array<{ model: string; testModel: string; testPoints: string[] }> {
  if (Array.isArray(value)) {
    return value.flatMap((item) => parseCaseNameRows(item, inheritedModel, inheritedTestModel))
  }

  if (!value || typeof value !== 'object') {
    const text = toDisplayText(value)
    return text ? [{ model: inheritedModel || '未分组模块', testModel: inheritedTestModel || '未分组场景', testPoints: [text] }] : []
  }

  const record = value as Record<string, unknown>
  const model = toDisplayText(record.model) || inheritedModel
  const testModel = toDisplayText(record.test_model) || inheritedTestModel
  const directPoints = toCaseNamePointList(record.test_points)
  const rows = directPoints.length > 0 ? [{ model: model || '未分组模块', testModel: testModel || '未分组场景', testPoints: directPoints }] : []

  const nestedRows = Object.entries(record)
    .filter(([key]) => key !== 'model' && key !== 'test_model' && key !== 'test_points')
    .flatMap(([key, nestedValue]) => {
      const nextModel = model || key
      const nextTestModel = model ? testModel || key : testModel
      return parseCaseNameRows(nestedValue, nextModel, nextTestModel)
    })

  return [...rows, ...nestedRows]
}

function buildCategoryCaseNameTree(parsed: unknown, rootTitle: string): CaseNameTreeNode | null {
  const rootRecord = toRecord(parsed)
  const categories = rootRecord?.categories
  if (!Array.isArray(categories)) return null

  const categoryNodes = categories.reduce<CaseNameTreeNode[]>((categoryNodes, category, categoryIndex) => {
    const categoryRecord = toRecord(category)
    const data = categoryRecord?.data
    if (!categoryRecord || !Array.isArray(data)) return categoryNodes

    const testModelNodes = data.reduce<CaseNameTreeNode[]>((testModelNodes, item, dataIndex) => {
      const itemRecord = toRecord(item)
      const points = itemRecord?.test_points
      if (!itemRecord || !Array.isArray(points)) return testModelNodes

      const pointNodes = points.reduce<CaseNameTreeNode[]>((pointNodes, point, pointIndex) => {
        const title = toDisplayText(point)
        if (!title) return pointNodes
        pointNodes.push({
          id: `category-${categoryIndex}-data-${dataIndex}-point-${pointIndex}`,
          title,
          kind: 'point',
          children: [],
        })
        return pointNodes
      }, [])

      testModelNodes.push({
        id: `category-${categoryIndex}-data-${dataIndex}`,
        title: toDisplayText(itemRecord.test_model) || '未分组场景',
        kind: 'testModel',
        children: pointNodes,
      })

      return testModelNodes
    }, [])

    if (testModelNodes.length === 0) return categoryNodes

    categoryNodes.push({
      id: `category-${categoryIndex}`,
      title: toDisplayText(categoryRecord.model) || '未分组模块',
      kind: 'model',
      children: testModelNodes,
    })

    return categoryNodes
  }, [])

  if (categoryNodes.length === 0) return null

  return {
    id: 'root',
    title: rootTitle || '功能测试用例生成',
    kind: 'root',
    children: categoryNodes,
  }
}

type CategoryCaseNameNodePath = {
  categoryIndex: number
  dataIndex?: number
  pointIndex?: number
}

function parseCategoryCaseNameNodePath(nodeId: string): CategoryCaseNameNodePath | null {
  const match = /^category-(\d+)(?:-data-(\d+))?(?:-point-(\d+))?$/.exec(nodeId)
  if (!match) return null

  return {
    categoryIndex: Number(match[1]),
    dataIndex: match[2] === undefined ? undefined : Number(match[2]),
    pointIndex: match[3] === undefined ? undefined : Number(match[3]),
  }
}

function updateCaseNamePointTitle(point: unknown, nextTitle: string) {
  const pointRecord = toRecord(point)
  if (!pointRecord) return nextTitle
  if ('case_name' in pointRecord) return { ...pointRecord, case_name: nextTitle }
  if ('name' in pointRecord) return { ...pointRecord, name: nextTitle }
  if ('title' in pointRecord) return { ...pointRecord, title: nextTitle }
  if ('test_point' in pointRecord) return { ...pointRecord, test_point: nextTitle }
  return { ...pointRecord, case_name: nextTitle }
}

function updateCategoryCaseNamesContent(content: string, nodeId: string, action: 'rename' | 'delete', nextTitle?: string) {
  let parsed: unknown
  try {
    parsed = JSON.parse(content)
  } catch {
    return null
  }

  const rootRecord = toRecord(parsed)
  const path = parseCategoryCaseNameNodePath(nodeId)
  if (!rootRecord || !path || !Array.isArray(rootRecord.categories)) return null

  const categories = [...rootRecord.categories]
  const categoryRecord = toRecord(categories[path.categoryIndex])
  if (!categoryRecord) return null

  if (path.dataIndex === undefined) {
    if (action === 'delete') {
      categories.splice(path.categoryIndex, 1)
    } else if (nextTitle) {
      categories[path.categoryIndex] = { ...categoryRecord, model: nextTitle }
    }
    return JSON.stringify({ ...rootRecord, categories }, null, 2)
  }

  const data = categoryRecord.data
  if (!Array.isArray(data)) return null
  const nextData = [...data]
  const itemRecord = toRecord(nextData[path.dataIndex])
  if (!itemRecord) return null

  if (path.pointIndex === undefined) {
    if (action === 'delete') {
      nextData.splice(path.dataIndex, 1)
      if (nextData.length === 0) {
        categories.splice(path.categoryIndex, 1)
      } else {
        categories[path.categoryIndex] = { ...categoryRecord, data: nextData }
      }
    } else if (nextTitle) {
      nextData[path.dataIndex] = { ...itemRecord, test_model: nextTitle }
      categories[path.categoryIndex] = { ...categoryRecord, data: nextData }
    }
    return JSON.stringify({ ...rootRecord, categories }, null, 2)
  }

  const points = itemRecord.test_points
  if (!Array.isArray(points)) return null
  const nextPoints = [...points]

  if (action === 'delete') {
    nextPoints.splice(path.pointIndex, 1)
    if (nextPoints.length === 0) {
      nextData.splice(path.dataIndex, 1)
    } else {
      nextData[path.dataIndex] = { ...itemRecord, test_points: nextPoints }
    }

    if (nextData.length === 0) {
      categories.splice(path.categoryIndex, 1)
    } else {
      categories[path.categoryIndex] = { ...categoryRecord, data: nextData }
    }
  } else if (nextTitle) {
    nextPoints[path.pointIndex] = updateCaseNamePointTitle(nextPoints[path.pointIndex], nextTitle)
    nextData[path.dataIndex] = { ...itemRecord, test_points: nextPoints }
    categories[path.categoryIndex] = { ...categoryRecord, data: nextData }
  }

  return JSON.stringify({ ...rootRecord, categories }, null, 2)
}

function buildCaseNameTree(content: string, rootTitle: string): CaseNameTreeNode | null {
  if (!content.trim()) return null

  try {
    const parsed = JSON.parse(content)
    const categoryTree = buildCategoryCaseNameTree(parsed, rootTitle)
    if (categoryTree) return categoryTree

    const rows = parseCaseNameRows(parsed)
    if (rows.length === 0) return null

    const modelMap = new Map<string, Map<string, string[]>>()
    rows.forEach((row) => {
      const model = row.model || '未分组模块'
      const testModel = row.testModel || '未分组场景'
      const testModelMap = modelMap.get(model) ?? new Map<string, string[]>()
      const points = testModelMap.get(testModel) ?? []
      row.testPoints.forEach((point) => {
        if (point && !points.includes(point)) points.push(point)
      })
      testModelMap.set(testModel, points)
      modelMap.set(model, testModelMap)
    })

    return {
      id: 'root',
      title: rootTitle || '功能测试用例生成',
      kind: 'root',
      children: [...modelMap.entries()].map(([model, testModelMap], modelIndex) => ({
        id: `model-${modelIndex}`,
        title: model,
        kind: 'model',
        children: [...testModelMap.entries()].map(([testModel, testPoints], testModelIndex) => ({
          id: `model-${modelIndex}-test-${testModelIndex}`,
          title: testModel,
          kind: 'testModel',
          children: testPoints.map((point, pointIndex) => ({
            id: `model-${modelIndex}-test-${testModelIndex}-point-${pointIndex}`,
            title: point,
            kind: 'point',
            children: [],
          })),
        })),
      })),
    }
  } catch {
    return null
  }
}

function renameCaseNameTreeNode(tree: CaseNameTreeNode, nodeId: string, nextTitle: string): CaseNameTreeNode {
  if (tree.id === nodeId) {
    return { ...tree, title: nextTitle }
  }

  return {
    ...tree,
    children: tree.children.map((child) => renameCaseNameTreeNode(child, nodeId, nextTitle)),
  }
}

function pruneEmptyCaseNameTreeNode(node: CaseNameTreeNode): CaseNameTreeNode | null {
  if (node.kind === 'point') return node

  const children = node.children
    .map(pruneEmptyCaseNameTreeNode)
    .filter((child): child is CaseNameTreeNode => Boolean(child))

  if (node.kind !== 'root' && children.length === 0) return null
  return { ...node, children }
}

function deleteCaseNameTreeNode(tree: CaseNameTreeNode, nodeId: string): CaseNameTreeNode {
  if (tree.id === nodeId) return tree

  const nextTree = {
    ...tree,
    children: tree.children
      .filter((child) => child.id !== nodeId)
      .map((child) => deleteCaseNameTreeNode(child, nodeId)),
  }

  return pruneEmptyCaseNameTreeNode(nextTree) ?? { ...tree, children: [] }
}

function serializeCaseNameTree(tree: CaseNameTreeNode) {
  const rows = tree.children.flatMap((model) =>
    model.children.map((testModel) => ({
      model: model.title,
      test_model: testModel.title,
      test_points: testModel.children.map((point) => point.title),
    })),
  )

  return JSON.stringify(rows, null, 2)
}

function countCaseNameTree(tree: CaseNameTreeNode | null) {
  const models = tree?.children.length ?? 0
  const testModels = tree?.children.reduce((sum, model) => sum + model.children.length, 0) ?? 0
  const testPoints = tree?.children.reduce((sum, model) => sum + model.children.reduce((itemSum, testModel) => itemSum + testModel.children.length, 0), 0) ?? 0
  return { models, testModels, testPoints }
}

const CASE_NAME_TREE_NODE_HEIGHT = 38
const CASE_NAME_TREE_ROW_GAP = 14
const CASE_NAME_TREE_POINT_GAP = 10
const CASE_NAME_TREE_CONNECTOR_WIDTH = 86

function getStackHeight(count: number, gap = CASE_NAME_TREE_ROW_GAP) {
  if (count <= 0) return CASE_NAME_TREE_NODE_HEIGHT
  return count * CASE_NAME_TREE_NODE_HEIGHT + (count - 1) * gap
}

function getTestModelHeight(testModel: CaseNameTreeNode) {
  return getStackHeight(testModel.children.length, CASE_NAME_TREE_POINT_GAP)
}

function getModelHeight(model: CaseNameTreeNode) {
  if (model.children.length === 0) return CASE_NAME_TREE_NODE_HEIGHT
  return model.children.reduce((sum, testModel, index) => (
    sum + getTestModelHeight(testModel) + (index === 0 ? 0 : CASE_NAME_TREE_ROW_GAP)
  ), 0)
}

function getTreeHeight(tree: CaseNameTreeNode) {
  if (tree.children.length === 0) return CASE_NAME_TREE_NODE_HEIGHT
  return tree.children.reduce((sum, model, index) => (
    sum + getModelHeight(model) + (index === 0 ? 0 : CASE_NAME_TREE_ROW_GAP)
  ), 0)
}

function getModelTargetYs(tree: CaseNameTreeNode) {
  let cursor = 0
  return tree.children.map((model) => {
    const height = getModelHeight(model)
    const y = cursor + height / 2
    cursor += height + CASE_NAME_TREE_ROW_GAP
    return y
  })
}

function getTestModelTargetYs(model: CaseNameTreeNode) {
  let cursor = 0
  return model.children.map((testModel) => {
    const height = getTestModelHeight(testModel)
    const y = cursor + height / 2
    cursor += height + CASE_NAME_TREE_ROW_GAP
    return y
  })
}

function getPointTargetYs(testModel: CaseNameTreeNode) {
  return testModel.children.map((_, index) => (
    CASE_NAME_TREE_NODE_HEIGHT / 2 + index * (CASE_NAME_TREE_NODE_HEIGHT + CASE_NAME_TREE_POINT_GAP)
  ))
}

const CURVE_STROKE_META = {
  green: { color: 'rgba(124, 195, 163, 0.68)', width: 2 },
  blue: { color: 'rgba(70, 166, 210, 0.58)', width: 2 },
  slate: { color: 'rgba(100, 116, 139, 0.46)', width: 1.8 },
} as const

const CURVE_STROKE_META_DARK = {
  green: { color: 'rgba(124, 195, 163, 0.72)', width: 2 },
  blue: { color: 'rgba(96, 165, 250, 0.68)', width: 2 },
  slate: { color: 'rgba(148, 163, 184, 0.58)', width: 1.8 },
} as const

function CaseNameTreeCurves({ height, targetYs, layoutKey, tone = 'green' }: { height: number; targetYs: number[]; layoutKey: string; tone?: 'green' | 'blue' | 'slate' }) {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [layout, setLayout] = useState<{ height: number; targetYs: number[] } | null>(null)
  const targetKey = targetYs.join(',')

  useLayoutEffect(() => {
    const svg = svgRef.current
    const source = svg?.previousElementSibling
    const targets = svg?.nextElementSibling
    if (!source || !targets) return

    // 换行后的节点高度各不相同，连接线使用实际布局中的节点中心。
    const measure = () => {
      const bounds = targets.getBoundingClientRect()
      if (!bounds.height) return
      const measuredHeight = Math.max(bounds.height, source.getBoundingClientRect().height)
      const next = {
        height: measuredHeight,
        targetYs: Array.from(targets.children, (child) => {
          const rect = child.getBoundingClientRect()
          return rect.top - bounds.top + rect.height / 2 + (measuredHeight - bounds.height) / 2
        }),
      }
      setLayout((current) => current?.height === next.height
        && current.targetYs.length === next.targetYs.length
        && current.targetYs.every((y, index) => y === next.targetYs[index]) ? current : next)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(source)
    observer.observe(targets)
    Array.from(targets.children).forEach((child) => observer.observe(child))
    return () => observer.disconnect()
  }, [height, targetKey, layoutKey])

  const safeHeight = Math.max(layout?.height ?? height, CASE_NAME_TREE_NODE_HEIGHT)
  const sourceY = safeHeight / 2
  const width = CASE_NAME_TREE_CONNECTOR_WIDTH
  const themeMode = useThemeStore((state) => state.mode)
  // 描边同时写成 presentation attributes，保证 html-to-image 导出图片时曲线样式不丢失
  const stroke = (themeMode === 'dark' ? CURVE_STROKE_META_DARK : CURVE_STROKE_META)[tone]

  return (
    <svg
      ref={svgRef}
      className={`ai-case-name-tree-curves ${tone}`}
      width={width}
      height={safeHeight}
      viewBox={`0 0 ${width} ${safeHeight}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {(layout?.targetYs ?? targetYs).map((targetY, index) => {
        const controlOffset = Math.min(42, Math.max(24, Math.abs(targetY - sourceY) * 0.42 + 18))
        const d = `M 2 ${sourceY} C ${controlOffset} ${sourceY}, ${width - controlOffset} ${targetY}, ${width - 2} ${targetY}`
        return (
          <path
            key={`${targetY}-${index}`}
            d={d}
            fill="none"
            stroke={stroke.color}
            strokeWidth={stroke.width}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        )
      })}
    </svg>
  )
}

function CaseNameTreeNodeView({
  node,
  className,
  editable,
  onRename,
  onDelete,
}: {
  node: CaseNameTreeNode
  className: string
  editable?: boolean
  onRename?: (nodeId: string, title: string) => void
  onDelete?: (nodeId: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState(node.title)
  const canEdit = Boolean(editable && node.kind !== 'root')

  useEffect(() => {
    setDraftTitle(node.title)
  }, [node.title])

  function commitEdit() {
    const nextTitle = draftTitle.trim()
    if (!nextTitle) {
      message.warning('节点名称不能为空')
      setDraftTitle(node.title)
      setEditing(false)
      return
    }

    if (nextTitle !== node.title) {
      onRename?.(node.id, nextTitle)
    }
    setEditing(false)
  }

  return (
    <div className={`${className}${canEdit ? ' editable' : ''}`} title={node.title}>
      {editing ? (
        <Input
          className="ai-case-name-tree-node-input"
          size="small"
          value={draftTitle}
          autoFocus
          onChange={(event) => setDraftTitle(event.target.value)}
          onBlur={commitEdit}
          onPressEnter={commitEdit}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setDraftTitle(node.title)
              setEditing(false)
            }
          }}
        />
      ) : (
        <span className="ai-case-name-tree-node-label">{node.title}</span>
      )}
      {canEdit && !editing ? (
        <span className="ai-case-name-tree-node-actions">
          <ProjectActionButton action="write"
            type="text"
            size="small"
            operation="edit" iconOnly
            aria-label="编辑节点"
            onClick={(event) => {
              event.stopPropagation()
              setEditing(true)
            }}
          />
          <Popconfirm
            title="确认删除该节点？"
            onConfirm={() => onDelete?.(node.id)}
          >
            <ProjectActionButton action="write"
              danger
              type="text"
              size="small"
              operation="delete" iconOnly
              aria-label="删除节点"
              onClick={(event) => event.stopPropagation()}
            />
          </Popconfirm>
        </span>
      ) : null}
    </div>
  )
}

function CaseNameTreeView({
  content,
  rootTitle,
  expanded = false,
  editable = false,
  onTreeChange,
}: {
  content: string
  rootTitle: string
  expanded?: boolean
  editable?: boolean
  onTreeChange?: (content: string) => void
}) {
  const tree = buildCaseNameTree(content, rootTitle)
  const counts = countCaseNameTree(tree)
  const themeMode = useThemeStore((state) => state.mode)
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const [exportingImage, setExportingImage] = useState(false)

  async function handleSaveTreeImage() {
    const canvas = canvasRef.current
    if (!canvas) return
    setExportingImage(true)
    try {
      // 页面上的树卡片带有边框、圆角和渐变背景，导出时在克隆节点上补齐，保证图片与页面显示一致
      const cardVisualStyle =
        themeMode === 'dark'
          ? {
              background: 'radial-gradient(circle at 24px 24px, rgba(124, 195, 163, 0.08), transparent 28px), #1b202b',
              border: '1px solid rgba(148, 163, 184, 0.18)',
              borderRadius: '14px',
            }
          : {
              background: 'radial-gradient(circle at 24px 24px, rgba(124, 195, 163, 0.08), transparent 26px), #ffffff',
              border: '1px solid rgba(148, 163, 184, 0.14)',
              borderRadius: '14px',
            }
      const blob = await toBlob(canvas, {
        pixelRatio: 2,
        skipFonts: true,
        style: cardVisualStyle,
      })
      if (!blob) throw new Error('导出内容为空')
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${rootTitle}-测试点树图.png`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      message.success('图片已保存')
    } catch {
      message.error('图片导出失败，请重试')
    } finally {
      setExportingImage(false)
    }
  }

  if (!tree) {
    return <JsonEditor value={content} readOnly foldable minHeight={expanded ? 560 : 260} />
  }

  const treeHeight = getTreeHeight(tree)
  const handleRename = (nodeId: string, title: string) => {
    onTreeChange?.(updateCategoryCaseNamesContent(content, nodeId, 'rename', title) ?? serializeCaseNameTree(renameCaseNameTreeNode(tree, nodeId, title)))
  }
  const handleDelete = (nodeId: string) => {
    onTreeChange?.(updateCategoryCaseNamesContent(content, nodeId, 'delete') ?? serializeCaseNameTree(deleteCaseNameTreeNode(tree, nodeId)))
  }

  return (
    <div className={`ai-case-name-tree${expanded ? ' expanded' : ''}${editable ? ' editable' : ''}`}>
      <div className="ai-case-name-tree-stats">
        <Tag color="green">model {counts.models}</Tag>
        <Tag color="cyan">test_model {counts.testModels}</Tag>
        <Tag color="blue">test_points {counts.testPoints}</Tag>
        <ProjectActionButton action="write"
          className="ai-case-name-tree-export"
          size="small"
          icon={<PictureOutlined />}
          loading={exportingImage}
          onClick={handleSaveTreeImage}
        >
          保存图片
        </ProjectActionButton>
      </div>
      <div className="ai-case-name-tree-canvas" ref={canvasRef}>
        <CaseNameTreeNodeView
          node={tree}
          className="ai-case-name-tree-root"
          editable={editable}
          onRename={handleRename}
          onDelete={handleDelete}
        />
        <CaseNameTreeCurves layoutKey={content} height={treeHeight} targetYs={getModelTargetYs(tree)} tone="green" />
        <div className="ai-case-name-tree-branches">
          {tree.children.map((model) => (
            <div key={model.id} className="ai-case-name-tree-row">
              <CaseNameTreeNodeView
                node={model}
                className="ai-case-name-tree-node model"
                editable={editable}
                onRename={handleRename}
                onDelete={handleDelete}
              />
              <CaseNameTreeCurves layoutKey={content} height={getModelHeight(model)} targetYs={getTestModelTargetYs(model)} tone="blue" />
              <div className="ai-case-name-tree-children">
                {model.children.map((testModel) => (
                  <div key={testModel.id} className="ai-case-name-tree-row nested">
                    <CaseNameTreeNodeView
                      node={testModel}
                      className="ai-case-name-tree-node test-model"
                      editable={editable}
                      onRename={handleRename}
                      onDelete={handleDelete}
                    />
                    <CaseNameTreeCurves layoutKey={content} height={getTestModelHeight(testModel)} targetYs={getPointTargetYs(testModel)} tone="slate" />
                    <div className="ai-case-name-tree-children point-list">
                      {testModel.children.map((point) => (
                        <CaseNameTreeNodeView
                          key={point.id}
                          node={point}
                          className="ai-case-name-tree-node point"
                          editable={editable}
                          onRename={handleRename}
                          onDelete={handleDelete}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function CaseNamesResultView({
  content,
  rootTitle,
  expanded = false,
  activeView,
  onViewChange,
}: {
  content: string
  rootTitle: string
  expanded?: boolean
  activeView?: CaseNamesViewMode
  onViewChange?: (view: CaseNamesViewMode) => void
}) {
  return (
    <Tabs
      className={`ai-case-names-inner-tabs${expanded ? ' expanded' : ''}`}
      size="small"
      activeKey={activeView}
      onChange={(key) => onViewChange?.(key as CaseNamesViewMode)}
      items={[
        {
          key: 'tree',
          label: '可视化',
          children: <CaseNameTreeView content={content} rootTitle={rootTitle} expanded={expanded} />,
        },
        {
          key: 'json',
          label: 'json',
          children: isJsonText(content) ? (
            <JsonEditor value={content} readOnly foldable minHeight={expanded ? 520 : 240} />
          ) : (
            <pre className="ai-task-code-block">{content}</pre>
          ),
        },
      ]}
    />
  )
}

function getRunOperationErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 403) {
    return error.message ? `无权限执行当前操作：${error.message}` : '无权限执行当前操作'
  }
  return getErrorMessage(error)
}

function normalizeReviewStatus(status?: string) {
  return status ?? 'unknown'
}

function getFunctionalStageMeta(stage?: string) {
  if (!stage) return { label: '未开始', color: 'default' }
  return functionalStageMetaMap[stage] ?? { label: stage, color: 'default' }
}

function getStageConfigField(stage?: string) {
  return stage ? stageConfigFieldMap[stage] : undefined
}

const runStageFilterOptions: Array<{ label: string; value: 'all' | RunPipelineFilterKey }> = [
  { label: '全部状态', value: 'all' },
  { label: '待审核', value: 'review_pending' },
  { label: '待导入', value: 'import_pending' },
  { label: '已导入', value: 'imported' },
  { label: '已拒绝', value: 'rejected' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'canceled' },
  { label: '执行中', value: 'running' },
]

const runArtifactDefinitions = [
  { key: 'requirementAnalysis', label: '需求分析' },
  { key: 'caseNames', label: '测试点' },
  { key: 'caseRelations', label: '图谱分析' },
] as const

function getRunRecordArtifacts(configJson: unknown) {
  return runArtifactDefinitions.map((definition) => ({
    ...definition,
    available: Boolean(getConfigStageFieldContent(configJson, definition.key)),
  }))
}

export function FunctionalCaseGenerateTaskDetailPage() {
  const { taskId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerSprintId, setDrawerSprintId] = useState<string | undefined>(undefined)
  const [llmSelectOpen, setLlmSelectOpen] = useState(false)
  const [expandedSection, setExpandedSection] = useState<'instruction' | 'document' | 'runHistory' | null>('runHistory')
  const [selectedRunRecordId, setSelectedRunRecordId] = useState<string | null>(null)
  const [runStageFilter, setRunStageFilter] = useState<'all' | RunPipelineFilterKey>('all')
  const [runResultModal, setRunResultModal] = useState<RunResultModalState>(null)
  const [resultModalRunId, setResultModalRunId] = useState<string | null>(null)
  const [reviewSubmitAction, setReviewSubmitAction] = useState<'approve' | 'reject' | null>(null)
  const [reviewComment, setReviewComment] = useState('')
  const [candidateModalView, setCandidateModalView] = useState<'preview' | 'edit'>('preview')
  const [candidateYaml, setCandidateYaml] = useState('')
  const [revisionTarget, setRevisionTarget] = useState<'stage' | 'final' | null>(null)
  const [revisionFooter, setRevisionFooter] = useState<HTMLDivElement | null>(null)
  const [revisionInstruction, setRevisionInstruction] = useState('')
  const [revisionDraftKey, setRevisionDraftKey] = useState('')
  const [revisionTemplate, setRevisionTemplate] = useState('')
  const [importConfirmRunId, setImportConfirmRunId] = useState<string | null>(null)
  const [importAcknowledged, setImportAcknowledged] = useState(false)
  const [importConflict, setImportConflict] = useState<{
    runId: string
    conflicts: FunctionalCaseGenerateTaskRunImportConflict[]
  } | null>(null)
  const [checkpointEnabled, setCheckpointEnabled] = useState(false)
  const [stageOutputDraft, setStageOutputDraft] = useState('')
  const [stageOutputDirty, setStageOutputDirty] = useState(false)
  const [stageOutputSourceKey, setStageOutputSourceKey] = useState('')
  const [stageReviewComment, setStageReviewComment] = useState('')
  const [stageReviewAction, setStageReviewAction] = useState<'approve' | 'reject' | null>(null)
  const [runResultCaseNamesView, setRunResultCaseNamesView] = useState<CaseNamesViewMode>('tree')
  const [stageRequirementAnalysisView, setStageRequirementAnalysisView] = useState<RequirementAnalysisViewMode>('diagram')
  const [form] = Form.useForm<FunctionalCaseGenerateTaskFormValues>()

  const taskQuery = useQuery({
    queryKey: ['functionalCaseGenerateTask', taskId],
    queryFn: () => api.getFunctionalCaseGenerateTask(taskId),
    enabled: Boolean(taskId),
  })

  const task = taskQuery.data
  const { can } = useProjectAccess(task?.projectId ?? '')
  const personalLlm = usePersonalLlmChoice(task?.projectId)
  const taskRequirementQuery = useQuery({
    queryKey: ['requirement', task?.requirementId],
    queryFn: () => api.getRequirement(task!.requirementId!),
    enabled: Boolean(task?.requirementId),
  })
  const runsQuery = useQuery({
    queryKey: ['functionalCaseGenerateTaskRuns', taskId],
    queryFn: () => api.getFunctionalCaseGenerateTaskRuns(taskId),
    enabled: Boolean(taskId),
    refetchInterval: expandedSection === 'runHistory' ? 5000 : false,
  })
  const sprintsQuery = useQuery({
    queryKey: ['sprints', 'functionalAiTestingDetail', task?.projectId],
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
    queryKey: ['requirements', 'functionalAiTestingDetail', drawerSprintId],
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
  const filteredRunRecords = useMemo(
    () =>
      runStageFilter === 'all'
        ? runRecords
        : runRecords.filter((record) => getRunPipelineModel(record).filterKey === runStageFilter),
    [runRecords, runStageFilter],
  )
  const selectedRunId = selectedRunRecordId ?? runRecords[0]?.runId ?? ''
  const selectedRunQuery = useQuery({
    queryKey: ['functionalCaseGenerateTaskRun', selectedRunId],
    queryFn: () => api.getFunctionalCaseGenerateTaskRun(selectedRunId),
    enabled: Boolean(selectedRunId),
    refetchInterval: expandedSection === 'runHistory' && selectedRunId ? 5000 : false,
  })
  const selectedRun = selectedRunQuery.data
  const importDetailsReady = Boolean(importConfirmRunId && selectedRun?.runId === importConfirmRunId && selectedRunQuery.isSuccess)
  const selectedStage = selectedRun?.currentStage
  const selectedStageField = getStageConfigField(selectedStage)
  const selectedStageOutputContent = useMemo(
    () =>
      formatStructuredContent(selectedRun?.stageOutput) ||
      getConfigStageFieldContent(selectedRun?.configJson, selectedStageField?.key),
    [selectedRun?.configJson, selectedRun?.stageOutput, selectedStageField?.key],
  )
  const selectedRunResultSections = useMemo(
    () =>
      selectedRun
        ? runResultSectionDefinitions
            .map((section) => {
              const rawValue =
                section.key === 'enhancedText' ||
                section.key === 'requirementAnalysis' ||
                section.key === 'caseNames' ||
                section.key === 'caseRelations'
                  ? getConfigStageFieldContent(selectedRun.configJson, section.key)
                  : selectedRun[section.key as keyof FunctionalCaseGenerateTaskRun]
              return { ...section, value: formatStructuredContent(rawValue) }
            })
            .filter((item) => item.value)
        : [],
    [selectedRun],
  )

  useEffect(() => {
    if (!task) return
    setDrawerSprintId(task.sprintId)
    form.setFieldsValue({
      name: task.name,
      sprintId: task.sprintId,
      requirementId: task.requirementId,
      instruction: task.instruction,
    })
  }, [form, task])

  useEffect(() => {
    setExpandedSection('runHistory')
  }, [taskId])

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
    if (runResultModal?.key !== 'caseNames') {
      setRunResultCaseNamesView('tree')
    }
    if (runResultModal?.key !== selectedStageField?.key) {
      setStageRequirementAnalysisView('diagram')
    }
  }, [runResultModal?.key, selectedStageField?.key])

  const updateTaskMutation = useMutation({
    mutationFn: (values: FunctionalCaseGenerateTaskFormValues) => api.updateFunctionalCaseGenerateTask(taskId, values),
    onSuccess: (updatedTask) => {
      message.success('任务已更新')
      setDrawerOpen(false)
      queryClient.setQueryData(['functionalCaseGenerateTask', taskId], updatedTask)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTasks', updatedTask.projectId] })
    },
  })

  const runTaskMutation = useMutation({
    mutationFn: ({ connectionId, checkpointEnabled }: { connectionId: string; checkpointEnabled?: boolean }) =>
      api.runFunctionalCaseGenerateTask(taskId, { connectionId, checkpointEnabled }),
    onSuccess: (run) => {
      message.success('任务已加入执行队列')
      setLlmSelectOpen(false)
      setCheckpointEnabled(false)
      setExpandedSection('runHistory')
      setSelectedRunRecordId(run.runId ?? null)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTask', taskId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTasks', task?.projectId ?? run.projectId] })
    },
  })

  const reviewRunMutation = useMutation({
    mutationFn: (payload: {
      runId: string
      body: { action: 'approve'; reviewComment?: string } | { action: 'reject'; reviewComment?: string }
    }) => api.reviewFunctionalCaseGenerateTaskRun(payload.runId, payload.body),
    onSuccess: (updatedRun, payload) => {
      message.success(payload.body.action === 'approve' ? '候选结果审核通过' : '候选结果审核已拒绝')
      setResultModalRunId(null)
      setReviewSubmitAction(null)
      setSelectedRunRecordId(updatedRun.runId ?? payload.runId)
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getRunOperationErrorMessage(error))
      if (resultModalRunId) {
        queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', resultModalRunId] })
      }
    },
  })

  const updateRunResultMutation = useMutation({
    mutationFn: (payload: { runId: string; resultYaml: string }) =>
      api.updateFunctionalCaseGenerateTaskRunResult(payload.runId, { resultYaml: payload.resultYaml }),
    onSuccess: (updatedRun, payload) => {
      message.success('候选结果已保存')
      setCandidateYaml(formatStructuredContent(updatedRun.resultYaml ?? payload.resultYaml))
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error, payload) => {
      message.error(getRunOperationErrorMessage(error))
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
    },
  })

  const importRunMutation = useMutation({
    mutationFn: (payload: { runId: string; confirmOverwrite: boolean }) =>
      api.importFunctionalCaseGenerateTaskRun(payload.runId, {
        confirmOverwrite: payload.confirmOverwrite,
      }),
    onSuccess: (result, payload) => {
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], result.run)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })

      if (result.requiresConfirmation) {
        setImportConflict({ runId: payload.runId, conflicts: result.conflicts })
        return
      }

      setImportConflict(null)
      message.success('正式功能用例导入成功')
      const targetRequirementId = task?.requirementId ?? result.run.requirementId
      if (targetRequirementId) {
        queryClient.invalidateQueries({ queryKey: ['functionTestSuites', targetRequirementId] })
      }
      queryClient.invalidateQueries({ queryKey: ['functionTestSuites'] })
      queryClient.invalidateQueries({ queryKey: ['functionTestCases'] })
    },
    onError: (error, payload) => {
      message.error(getRunOperationErrorMessage(error))
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
  })

  const generateRelationMutation = useMutation({
    mutationFn: (payload: { runId: string }) =>
      api.generateFunctionalCaseRelationAnalysis(payload.runId),
    onSuccess: (updatedRun) => {
      message.success('图谱生成任务已提交，完成后可在运行记录查看')
      setSelectedRunRecordId(updatedRun.runId ?? null)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', updatedRun.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getRunOperationErrorMessage(error))
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
  })

  const saveStageOutputMutation = useMutation({
    mutationFn: (payload: { runId: string; stage: string; configJson: string; silent?: boolean }) => {
      const field = getStageConfigField(payload.stage)
      if (field?.key !== 'requirementAnalysis' && field?.key !== 'caseNames') {
        return api.updateFunctionalCaseGenerateTaskRunStageOutput(payload.runId, {
          stage: payload.stage,
          configJson: payload.configJson,
        })
      }
      let parsed: unknown
      try {
        parsed = JSON.parse(payload.configJson)
      } catch {
        throw new Error('阶段产物必须是有效的 JSON 对象')
      }
      if (!field || !parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('阶段产物必须是有效的 JSON 对象')
      }
      const record = parsed as Record<string, unknown>
      return api.updateFunctionalCaseGenerateTaskRunStageOutput(payload.runId, {
        stage: payload.stage,
        configJson: JSON.stringify({ [field.key]: record[field.key] ?? record }),
      })
    },
    onSuccess: (updatedRun, payload) => {
      if (!payload.silent) {
        message.success('阶段产物已保存')
      }
      setStageOutputDirty(false)
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const reviewStageMutation = useMutation({
    mutationFn: async (payload: {
      runId: string
      body: { stage: string; action: 'approve'; comment?: string } | { stage: string; action: 'reject'; comment?: string }
    }) => api.reviewFunctionalCaseGenerateTaskRunStage(payload.runId, { ...payload.body, llmConnectionId: payload.body.action === 'approve' ? await personalLlm.choose() : undefined }),
    onSuccess: (updatedRun, payload) => {
      message.success(payload.body.action === 'approve' ? '阶段审核已通过，继续生成' : '已拒绝并停止继续生成')
      setStageReviewAction(null)
      setStageReviewComment('')
      setSelectedRunRecordId(updatedRun.runId ?? payload.runId)
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
      setStageReviewAction(null)
    },
  })

  const reviseStageMutation = useMutation({
    mutationFn: async (payload: { runId: string; body: { llmConnectionId: string; stage: string; revisionInstruction: string; configJson?: Record<string, unknown>; resultYaml?: string } }) =>
      api.reviseFunctionalCaseGenerateTaskRunStage(payload.runId, payload.body),
    onSuccess: (updatedRun, payload) => {
      message.success('已提交优化，等待重新生成')
      setRevisionTarget(null)
      setRevisionInstruction('')
      setRevisionDraftKey('')
      setRunResultModal(null)
      setResultModalRunId(null)
      setStageOutputDirty(false)
      setExpandedSection('runHistory')
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const retryStageMutation = useMutation({
    mutationFn: async (payload: { runId: string; stage: string }) =>
      api.retryFunctionalCaseGenerateTaskRunStage(payload.runId, { stage: payload.stage, llmConnectionId: await personalLlm.choose() }),
    onSuccess: (updatedRun, payload) => {
      message.success('已提交阶段重试，等待重新执行')
      setSelectedRunRecordId(updatedRun.runId ?? payload.runId)
      queryClient.setQueryData(['functionalCaseGenerateTaskRun', payload.runId], updatedRun)
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', payload.runId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRuns', taskId] })
      queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTask', taskId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const deleteTaskMutation = useMutation({
    mutationFn: () => api.deleteFunctionalCaseGenerateTask(taskId),
    onSuccess: () => {
      message.success('任务已删除')
      queryClient.removeQueries({ queryKey: ['functionalCaseGenerateTask', taskId], exact: true })
      if (task?.projectId) {
        queryClient.invalidateQueries({ queryKey: ['functionalCaseGenerateTasks', task.projectId] })
      }
      navigate('/ai-testing?tab=tasks')
    },
  })

  const runnableTask = isRunnableApiCaseGenerateTaskRun(latestRunRecord?.status)
  const detailItems = useMemo(
    () =>
      task
        ? [
            { label: '任务名称', value: task.name || '-' },
            { label: '迭代', value: sprintNameMap.get(task.sprintId ?? '') ?? task.sprintId ?? '-' },
            {
              label: '需求',
              value:
                taskRequirementQuery.data?.name ??
                requirementNameMap.get(task.requirementId ?? '') ??
                task.requirementId ??
                '-',
            },
            { label: '更新时间', value: formatTime(pickUpdatedAt(task)) },
          ]
        : [],
    [requirementNameMap, sprintNameMap, task, taskRequirementQuery.data?.name],
  )
  const selectedRunResultSectionMap = useMemo(
    () => new Map(selectedRunResultSections.map((section) => [section.key, section.value])),
    [selectedRunResultSections],
  )
  const runResultModalContent = runResultModal ? selectedRunResultSectionMap.get(runResultModal.key) : undefined
  const selectedRunImportStats = useMemo(
    () => getGeneratedCaseImportStats(selectedRun?.resultYaml),
    [selectedRun?.resultYaml],
  )
  const importTargetRequirementName = task?.requirementId
    ? taskRequirementQuery.data?.name ?? requirementNameMap.get(task.requirementId) ?? task.requirementId
    : selectedRun?.requirementId
      ? requirementNameMap.get(selectedRun.requirementId) ?? selectedRun.requirementId
      : '-'
  const runHistoryRefreshing = runsQuery.isFetching || selectedRunQuery.isFetching
  const resultModalOpen = Boolean(resultModalRunId)
  const selectedRunReviewStatus = normalizeReviewStatus(selectedRun?.reviewStatus)
  const selectedRunStatus = String(selectedRun?.status ?? '')
  const selectedStageMeta = getFunctionalStageMeta(selectedStage)
  const stageOutputIsCaseNames = selectedStageField?.key === 'caseNames'
  const stageOutputIsRequirementAnalysis = selectedStageField?.key === 'requirementAnalysis'
  const selectedStageStatusMeta = getApiCaseGenerateTaskRunStatusMeta(selectedRun?.stageStatus)
  const canRetryStage = Boolean(
    ['failed', 'retrying'].includes(String(selectedRun?.stageStatus ?? '')) &&
      ['requirement_analysis', 'case_names', 'detailed_cases'].includes(String(selectedStage ?? '')) &&
      selectedRunReviewStatus === 'pending' &&
      selectedRun?.importStatus !== 'imported' &&
      (selectedRunStatus === 'failed' || selectedRunStatus === 'error'),
  )
  const checkpointStageWaitingReview = Boolean(
    selectedRun?.checkpointEnabled &&
      selectedRunStatus === 'waiting_review' &&
      selectedRun?.stageStatus === 'waiting_review' &&
      selectedStage,
  )
  const showStageReviewInRunResultModal = runResultModal?.key === selectedStageField?.key && checkpointStageWaitingReview
  const checkpointStageVisible = Boolean(
    selectedRun?.checkpointEnabled &&
      selectedStage &&
      selectedRunStatus !== 'success' &&
      selectedRunStatus !== 'failed' &&
      selectedRunStatus !== 'error' &&
      selectedRunStatus !== 'canceled',
  )
  const canReviseCheckpoint = showStageReviewInRunResultModal
    && (selectedStage === 'requirement_analysis' || selectedStage === 'case_names')
    && selectedRunReviewStatus === 'pending' && selectedRun?.importStatus !== 'imported'
  const stageActionPending = saveStageOutputMutation.isPending || reviewStageMutation.isPending || reviseStageMutation.isPending
  const reviewAvailable = Boolean(selectedRun) && selectedRunReviewStatus === 'pending' && selectedRunStatus === 'success'
  const canReviewSelectedRun = can('review') && reviewAvailable
  const canReviseFinal = canReviewSelectedRun && selectedRun?.importStatus !== 'imported'
    && (!selectedStage || selectedStage === 'detailed_cases' || selectedStage === 'completed')
  const canEditCandidate = canReviewSelectedRun
  const candidateDirty = candidateYaml !== formatStructuredContent(selectedRun?.resultYaml ?? '')

  useEffect(() => {
    if (!resultModalRunId) {
      setCandidateYaml('')
      setReviewComment('')
      return
    }
    setReviewComment(selectedRun?.reviewComment ?? '')
    setCandidateYaml(formatStructuredContent(selectedRun?.resultYaml ?? ''))
  }, [resultModalRunId, selectedRun?.reviewComment, selectedRun?.resultYaml])

  useEffect(() => {
    const nextSourceKey = `${selectedRun?.runId ?? ''}:${selectedRun?.currentStage ?? ''}`

    if (stageOutputSourceKey !== nextSourceKey) {
      setStageOutputSourceKey(nextSourceKey)
      setStageOutputDraft(selectedStageOutputContent)
      setStageOutputDirty(false)
      setStageRequirementAnalysisView('diagram')
      setStageReviewComment('')
      setStageReviewAction(null)
      return
    }

    if (!stageOutputDirty) {
      setStageOutputDraft(selectedStageOutputContent)
    }
  }, [
    selectedRun?.currentStage,
    selectedRun?.runId,
    selectedStageOutputContent,
    stageOutputDirty,
    stageOutputSourceKey,
  ])

  async function handleRunTask() {
    if (runsQuery.isLoading) {
      message.warning('运行记录加载中，请稍后再试')
      return
    }
    if (!runnableTask) {
      message.warning('任务执行中，暂时不能重复运行')
      return
    }

    let requirement = taskRequirementQuery.data
    if (!requirement && task?.requirementId) {
      try {
        requirement = await queryClient.fetchQuery({
          queryKey: ['requirement', task.requirementId],
          queryFn: () => api.getRequirement(task.requirementId!),
        })
      } catch (error) {
        message.error(getErrorMessage(error))
        return
      }
    }

    if (!hasRequirementEnhancedText(requirement)) {
      message.warning('请先完成需求分析并导入增强文本，再生成功能用例')
      return
    }

    setLlmSelectOpen(true)
  }

  function handleLlmSelectConfirm(connectionId: string) {
    runTaskMutation.mutate({ connectionId, checkpointEnabled })
  }

  function handleRefreshRuns() {
    void runsQuery.refetch()
    if (selectedRunId) {
      void selectedRunQuery.refetch()
    }
  }

  function openRevisionModal(target: 'stage' | 'final') {
    if (!selectedRun?.runId) return
    const stage = target === 'final' ? 'detailed_cases' : selectedStage
    const label = stage === 'detailed_cases' ? '详细测试用例' : stage === 'case_names' ? '测试点' : '需求分析'
    const key = `${selectedRun.runId}:${stage}`
    // Initialize once per run/stage; closing, retrying and polling must preserve the draft.
    if (key !== revisionDraftKey) {
      const questions = stage === 'requirement_analysis' ? getRevisionQuestions(stageOutputDraft) : []
      const template = buildRevisionTemplate(questions, label)
      setRevisionTemplate(template)
      setRevisionInstruction(template)
      setRevisionDraftKey(key)
    }
    if (target === 'final') setCandidateModalView('edit')
    setRevisionTarget(target)
  }

  function handleReviseStage(connectionId: string) {
    if (!selectedRun?.runId || reviseStageMutation.isPending) return
    if (!revisionInstruction.trim()) {
      message.warning('请输入优化指令')
      return
    }
    if (revisionTemplate && revisionInstruction.trim() === revisionTemplate.trim()) {
      message.warning('请补充已确认的信息，或填写其他优化要求')
      return
    }
    const final = revisionTarget === 'final'
    if (final ? !canReviseFinal : !canReviseCheckpoint) return
    const content = final ? candidateYaml : stageOutputDraft
    if (!content.trim()) {
      message.warning('当前产物不能为空')
      return
    }
    let configJson: Record<string, unknown> | undefined
    if (!final) {
      try {
        const parsed: unknown = JSON.parse(content)
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || !selectedStageField) throw new Error()
        const record = parsed as Record<string, unknown>
        configJson = { [selectedStageField.key]: record[selectedStageField.key] ?? record }
      } catch {
        message.warning('阶段产物必须是有效的 JSON 对象')
        return
      }
    }
    reviseStageMutation.mutate({
      runId: selectedRun.runId,
      body: {
        stage: final ? 'detailed_cases' : selectedStage!,
        revisionInstruction: revisionInstruction.trim(),
        llmConnectionId: connectionId,
        ...(final ? { resultYaml: content } : { configJson }),
      },
    })
  }

  function handleSaveStageOutput() {
    if (!selectedRun?.runId || !selectedStage) return
    if (!stageOutputDraft.trim()) {
      message.warning('阶段产物不能为空')
      return
    }
    saveStageOutputMutation.mutate({
      runId: selectedRun.runId,
      stage: selectedStage,
      configJson: stageOutputDraft,
    })
  }

  async function handleApproveStageReview() {
    if (!selectedRun?.runId || !selectedStage) return
    if (!stageOutputDraft.trim()) {
      message.warning('阶段产物不能为空')
      return
    }
    setStageReviewAction('approve')
    try {
      await saveStageOutputMutation.mutateAsync({
        runId: selectedRun.runId,
        stage: selectedStage,
        configJson: stageOutputDraft,
        silent: true,
      })
      await reviewStageMutation.mutateAsync({
        runId: selectedRun.runId,
        body: {
          stage: selectedStage,
          action: 'approve',
          comment: stageReviewComment.trim() || undefined,
        },
      })
    } catch {
      setStageReviewAction(null)
    }
  }

  function handleRejectStageReview() {
    if (!selectedRun?.runId || !selectedStage) return
    setStageReviewAction('reject')
    reviewStageMutation.mutate({
      runId: selectedRun.runId,
      body: {
        stage: selectedStage,
        action: 'reject',
        comment: stageReviewComment.trim() || undefined,
      },
    })
  }

  function handleRetryStage() {
    if (!selectedRun?.runId || !selectedStage || !canRetryStage) return
    retryStageMutation.mutate({
      runId: selectedRun.runId,
      stage: selectedStage,
    })
  }

  function openResultModal(runId?: string) {
    if (!runId) return
    setSelectedRunRecordId(runId)
    setResultModalRunId(runId)
    setReviewSubmitAction(null)
    setCandidateModalView('preview')
  }

  function closeResultModal() {
    if (reviseStageMutation.isPending) return
    setRevisionTarget(null)
    if (reviewRunMutation.isPending || updateRunResultMutation.isPending) return
    setResultModalRunId(null)
    setReviewSubmitAction(null)
  }

  function handleApproveReview() {
    if (!resultModalRunId) return
    if (!canReviewSelectedRun) {
      message.warning('当前运行状态不允许批准候选结果')
      return
    }
    setReviewSubmitAction('approve')
    reviewRunMutation.mutate({
      runId: resultModalRunId,
      body: {
        action: 'approve',
        reviewComment: reviewComment.trim() || undefined,
      },
    })
  }

  function handleRejectReview() {
    if (!resultModalRunId) return
    if (!canReviewSelectedRun) {
      message.warning('当前运行状态不允许拒绝候选结果')
      return
    }
    if (!reviewComment.trim()) {
      message.warning('拒绝候选结果时请填写审核备注')
      return
    }
    setReviewSubmitAction('reject')
    reviewRunMutation.mutate({
      runId: resultModalRunId,
      body: {
        action: 'reject',
        reviewComment: reviewComment.trim() || undefined,
      },
    })
  }

  function handleSaveCandidateResult() {
    if (!resultModalRunId || !canEditCandidate) return
    updateRunResultMutation.mutate({ runId: resultModalRunId, resultYaml: candidateYaml })
  }

  function handleImportRun(runId?: string) {
    if (!runId || importRunMutation.isPending) return
    setSelectedRunRecordId(runId)
    setImportAcknowledged(false)
    setImportConfirmRunId(runId)
  }

  function handleConfirmImport() {
    if (!importConfirmRunId || !importDetailsReady || !importAcknowledged || importRunMutation.isPending) return
    importRunMutation.mutate({ runId: importConfirmRunId, confirmOverwrite: false })
    setImportConfirmRunId(null)
    setImportAcknowledged(false)
  }

  function handleConfirmImportOverwrite() {
    if (!importConflict || importRunMutation.isPending) return
    importRunMutation.mutate({ runId: importConflict.runId, confirmOverwrite: true })
  }

  function resolveRunRecord(record: FunctionalCaseGenerateTaskRun): FunctionalCaseGenerateTaskRun {
    return record.runId && record.runId === selectedRunId && selectedRun ? selectedRun : record
  }

  function openRunRecordSection(runId: string | undefined, key: RunResultSectionKey, label: string) {
    setSelectedRunRecordId(runId ?? null)
    // 图谱分析改为独立页面展示：鱼骨图需要完整视口宽度，且 URL 可直接访问。
    if (key === 'caseRelations' && runId && taskId) {
      navigate(`/ai-testing/function-tasks/${taskId}/runs/${runId}/graph`)
      return
    }
    setRunResultModal({ key, label })
  }

  return (<ProjectAccessScope resourceError={taskQuery.error} projectId={task?.projectId ?? ''}>{personalLlm.dialog}{(
    <div className="workbench-page ai-testing-page">
      <div className="workbench-tabs">
        {taskQuery.error ? <Alert showIcon type="error" title={getErrorMessage(taskQuery.error)} /> : null}
        {runsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(runsQuery.error)} /> : null}

        {!task && taskQuery.isLoading ? (
          <Spin />
        ) : task ? (
          <div className="ai-task-detail-layout">
            <Card className="ai-task-detail-summary-card">
              <div className="ai-task-detail-inline-meta">
                <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/ai-testing?tab=tasks')}>
                  返回生成任务
                </Button>
                {detailItems.map((item) => (
                  <div key={item.label} className="ai-task-detail-inline-item">
                    <span className="ai-task-detail-inline-label">{item.label}</span>
                    <span className="ai-task-detail-inline-value">{item.value}</span>
                  </div>
                ))}
                <div className="ai-task-detail-inline-actions">
                  <ProjectActionButton action="execute"
                    className="action-btn-run"
                    operation="run"
                    disabled={runsQuery.isLoading || !runnableTask}
                    loading={runTaskMutation.isPending}
                    onClick={handleRunTask}
                  >
                    运行
                  </ProjectActionButton>
                  <ProjectActionButton action="write" className="action-btn-update" operation="edit" onClick={() => setDrawerOpen(true)}>
                    编辑
                  </ProjectActionButton>
                  <Popconfirm title="确认删除该任务？" onConfirm={() => deleteTaskMutation.mutate()}>
                    <ProjectActionButton action="write" danger className="action-btn-delete" operation="delete" loading={deleteTaskMutation.isPending}>
                      删除
                    </ProjectActionButton>
                  </Popconfirm>
                </div>
              </div>
            </Card>

            <div className="ai-task-detail-split">
              <aside className="ai-task-detail-nav-panel">
                <div className="ai-task-detail-nav-head">
                  <span className="ai-task-detail-nav-head-title">任务信息</span>
                  <span className="ai-task-detail-nav-head-sub">导航</span>
                </div>
                <div className="ai-task-detail-nav-body">
                  <div className="ai-task-detail-nav-label">输入</div>
                  <button type="button" className={`ai-task-detail-nav-item${expandedSection === 'document' ? ' active' : ''}`} onClick={() => setExpandedSection('document')}>
                    <span className="ai-task-detail-nav-item-title">需求文档</span>
                    <span className="ai-task-detail-nav-item-sub">{taskRequirementQuery.data?.name || '查看关联需求内容'}</span>
                  </button>
                  <button type="button" className={`ai-task-detail-nav-item${expandedSection === 'instruction' ? ' active' : ''}`} onClick={() => setExpandedSection('instruction')}>
                    <span className="ai-task-detail-nav-item-title">生成指令</span>
                    <span className="ai-task-detail-nav-item-sub">{task.instruction?.trim() || '暂无补充指令'}</span>
                  </button>
                  <div className="ai-task-detail-nav-label">输出</div>
                  <button type="button" className={`ai-task-detail-nav-item${expandedSection === 'runHistory' ? ' active' : ''}`} onClick={() => setExpandedSection('runHistory')}>
                    <span className="ai-task-detail-nav-item-title">运行记录</span>
                    <span className="ai-task-detail-nav-item-sub">共 {runRecords.length} 条运行记录</span>
                  </button>
                </div>
              </aside>

              <section className="ai-task-detail-main-panel">
                {expandedSection === 'document' ? (
                  <>
                    <div className="ai-task-detail-main-head">
                      <span className="ai-task-detail-main-head-title">需求文档</span>
                    </div>
                    <div className="ai-task-detail-main-body">
                      {taskRequirementQuery.isLoading ? (
                        <div className="ai-task-run-history-placeholder compact"><Spin /><span>需求内容加载中...</span></div>
                      ) : taskRequirementQuery.data && hasRequirementDocument(taskRequirementQuery.data) ? (
                        <RequirementDocumentPreviewContent
                          embedded
                          requirementId={normalizeRequirementId(taskRequirementQuery.data)}
                          requirementName={taskRequirementQuery.data.name}
                          documentType={taskRequirementQuery.data.documentType}
                          documentContent={taskRequirementQuery.data.documentContent}
                          documentFilename={taskRequirementQuery.data.documentFilename}
                          documentDownloadUrl={taskRequirementQuery.data.documentDownloadUrl}
                        />
                      ) : (
                        <div className="ai-task-run-history-placeholder compact"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="关联需求暂无可展示文档" /></div>
                      )}
                    </div>
                  </>
                ) : expandedSection === 'instruction' ? (
                  <>
                    <div className="ai-task-detail-main-head">
                      <span className="ai-task-detail-main-head-title">生成指令</span>
                    </div>
                    <div className="ai-task-detail-main-body">
                      <pre className="ai-task-code-block">{task.instruction || '-'}</pre>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="ai-task-detail-main-head">
                      <span className="ai-task-detail-main-head-title">运行记录</span>
                      <div className="ai-task-detail-main-head-extra">
                        <div className="ai-task-run-history-toolbar">
                          <Select
                            size="small"
                            className="ai-task-run-stage-filter"
                            aria-label="按状态筛选运行记录"
                            value={runStageFilter}
                            options={runStageFilterOptions}
                            onChange={(value) => setRunStageFilter(value)}
                          />
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
                        <RunHistoryTable<FunctionalCaseGenerateTaskRun>
                          rows={filteredRunRecords}
                          getRunId={(record) => record.runId}
                          selectedRunId={selectedRunId}
                          resolveRow={resolveRunRecord}
                          onSelect={(runId) => setSelectedRunRecordId(runId ?? null)}
                          renderStatus={(row) => {
                            const data = resolveRunRecord(row)
                            const repairProgress = String(data.status ?? '') === 'running' ? getOutputRepairProgress(data.resultSummaryJson) : null
                            const stageTag = row.runId === selectedRunId && data.checkpointEnabled && data.currentStage && data.currentStage !== 'completed'
                              ? <Tag color={selectedStageMeta.color}>{selectedStageMeta.label}</Tag>
                              : null
                            return <RunPipelineStatus run={data} repairProgress={repairProgress} stageTag={stageTag} />
                          }}
                          renderArtifacts={(row) => {
                            const artifacts = getRunRecordArtifacts(resolveRunRecord(row).configJson)
                            return (
                              <RunArtifacts
                                artifacts={artifacts}
                                onOpen={(key) => {
                                  const label = artifacts.find((artifact) => artifact.key === key)?.label ?? key
                                  openRunRecordSection(row.runId, key as RunResultSectionKey, label)
                                }}
                              />
                            )
                          }}
                          getReviewedAt={(row) => resolveRunRecord(row).reviewedAt}
                          getReviewComment={(row) => resolveRunRecord(row).reviewComment}
                          getImportedAt={(row) => resolveRunRecord(row).importedAt}
                          renderActions={(row, active) => {
                            const data = resolveRunRecord(row)
                            const recordStatus = String(data.status ?? '')
                            const recordSucceeded = recordStatus.toLowerCase() === 'success'
                            const recordFailed = ['failed', 'error'].includes(recordStatus.toLowerCase())
                            const reviewStatus = normalizeReviewStatus(data.reviewStatus)
                            const canReviewRecord = reviewStatus === 'pending' && recordStatus === 'success'
                            const canImportRecord = reviewStatus === 'approved' && data.importStatus === 'pending' && recordStatus === 'success'
                            const recordHasResultYaml = Boolean(formatStructuredContent(data.resultYaml))
                            const recordHasErrorMessage = Boolean(data.errorMessage?.trim())
                            const hasGraph = Boolean(getConfigStageFieldContent(data.configJson, 'caseRelations'))
                            const relationActionAllowed = reviewStatus === 'approved' && (recordSucceeded || recordFailed)
                            const stageReviewEntry = active && checkpointStageWaitingReview && selectedStageField
                            return (
                              <RunRowActions
                                inline={
                                  <>
                                    {/* 审核是本行最需要用户处理的动作，直接放在操作列，「更多」只留状态变更类操作。 */}
                                    {stageReviewEntry ? (
                                      <Button
                                        size="small"
                                        type="primary"
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          openRunRecordSection(row.runId, selectedStageField!.key as RunResultSectionKey, '审核')
                                        }}
                                      >
                                        审核
                                      </Button>
                                    ) : null}
                                    {canReviewRecord && can('read') ? (
                                      <Button
                                        size="small"
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          openResultModal(row.runId)
                                        }}
                                      >
                                        {can('review') ? '审核候选结果' : '查看候选结果'}
                                      </Button>
                                    ) : null}
                                    {!canReviewRecord && recordSucceeded && recordHasResultYaml ? (
                                      <Button
                                        size="small"
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          openResultModal(row.runId)
                                        }}
                                      >
                                        查看结果
                                      </Button>
                                    ) : null}
                                    {recordFailed && recordHasErrorMessage ? (
                                      <button
                                        type="button"
                                        className="ai-task-run-result-popover-btn"
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          openRunRecordSection(row.runId, 'errorMessage', '错误信息')
                                        }}
                                      >
                                        错误信息
                                      </button>
                                    ) : null}
                                    {!data.importMigrationComplete ? <RunMigrationWarningIcon /> : null}
                                  </>
                                }
                                menuItems={[
                                  ...(active && canRetryStage && can('execute')
                                    ? [{ key: 'retryStage', label: '重试阶段', disabled: retryStageMutation.isPending }]
                                    : []),
                                  ...(canImportRecord && can('execute')
                                    ? [{ key: 'importCases', label: '导入正式用例', disabled: importRunMutation.isPending }]
                                    : []),
                                  ...(relationActionAllowed && can('execute')
                                    ? [{
                                        key: 'generateRelations',
                                        label: hasGraph ? '重新生成图谱' : '生成图谱',
                                        disabled: generateRelationMutation.isPending && active,
                                      }]
                                    : []),
                                ]}
                                onMenuAction={(key) => {
                                  if (key === 'retryStage') {
                                    handleRetryStage()
                                    return
                                  }
                                  if (key === 'importCases') {
                                    handleImportRun(row.runId)
                                    return
                                  }
                                  if (key === 'generateRelations' && row.runId) {
                                    generateRelationMutation.mutate({ runId: row.runId })
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
                        {selectedRun && selectedRunResultSections.length === 0 && !checkpointStageVisible ? (
                          <div className="ai-task-run-history-hint compact">当前选中记录暂无可展示结果</div>
                        ) : null}
                      </>
                    ) : (
                      <div className="ai-task-run-history-placeholder">
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有运行记录" />
                        <div className="ai-task-run-history-hint">点击上方“运行”后，任务状态和最近一次执行信息会展示在这里。</div>
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

        <FunctionalCaseGenerateTaskDrawer
          title="编辑功能用例生成任务"
          open={drawerOpen}
          form={form}
          editing
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
          className={`ai-task-run-result-modal${showStageReviewInRunResultModal ? ' review' : ''}${showStageReviewInRunResultModal && revisionTarget !== 'stage' ? ' stage-review-with-comment' : ''}`}
          title={showStageReviewInRunResultModal ? '审核' : runResultModal?.label ?? '运行结果'}
          open={Boolean(runResultModal)}
          onCancel={() => { if (!reviseStageMutation.isPending) { setRevisionTarget(null); setRunResultModal(null) } }}
          footer={
            revisionTarget === 'stage' ? <div ref={setRevisionFooter} /> : showStageReviewInRunResultModal
              ? [
                  <div key="comment" className="ai-task-stage-review-footer-comment">
                    <Input.TextArea
                      className="ai-task-stage-review-comment"
                      value={stageReviewComment}
                      onChange={(event) => setStageReviewComment(event.target.value)}
                      rows={2}
                      aria-label="审核备注"
                      placeholder="审核备注，可选"
                    />
                  </div>,
                  <Button key="close" onClick={() => { setRevisionTarget(null); setRunResultModal(null) }}>
                    关闭
                  </Button>,
                  <ProjectActionButton operation="save" action="write"
                    key="save"
                    onClick={handleSaveStageOutput}
                    loading={saveStageOutputMutation.isPending && !stageReviewAction}
                    disabled={reviewStageMutation.isPending || reviseStageMutation.isPending}
                  >
                    保存
                  </ProjectActionButton>,
                  canReviseCheckpoint ? (
                    <ProjectActionButton action="execute" key="revise" disabled={stageActionPending} onClick={() => openRevisionModal('stage')}>
                      继续优化
                    </ProjectActionButton>
                  ) : null,
                  <ProjectActionButton action="review"
                    key="reject"
                    danger
                    ghost
                    onClick={handleRejectStageReview}
                    loading={reviewStageMutation.isPending && stageReviewAction === 'reject'}
                    disabled={saveStageOutputMutation.isPending || reviseStageMutation.isPending}
                  >
                    审核不通过
                  </ProjectActionButton>,
                  <ProjectActionButton action="review"
                    key="approve"
                    type="primary"
                    onClick={handleApproveStageReview}
                    loading={stageActionPending && stageReviewAction === 'approve'}
                    disabled={reviseStageMutation.isPending || (reviewStageMutation.isPending && stageReviewAction !== 'approve')}
                  >
                    审核通过并继续
                  </ProjectActionButton>,
                ]
              : [
                  <Button key="close" type="primary" onClick={() => { setRevisionTarget(null); setRunResultModal(null) }}>
                    关闭
                  </Button>,
                ]
          }
          width={revisionTarget === 'stage' ? "calc(100vw - 56px)" : "min(1620px, calc(100vw - 72px))"}
          centered
          destroyOnHidden
        >
          <div className={`revision-workspace${revisionTarget === 'stage' ? ' is-revising' : ''}`}><div className="revision-source">
          <div className={`ai-task-run-result-modal-content${showStageReviewInRunResultModal ? ' review' : ''}`}>
            {selectedRunQuery.isLoading ? (
              <div className="ai-task-run-result-popover-loading">
                <Spin />
              </div>
            ) : showStageReviewInRunResultModal ? (
              <div className="ai-task-stage-review-popover">
                <div className="ai-task-run-result-popover-header">
                  <span>阶段产物 {selectedStageField?.label ?? '当前阶段'}</span>
                  <div className="ai-task-stage-review-mini-tags">
                    <Tag color={selectedStageMeta.color}>{selectedStageMeta.label}</Tag>
                    <Tag color={selectedStageStatusMeta.color}>{selectedStageStatusMeta.label}</Tag>
                  </div>
                </div>
                <div className="ai-task-stage-review-note compact">
                  <strong>待审核/可编辑</strong>
                  <span>当前编辑的是本阶段产物，保存后会写回当前阶段输出，审核通过后继续进入下一阶段。</span>
                </div>
                {stageOutputIsCaseNames ? (
                  <Tabs
                    className="ai-case-names-inner-tabs expanded review"
                    size="small"
                    items={[
                      {
                        key: 'tree',
                        label: '可视化',
                        children: (
                          <CaseNameTreeView
                            content={stageOutputDraft}
                            rootTitle={task?.name || '功能测试用例生成'}
                            expanded
                            editable
                            onTreeChange={(value) => {
                              setStageOutputDraft(value)
                              setStageOutputDirty(true)
                            }}
                          />
                        ),
                      },
                      {
                        key: 'json',
                        label: 'json',
                        children: (
                          <TextCodeEditor
                            value={stageOutputDraft}
                            language="json"
                            onChange={(value) => {
                              setStageOutputDraft(value)
                              setStageOutputDirty(true)
                            }}
                            minHeight={360}
                          />
                        ),
                      },
                    ]}
                  />
                ) : stageOutputIsRequirementAnalysis ? (
                  <Tabs
                    className="ai-requirement-analysis-tabs review"
                    size="small"
                    activeKey={stageRequirementAnalysisView}
                    onChange={(key) => setStageRequirementAnalysisView(key as RequirementAnalysisViewMode)}
                    items={[
                      {
                        key: 'diagram',
                        label: '可视化',
                        children: (
                          <div className="ai-requirement-analysis-review-diagram">
                            <RequirementAnalysisDiagramView content={stageOutputDraft} />
                          </div>
                        ),
                      },
                      {
                        key: 'json',
                        label: 'json',
                        children: (
                          <TextCodeEditor
                            value={stageOutputDraft}
                            language="json"
                            onChange={(value) => {
                              setStageOutputDraft(value)
                              setStageOutputDirty(true)
                            }}
                            minHeight={360}
                          />
                        ),
                      },
                    ]}
                  />
                ) : (
                  <TextCodeEditor
                    value={stageOutputDraft}
                    onChange={(value) => {
                      setStageOutputDraft(value)
                      setStageOutputDirty(true)
                    }}
                    minHeight={360}
                  />
                )}

              </div>
            ) : runResultModalContent ? (
              runResultModal?.key === 'caseNames' ? (
                <CaseNamesResultView
                  content={runResultModalContent}
                  rootTitle={task?.name || '功能测试用例生成'}
                  expanded
                  activeView={runResultCaseNamesView}
                  onViewChange={setRunResultCaseNamesView}
                />
              ) : runResultModal?.key === 'requirementAnalysis' ? (
                <RequirementAnalysisView content={runResultModalContent} />
              ) : runResultModal?.key === 'enhancedText' ? (
                isJsonText(runResultModalContent) ? (
                  <JsonEditor value={runResultModalContent} readOnly foldable minHeight={640} />
                ) : (
                  <pre className="ai-task-code-block">{runResultModalContent}</pre>
                )
              ) : (
                <pre className="ai-task-code-block">{runResultModalContent}</pre>
              )
            ) : (
              <div className="ai-task-run-result-popover-empty">暂无内容</div>
            )}
          </div>
          </div>{revisionTarget === 'stage' && <><RevisionDivider /><RevisionSidePanel footerContainer={revisionFooter} projectId={task?.projectId} value={revisionInstruction} onChange={setRevisionInstruction} loading={reviseStageMutation.isPending} onCancel={() => setRevisionTarget(null)} onSubmit={handleReviseStage} /></>}</div>
        </Modal>

        <Modal
          mask={{ closable: false }}
          className="ai-task-import-result-modal functional-candidate-review-modal"
          title={
            <div className="functional-candidate-review-title">
              <div>
                <strong>{canReviewSelectedRun ? '审核候选结果' : '功能测试用例候选结果'}</strong>
                <span title={importTargetRequirementName}>关联需求：{importTargetRequirementName}</span>
              </div>
              <div className="functional-candidate-review-title-stats">
                <span>模块 <strong>{selectedRunImportStats.moduleCount}</strong></span>
                <span>用例 <strong>{selectedRunImportStats.caseCount}</strong></span>
              </div>
            </div>
          }
          open={resultModalOpen}
          onCancel={closeResultModal}
          footer={
            revisionTarget === 'final' ? <div ref={setRevisionFooter} /> : reviewAvailable
              ? (
                  <div className="functional-candidate-review-footer">
                    <label htmlFor="functional-review-comment">
                      <span>审核备注 <em>拒绝时必填</em></span>
                      <Input.TextArea
                        id="functional-review-comment"
                        aria-label="审核备注"
                        autoSize={{ minRows: 1, maxRows: 2 }}
                        value={reviewComment}
                        onChange={(event) => setReviewComment(event.target.value)}
                        placeholder="请输入审核意见或补充说明"
                      />
                    </label>
                    <div className="functional-candidate-review-actions">
                      <span>已选择全部 <strong>{selectedRunImportStats.caseCount}</strong> 条</span>
                      <Button onClick={closeResultModal}>取消</Button>
                      {reviewAvailable && selectedRun?.importStatus !== 'imported' ? (
                        <ProjectActionButton action="execute" disabled={updateRunResultMutation.isPending || reviewRunMutation.isPending || reviseStageMutation.isPending}
                          onClick={() => openRevisionModal('final')}>继续优化</ProjectActionButton>
                      ) : null}
                      <ProjectActionButton action="review"
                        danger
                        ghost
                        loading={reviewRunMutation.isPending && reviewSubmitAction === 'reject'}
                        disabled={reviseStageMutation.isPending || updateRunResultMutation.isPending || (reviewRunMutation.isPending && reviewSubmitAction !== 'reject')}
                        onClick={handleRejectReview}
                      >
                        拒绝
                      </ProjectActionButton>
                      <ProjectActionButton action="review"
                        type="primary"
                        loading={reviewRunMutation.isPending && reviewSubmitAction === 'approve'}
                        disabled={reviseStageMutation.isPending || updateRunResultMutation.isPending || (reviewRunMutation.isPending && reviewSubmitAction !== 'approve')}
                        onClick={handleApproveReview}
                      >
                        批准 {selectedRunImportStats.caseCount} 条
                      </ProjectActionButton>
                    </div>
                  </div>
                )
              : <Button type="primary" onClick={closeResultModal}>关闭</Button>
          }
          width={revisionTarget === 'final' ? "calc(100vw - 56px)" : "min(1620px, calc(100vw - 72px))"}
          centered
          destroyOnHidden
        >
          <div className={`revision-workspace${revisionTarget === 'final' ? ' is-revising' : ''}`}><div className="revision-source">
          <Form layout="vertical" className="ai-task-import-result-form">
            <Tabs
              className="functional-candidate-review-tabs"
              activeKey={candidateModalView}
              onChange={(key) => setCandidateModalView(key as 'preview' | 'edit')}
              items={[
                {
                  key: 'preview',
                  label: '可视化',
                  children: (
                    <div className="ai-task-review-modal-content ai-task-result-preview-modal-content ai-task-import-result-preview-content single-column">
                      <div className="ai-task-review-modal-section">
                        <div className="ai-task-review-modal-preview ai-task-import-result-preview">
                          {selectedRunQuery.isLoading ? (
                            <div className="ai-task-run-result-popover-loading">
                              <Spin />
                            </div>
                          ) : selectedRun?.resultYaml ? (
                            <GeneratedCasesReviewView content={formatStructuredContent(selectedRun.resultYaml)} />
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
                    <div className="ai-task-review-modal-content single-column functional-candidate-edit-pane">
                      <JsonEditor
                        ariaLabel="功能候选结果 JSON"
                        value={candidateYaml}
                        onChange={setCandidateYaml}
                        readOnly={!canEditCandidate}
                        foldable
                        minHeight={0}
                        downloadFileName="功能候选结果.json"
                      />
                      {updateRunResultMutation.error ? (
                        <Alert showIcon type="error" title={getErrorMessage(updateRunResultMutation.error)} />
                      ) : null}
                      {reviewAvailable ? (
                        <ProjectActionButton action="write"
                          type="primary"
                          loading={updateRunResultMutation.isPending}
                          disabled={!candidateDirty || reviewRunMutation.isPending || reviseStageMutation.isPending}
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
          </Form>
          </div>{revisionTarget === 'final' && <><RevisionDivider /><RevisionSidePanel footerContainer={revisionFooter} projectId={task?.projectId} value={revisionInstruction} onChange={setRevisionInstruction} loading={reviseStageMutation.isPending} onCancel={() => setRevisionTarget(null)} onSubmit={handleReviseStage} /></>}</div>
        </Modal>

        {importConfirmRunId ? <ProjectActionModal action="execute"
          title={<div className="functional-import-confirm-title"><span className="functional-import-confirm-icon"><FileTextOutlined /></span><span>确认导入正式用例</span></div>}
          className="functional-import-confirm-modal"
          width={560}
          centered
          open={Boolean(importConfirmRunId)}
          okText="确认导入"
          cancelText="取消"
          okButtonProps={{ disabled: !importDetailsReady || !importAcknowledged }}
          onOk={handleConfirmImport}
          onCancel={() => { setImportConfirmRunId(null); setImportAcknowledged(false) }}
        >
          <p className="functional-import-confirm-description">导入后，审核通过的结果将写入对应需求的功能测试集。</p>
          {selectedRunQuery.isError ? (
            <Alert
              showIcon
              type="error"
              title={getErrorMessage(selectedRunQuery.error)}
              action={<Button loading={selectedRunQuery.isFetching} onClick={() => { void selectedRunQuery.refetch() }}>重新加载结果</Button>}
            />
          ) : !importDetailsReady ? (
            <div role="status"><Spin size="small" /> <span>正在加载待导入结果…</span></div>
          ) : (
            <div className="functional-import-confirm-summary">
              <span className="functional-import-confirm-label">关联需求</span>
              <strong>{importTargetRequirementName}</strong>
              <div className="functional-import-confirm-counts">
                <span><b>{selectedRunImportStats.moduleCount}</b> 个模块</span>
                <span><b>{selectedRunImportStats.caseCount}</b> 条用例</span>
              </div>
            </div>
          )}
          <div className={`functional-import-confirm-check${importAcknowledged ? ' is-checked' : ''}`}>
            <Checkbox disabled={!importDetailsReady} checked={importAcknowledged} onChange={(event) => setImportAcknowledged(event.target.checked)}>
              我已确认结果，确定导入正式用例
            </Checkbox>
          </div>
        </ProjectActionModal> : null}

        <FunctionalImportConflictModal
          open={Boolean(importConflict)}
          conflicts={importConflict?.conflicts ?? []}
          loading={importRunMutation.isPending}
          error={importConflict ? importRunMutation.error : undefined}
          onCancel={() => setImportConflict(null)}
          onConfirm={handleConfirmImportOverwrite}
        />

        <LlmConnectionSelectModal
          open={llmSelectOpen}
          projectId={task?.projectId}
          onClose={() => {
            setLlmSelectOpen(false)
            setCheckpointEnabled(false)
          }}
          onConfirm={handleLlmSelectConfirm}
          loading={runTaskMutation.isPending}
          showCheckpointOption
          checkpointEnabled={checkpointEnabled}
          onCheckpointEnabledChange={setCheckpointEnabled}
        />
      </div>
    </div>
  )}</ProjectAccessScope>)
}
