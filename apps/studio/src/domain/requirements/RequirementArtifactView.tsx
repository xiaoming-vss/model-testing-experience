import { parseRequirementArtifact, pendingRequirementQuestions, type RequirementSourceReference } from './requirementArtifact'
import { Alert, Button, Collapse, Descriptions, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ReactNode } from 'react'

const labels: Record<string, string> = {
  documentTitle: '材料标题', title: '标题', sources: '材料来源', contentBlocks: '材料内容',
  extractedFacts: '提取的事实', functionalOverview: '功能概况', businessFlows: '整体业务流程',
  modules: '模块使用理解', businessRules: '业务规则', questions: '待确认问题', purpose: '功能目的',
  scope: '适用范围', actors: '适用角色', explicitExclusions: '明确排除的范围', name: '名称',
  entryPoints: '这个功能怎么进入', operations: '这个功能怎么使用', userVisibleFlow: '用户看到的完整流程',
  path: '入口路径', conditions: '进入条件', goal: '操作目的', preconditions: '前置条件',
  steps: '操作流程', actor: '执行角色', action: '操作动作', systemResponse: '系统响应',
  interaction: '交互说明', controls: '控件与字段', label: '控件名称', businessMeaning: '业务含义',
  type: '类型', options: '实际选项', items: '已记录条目', completeness: '选项是否完整',
  inputRules: '输入规则', defaultValue: '默认值', trigger: '触发方式', initialState: '初始状态',
  dependencies: '条件联动', results: '结果观察', location: '观察或来源位置', fields: '展示字段',
  recordIdentity: '记录标识', emptyState: '空结果展示', pagination: '分页', sorting: '排序',
  validationAndFeedback: '校验与反馈', ruleIds: '关联规则', moduleIds: '关联模块',
  operationIds: '关联操作', moduleId: '所属模块', operationId: '对应操作', nextSteps: '后续分支',
  stepId: '下一节点', condition: '分支条件', expectedBehavior: '预期处理', observableOutcome: '观察依据',
  id: '条目标识', parentId: '所属章节', kind: '内容类型', text: '正文', table: '表格', image: '图片理解',
  visibleTexts: '可见文字', meaning: '含义', parseStatus: '识别状态', category: '事实分类',
  fact: '材料事实', relatedBlockIds: '对应材料', note: '衔接说明', relatedQuestionIds: '关联问题',
  question: '待确认问题', status: '问题状态', affectedRefs: '影响对象', impacts: '影响的工作',
  stage: '影响阶段', description: '具体影响', blocking: '是否阻塞', answer: '答复', value: '选项值',
  sourceReferences: '依据来源', sourceId: '来源', locator: '定位', excerpt: '摘录', version: '材料版本',
}
const states: Record<string, string> = {
  confirmed: '有明确依据', unconfirmed: '待确认', conflicting: '存在冲突', example: '示例',
  not_applicable: '不适用', open: '未解决', resolved: '已答复', complete: '完整', partial: '部分已知',
  unknown: '未知', unreadable: '无法识别', section: '章节', paragraph: '段落', list: '列表',
  table: '表格', image: '图片', document: '需求文档', text: '文本材料', prototype: '原型', screenshot: '截图', design: '设计稿',
  user_confirmation: '用户明确答复', extraction: '材料提取', understanding: '需求理解',
  test_points: '测试点', test_cases: '完整用例', other: '其他', control: '控件', operation: '操作',
  option: '选项', default: '默认值', dependency: '联动', result: '结果', validation: '校验',
  business_rule: '业务规则', actor: '角色', entry: '入口', block: '材料块', extracted_fact: '提取事实',
  requirement: '整体需求', module: '模块', rule: '规则', flow: '流程', scope: '范围',
}

type RecordValue = Record<string, unknown>
function record(value: unknown): value is RecordValue {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}


function MaterialTable({ value }: { value: RecordValue }) {
  const cells = Array.isArray(value.cells) ? value.cells.filter(record) : []
  const rows = Number(value.rowCount) || Math.max(0, ...cells.map(c => Number(c.row) + Number(c.rowSpan)))
  const columns = Number(value.columnCount) || Math.max(0, ...cells.map(c => Number(c.column) + Number(c.columnSpan)))
  if (!rows || !columns) return <Typography.Text type="secondary">表格尚未识别</Typography.Text>
  const data = Array.from({ length: rows }, (_, row) => ({ key: row, row }))
  return <Table size="small" pagination={false} showHeader={false} scroll={{ x: 'max-content' }} dataSource={data}
    columns={Array.from({ length: columns }, (_, column) => ({
      key: String(column), width: 160,
      render: (_: unknown, item: { row: number }) => {
        const cell = cells.find(c => c.row === item.row && c.column === column)
        return cell?.text == null ? '未识别' : String(cell.text)
      },
      onCell: (item: { row: number }) => {
        const cell = cells.find(c => c.row === item.row && c.column === column)
        return cell ? { rowSpan: Number(cell.rowSpan), colSpan: Number(cell.columnSpan) } : { rowSpan: 0, colSpan: 0 }
      },
    }))} />
}

function RequirementArtifactRenderer({ content, section, onSourceReference, expandCollections = false }: { content: unknown; section?: { field: string; value: unknown }; expandCollections?: boolean; onSourceReference?: (ref: RequirementSourceReference) => void }) {
  let artifact: RecordValue | null
  try { artifact = parseRequirementArtifact(content) } catch (error) {
    return <Alert type="error" showIcon title={error instanceof Error ? error.message : '无法读取结构化产物'} />
  }
  if (!artifact) return <Alert type="error" showIcon title="产物缺少有效的 JSON 契约，请在原始 JSON 中修正" />
  const sources = (artifact.sources as unknown[]).filter(record)
  const pendingQuestions = pendingRequirementQuestions((artifact.questions as unknown[]).filter(record))
  const pendingQuestionIds = new Set(pendingQuestions.map(q => String(q.id)))
  const names = new Map<string, string>()
  function collect(value: unknown) {
    if (Array.isArray(value)) value.forEach(collect)
    else if (record(value)) {
      if (typeof value.id === 'string') {
        const name = value.name || value.title || value.question
        if (name || !names.has(value.id)) names.set(value.id, String(name || value.id))
      }
      Object.values(value).forEach(collect)
    }
  }
  collect(artifact)
  // 流程步骤自身没有名称，把步骤 ID 翻译成其「对应操作」名，供下一节点等引用显示。
  for (const flow of (Array.isArray(artifact.businessFlows) ? artifact.businessFlows : []).filter(record)) {
    for (const step of (Array.isArray(flow.steps) ? flow.steps : []).filter(record)) {
      if (typeof step.id === 'string' && step.name == null && step.title == null) {
        const operationName = names.get(String(step.operationId ?? ''))
        if (operationName) names.set(step.id, operationName)
      }
    }
  }
  function renderSource(ref: RecordValue, index: number) {
    const label = `${sources.find(source => source.id === ref.sourceId)?.name || String(ref.sourceId)} · ${String(ref.locator)}`
    return <Tooltip key={index} title={ref.excerpt ? String(ref.excerpt) : undefined}>
      {onSourceReference && typeof ref.sourceId === 'string' && typeof ref.locator === 'string'
        ? <Button type="link" size="small" style={{ height: 'auto', padding: 0, whiteSpace: 'normal', textAlign: 'left' }} onClick={() => onSourceReference({ sourceId: String(ref.sourceId), locator: String(ref.locator), excerpt: typeof ref.excerpt === 'string' ? ref.excerpt : null })}>{label}</Button>
        : <Typography.Text type="secondary">{label}</Typography.Text>}
    </Tooltip>
  }
  function displayName(item: RecordValue, key: string, index: number) {
    const unwrap = (value: unknown) => record(value) && 'value' in value ? value.value : value
    const preferred = [item.name, item.title, item.question, unwrap(item.label), unwrap(item.action),
      unwrap(item.fact), unwrap(item.value), unwrap(item.path), unwrap(item.condition), names.get(String(item.operationId || '')), item.text]
      .find(value => value !== null && value !== undefined && value !== '')
    return preferred !== undefined ? String(preferred).slice(0, 80) : `${labels[key] || '条目'} ${index + 1}`
  }
  function render(value: unknown, key = '', expand: boolean = expandCollections): ReactNode {
    if (value == null) return <Typography.Text type="secondary">未明确</Typography.Text>
    if (typeof value === 'boolean') return value ? '是' : '否'
    if (typeof value !== 'object') {
      const text = String(value)
      return ['status', 'parseStatus', 'type', 'kind', 'stage', 'category', 'completeness'].includes(key)
        ? states[text] || text : names.get(text) || text
    }
    if (Array.isArray(value)) {
      let items = value
      if (key === 'questions') items = pendingRequirementQuestions(items.filter(record))
      if (key === 'relatedQuestionIds') items = items.filter(id => pendingQuestionIds.has(String(id)))
      if (!items.length) return <Typography.Text type="secondary">暂无已记录条目</Typography.Text>
      if (key === 'sourceReferences' && onSourceReference) return <Space orientation="vertical" size={4}>{items.filter(record).map(renderSource)}</Space>
      if (items.every(item => !record(item))) return items.map(item => render(item, key)).join('、')
      if (key === 'userVisibleFlow') return <Space orientation="vertical" size={8}>{items.filter(record).map((item, index) =>
        <div key={index}><Typography.Text strong>{index + 1}. {names.get(String(item.operationId)) || String(item.operationId)}</Typography.Text><div>{render(item.note)}</div></div>)}</Space>
      if (items.every(item => record(item) && 'confirmationStatus' in item)) {
        return <Space orientation="vertical" size={8}>{items.map((item, index) => <div key={index}>{render(item)}</div>)}</Space>
      }
      if (expand) return <Space orientation="vertical" size="middle" style={{ width: '100%' }}>{items.map((item, index) => <section key={record(item) && typeof item.id === 'string' ? item.id : index} style={{ width: '100%' }}>
        <Typography.Text strong>{record(item) ? displayName(item, key, index) : String(index + 1)}</Typography.Text>
        {render(item)}
      </section>)}</Space>
      return <Collapse ghost items={items.map((item, index) => ({
        key: record(item) && typeof item.id === 'string' ? item.id : String(index),
        label: record(item) ? displayName(item, key, index) : `${index + 1}`,
        children: render(item, key),
      }))} />
    }
    const item = value as RecordValue
    if ('confirmationStatus' in item && 'value' in item) {
      const questionIds = Array.isArray(item.relatedQuestionIds) ? item.relatedQuestionIds.filter(id => pendingQuestionIds.has(String(id))) : []
      const status = String(item.confirmationStatus)
      const displayValue = key === 'completeness' && typeof item.value === 'string' ? states[item.value] || item.value : item.value
      const refs = Array.isArray(item.sourceReferences) ? item.sourceReferences.filter(record) : []
      return <Space orientation="vertical" size={4}>
        <Space wrap><span>{displayValue == null ? (status === 'not_applicable' ? '不适用' : '未知') : Array.isArray(displayValue) ? displayValue.map(String).join('、') || '空值' : String(displayValue)}</span>
          <Tag color={status === 'conflicting' ? 'error' : status === 'unconfirmed' ? 'warning' : status === 'confirmed' ? 'success' : 'default'}>{states[status] || status}</Tag></Space>
        {refs.map(renderSource)}
        {questionIds.length ? <Typography.Text type="warning">关联问题：{questionIds.map(q => names.get(String(q)) || String(q)).join('；')}</Typography.Text> : null}
      </Space>
    }
    if (key === 'table') return <MaterialTable value={item} />
    return <Descriptions column={1} size="small" items={Object.entries(item)
      .filter(([field]) => !['schemaVersion', 'artifactType', 'id'].includes(field))
      // 操作内的交互细节统一由「UI 交互」章节读取，避免同一份控件记录重复展示。
      .filter(([field]) => !(key === 'operations' && field === 'interaction'))
      .filter(([field, child]) => field !== 'answer' || child != null)
      .filter(([field, child]) => field !== 'relatedQuestionIds' || (Array.isArray(child) && child.some(id => pendingQuestionIds.has(String(id)))))
      .filter(([field]) => {
        if (!['section', 'paragraph', 'list', 'table', 'image'].includes(String(item.kind))) return true
        if (field === 'text') return ['section', 'paragraph'].includes(String(item.kind))
        if (field === 'items') return item.kind === 'list'
        if (field === 'table' || field === 'image') return item.kind === field
        return true
      })
      .map(([field, child]) => ({ key: field, label: labels[field] || field, children: render(child, field) }))} />
  }
  const moduleItems = Array.isArray(artifact.modules) ? artifact.modules.filter(record) : []
  /** Dedicated UI-interaction reading: one collapsed entry per operation; controls stay collapsed behind their own items. */
  function renderUiInteractionSection(): ReactNode {
    const entries = moduleItems.flatMap(module => (Array.isArray(module.operations) ? module.operations : []).filter(record).flatMap(operation => {
      if (!record(operation.interaction)) return []
      return [{ module, operation, interaction: operation.interaction }]
    }))
    return <section key="ui-interactions" style={{ width: '100%' }}>
      <Typography.Title level={5}>UI 交互</Typography.Title>
      {entries.length ? <Collapse ghost items={entries.map(({ module, operation, interaction }) => {
        const controls = Array.isArray(interaction.controls) ? interaction.controls : []
        const behavior = Object.fromEntries(Object.entries(interaction).filter(([field]) => !['id', 'controls'].includes(field)))
        return {
          key: `${String(module.id)}/${String(operation.id)}`,
          label: `${displayName(module, 'modules', 0)} / ${displayName(operation, 'operations', 0)}`,
          children: <>
            {controls.length ? render(controls, 'controls') : <Typography.Text type="secondary">暂无控件记录</Typography.Text>}
            {Object.keys(behavior).length ? render(behavior) : null}
          </>,
        }
      })} /> : <Typography.Text type="secondary">暂无已记录的操作交互</Typography.Text>}
    </section>
  }
  if (section) return <>{render(section.value, section.field)}</>
  return <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Typography.Title level={4}>{String(artifact.title || artifact.documentTitle || '需求材料')}</Typography.Title>
    {Object.entries(artifact).filter(([key]) => !['schemaVersion', 'artifactType', 'title', 'documentTitle'].includes(key) && (key !== 'questions' || pendingQuestions.length > 0)).flatMap(([key, value]) => {
      const node = <section key={key} style={{ width: '100%' }}><Typography.Title level={5}>{labels[key] || key}</Typography.Title>{render(value, key)}</section>
      return key === 'modules' && moduleItems.length ? [node, renderUiInteractionSection()] : [node]
    })}
  </Space>
}

export function RequirementArtifactView({ content }: { content: unknown }) {
  return <RequirementArtifactRenderer content={content} />
}

/** Render a material table, fact or question with the same source/status semantics as the full artifact. */
export function RequirementArtifactValue({ artifact, value, field = '', onSourceReference, expandCollections = false }: { artifact: unknown; value: unknown; field?: string; expandCollections?: boolean; onSourceReference?: (ref: RequirementSourceReference) => void }) {
  return <RequirementArtifactRenderer content={artifact} section={{ field, value }} onSourceReference={onSourceReference} expandCollections={expandCollections} />
}
