import { useMemo, useState } from 'react'
import { Alert, Empty, Input, Tag } from 'antd'
import { parseRequirementArtifact } from '../../../domain/requirements/requirementArtifact'
import '../styles/readable-requirement-material.css'

export type MaterialBlock = { id: string; sourceId: string; kind: string; locator: string; content: Record<string, unknown> }
type Source = { id: string; name: string; location: string | null }
type Item = { text: string; status: string; materialBlockIds: string[] }
type Section = { title: string; items: Item[] }
type Question = { id: string; question: string; reason: string; materialBlockIds: string[]; functionIds: string[] }
type Material = {
  artifactType: string
  title: string
  sources: Source[]
  materialBlocks: MaterialBlock[]
  functions: { id: string; name: string; sections: Section[] }[]
  questions: Question[]
}

const tabs = [
  { key: 'functions', label: '功能说明', hint: '按功能浏览章节与条目' },
  { key: 'questions', label: '待确认', hint: '材料未明确、需要进一步确认的事项' },
] as const

type Tab = (typeof tabs)[number]['key']

const statusLabels: Record<string, { label: string; color: string }> = {
  confirmed: { label: '明确', color: 'green' },
  unconfirmed: { label: '待确认', color: 'orange' },
  conflicting: { label: '有冲突', color: 'red' },
  example: { label: '示例', color: 'blue' },
}

const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const references = (value: unknown) => Array.isArray(value) && value.every(item => typeof item === 'string')

function parse(content: unknown): Material {
  const value = parseRequirementArtifact(content)
  if (!value || value.artifactType !== 'readable_requirement_material' || !Array.isArray(value.sources) || !Array.isArray(value.materialBlocks) || !Array.isArray(value.functions) || !Array.isArray(value.questions)) throw new Error('材料整理结果不符合当前格式，请检查 JSON')
  if (typeof value.title !== 'string' || value.sources.some(s => !record(s) || typeof s.id !== 'string' || typeof s.name !== 'string' || !(s.location === null || typeof s.location === 'string')) || value.materialBlocks.some(b => !record(b) || typeof b.id !== 'string' || typeof b.sourceId !== 'string' || typeof b.kind !== 'string' || typeof b.locator !== 'string' || !record(b.content)) || value.functions.some(f => !record(f) || typeof f.id !== 'string' || typeof f.name !== 'string' || !Array.isArray(f.sections) || f.sections.some(s => !record(s) || typeof s.title !== 'string' || !Array.isArray(s.items) || s.items.some(i => !record(i) || typeof i.text !== 'string' || typeof i.status !== 'string' || !references(i.materialBlockIds)))) || value.questions.some(q => !record(q) || typeof q.id !== 'string' || typeof q.question !== 'string' || !references(q.materialBlockIds) || !references(q.functionIds))) throw new Error('材料整理内容不完整，请检查 JSON')
  return value as unknown as Material
}

export function MaterialBlockContent({ block }: { block: MaterialBlock }) {
  const value = block.content
  if (block.kind === 'table' && Array.isArray(value.rows)) {
    const spans = Array.isArray(value.spans) ? value.spans as { row: number; column: number; rowSpan: number; columnSpan: number }[] : []
    return <div className="readable-material-table"><table><tbody>{value.rows.map((row, i) => <tr key={i}>{Array.isArray(row) && row.map((cell, j) => {
      const span = spans.find(s => s.row === i && s.column === j)
      if (!span && spans.some(s => i >= s.row && i < s.row + s.rowSpan && j >= s.column && j < s.column + s.columnSpan)) return null
      return <td key={j} rowSpan={span?.rowSpan} colSpan={span?.columnSpan}>{typeof cell === 'string' ? cell : '无法识别'}</td>
    })}</tr>)}</tbody></table></div>
  }
  if (block.kind === 'list' && Array.isArray(value.items)) return <ul>{value.items.map((item, i) => <li key={i}>{String(item)}</li>)}</ul>
  if (block.kind === 'image') return <><p>{typeof value.description === 'string' ? value.description : '图片内容未识别'}</p>{value.readStatus !== 'complete' && <small>图片内容可能未完整识别，请核对原始材料。</small>}</>
  return <p>{typeof value.text === 'string' ? value.text : '材料内容不可读取'}</p>
}

function itemsOf(feature: Material['functions'][number]) {
  return feature.sections.flatMap(section => section.items)
}

function Field({ label, value }: { label: string; value: string }) {
  return <div className="readable-material-field">
    <span>{label}</span>
    <p>{value || '未记录'}</p>
  </div>
}

function RefChips({ title, values, resolve }: {
  title: string
  values: string[]
  resolve: (id: string) => string | undefined
}) {
  if (!values.length) return null
  return <section className="readable-material-refs">
    <h4>{title}<span>{values.length}</span></h4>
    <div className="readable-material-chips">
      {values.map((id) => {
        const label = resolve(id)
        return <span key={id}>{label ? `${id} ${label}` : id}</span>
      })}
    </div>
  </section>
}

function Evidence({ blockIds, material }: { blockIds: string[]; material: Material }) {
  return <section className="readable-material-evidence" aria-label="材料依据">
    <h4>材料依据<span>{blockIds.length}</span></h4>
    {blockIds.length ? <div className="readable-material-evidence-list">
      {blockIds.map((id) => {
        const block = material.materialBlocks.find(item => item.id === id)
        if (!block) return <div key={id} className="readable-material-evidence-missing">{id}：未找到对应材料</div>
        const source = material.sources.find(item => item.id === block.sourceId)
        return <article key={id} className="readable-material-evidence-item">
          <div className="readable-material-evidence-head">
            <strong>{source?.name || '来源未找到'}</strong>
            <span>{block.locator}</span>
          </div>
          <MaterialBlockContent block={block} />
        </article>
      })}
    </div> : <p className="readable-material-empty-ref">暂无材料依据</p>}
  </section>
}

export function ReadableRequirementMaterial({ content, editable, onChange }: { content: unknown; editable?: boolean; onChange?: (content: string) => void }) {
  const [tab, setTab] = useState<Tab>('functions')
  const [activeFunctionId, setActiveFunctionId] = useState<string | null>(null)
  const [questionIndex, setQuestionIndex] = useState(0)
  const [expandedEvidence, setExpandedEvidence] = useState<string | null>(null)

  const parsed = useMemo(() => {
    try { return { value: parse(content) } } catch (error) { return { error: error instanceof Error ? error.message : '无法读取材料整理结果' } }
  }, [content])
  if (!parsed.value) return <Alert type="error" showIcon title={parsed.error} />
  const material = parsed.value

  const activeFunction = material.functions.find(feature => feature.id === activeFunctionId) ?? material.functions[0]
  const safeQuestionIndex = Math.min(questionIndex, Math.max(material.questions.length - 1, 0))
  const activeQuestion = material.questions[safeQuestionIndex]
  const currentTab = tabs.find(item => item.key === tab)!
  const allItems = material.functions.flatMap(itemsOf)
  const statusCounts = { confirmed: 0, unconfirmed: 0, conflicting: 0, example: 0 }
  allItems.forEach((item) => {
    if (item.status in statusCounts) statusCounts[item.status as keyof typeof statusCounts] += 1
  })
  const generalQuestions = material.questions.filter(question => question.functionIds.length === 0)
  const tabCounts: Record<Tab, number> = {
    functions: material.functions.length,
    questions: material.questions.length,
  }
  const functionNameById = new Map(material.functions.map(feature => [feature.id, feature.name]))

  const updateItem = (featureId: string, sectionIndex: number, itemIndex: number, text: string) => {
    if (!onChange) return
    const next = structuredClone(material)
    const item = next.functions.find(feature => feature.id === featureId)?.sections[sectionIndex]?.items[itemIndex]
    if (item) item.text = text
    onChange(JSON.stringify(next, null, 2))
  }

  const updateQuestion = (id: string, question: string) => {
    if (!onChange) return
    const next = structuredClone(material)
    const item = next.questions.find(entry => entry.id === id)
    if (item) item.question = question
    onChange(JSON.stringify(next, null, 2))
  }

  const questionScope = (question: Question) => question.functionIds.length
    ? question.functionIds.map(id => functionNameById.get(id) ?? id).join(' / ')
    : '整体'

  const selectFunction = (id: string) => {
    setActiveFunctionId(id)
    setExpandedEvidence(null)
  }

  const renderFunctionDetail = () => {
    if (!activeFunction) return <div className="readable-material-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无功能说明" /></div>
    const sections = activeFunction.sections
      .map((section, index) => ({ section, index }))
      .filter(({ section }) => section.items.length > 0)
    if (!sections.length) return <div className="readable-material-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该功能暂无内容" /></div>
    return <>
      <div className="readable-material-kicker">
        <span className="readable-material-badge">功能说明</span>
        <span>{activeFunction.id}</span>
      </div>
      <h2>{activeFunction.name || '未命名功能'}</h2>
      <div className="readable-material-sections">
        {sections.map(({ section, index: sectionIndex }) => <section className="readable-material-section" key={`${section.title}-${sectionIndex}`}>
          <div className="readable-material-section-head">
            <h3>{section.title || '未命名章节'}</h3>
            <span>{section.items.length} 条</span>
          </div>
          {section.items.map((item, itemIndex) => {
            const evidenceKey = `${activeFunction.id}:${sectionIndex}:${itemIndex}`
            const evidenceOpen = expandedEvidence === evidenceKey
            const itemStatus = statusLabels[item.status]
            return <article className="readable-material-item" key={evidenceKey}>
              <div className="readable-material-item-main">
                {editable && onChange
                  ? <Input.TextArea
                    className="readable-material-item-input"
                    aria-label={`${activeFunction.name} ${section.title} 内容 ${itemIndex + 1}`}
                    autoSize
                    value={item.text}
                    onChange={event => updateItem(activeFunction.id, sectionIndex, itemIndex, event.target.value)}
                  />
                  : <p className="readable-material-item-text">{item.text}</p>}
                <div className="readable-material-item-meta">
                  {itemStatus && item.status !== 'confirmed' ? <Tag color={itemStatus.color}>{itemStatus.label}</Tag> : null}
                  {item.materialBlockIds.length ? <button
                    type="button"
                    className="readable-material-evidence-toggle"
                    aria-expanded={evidenceOpen}
                    onClick={() => setExpandedEvidence(evidenceOpen ? null : evidenceKey)}
                  >依据 {item.materialBlockIds.length}</button> : null}
                </div>
              </div>
              {evidenceOpen ? <Evidence blockIds={item.materialBlockIds} material={material} /> : null}
            </article>
          })}
        </section>)}
      </div>
    </>
  }

  const renderQuestionDetail = () => {
    if (!activeQuestion) return <div className="readable-material-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待确认问题" /></div>
    return <>
      <div className="readable-material-kicker">
        <span className="readable-material-badge">待确认</span>
        <span>{activeQuestion.id || '问题'}</span>
        <Tag color={activeQuestion.functionIds.length ? undefined : 'blue'}>{questionScope(activeQuestion)}</Tag>
      </div>
      {editable && onChange
        ? <label className="readable-material-question-edit">
          <span>问题</span>
          <Input.TextArea
            aria-label={`待确认问题 ${safeQuestionIndex + 1}`}
            autoSize
            value={activeQuestion.question}
            onChange={event => updateQuestion(activeQuestion.id, event.target.value)}
          />
        </label>
        : <h2>{activeQuestion.question || '未记录问题'}</h2>}
      <Field label="原因" value={activeQuestion.reason} />
      <RefChips title="关联功能" values={activeQuestion.functionIds} resolve={id => functionNameById.get(id)} />
      <Evidence blockIds={activeQuestion.materialBlockIds} material={material} />
    </>
  }

  return <div className="readable-material" role="region" aria-label="材料整理结果">
    <div className="readable-material-tabs" role="tablist" aria-label="材料整理">
      {tabs.map((item) => <button
        key={item.key}
        type="button"
        role="tab"
        aria-selected={tab === item.key}
        className={`readable-material-tab${tab === item.key ? ' is-active' : ''}`}
        onClick={() => { setTab(item.key); setExpandedEvidence(null) }}
      >
        {item.label}
        <span className={`readable-material-count${item.key === 'questions' && tabCounts[item.key] ? ' is-warn' : ''}`}>{tabCounts[item.key]}</span>
      </button>)}
    </div>
    <div className="readable-material-page" role="tabpanel" aria-label={currentTab.label}>
      <header className="readable-material-head">
        {tab === 'functions' ? <>
          <div className="readable-material-stat"><span>功能</span><strong>{material.functions.length}</strong></div>
          <span className="readable-material-divider" aria-hidden="true" />
          <div className="readable-material-stat"><span>说明条目</span><strong>{allItems.length}</strong></div>
          <span className="readable-material-divider" aria-hidden="true" />
          <div className="readable-material-breakdown">
            <span><i className="readable-material-dot is-confirmed" aria-hidden="true" />明确 {statusCounts.confirmed}</span>
            <span><i className="readable-material-dot is-unconfirmed" aria-hidden="true" />待确认 {statusCounts.unconfirmed}</span>
            <span><i className="readable-material-dot is-conflicting" aria-hidden="true" />有冲突 {statusCounts.conflicting}</span>
            <span><i className="readable-material-dot is-example" aria-hidden="true" />示例 {statusCounts.example}</span>
          </div>
        </> : <>
          <div className="readable-material-stat"><span>待确认</span><strong>{material.questions.length}</strong></div>
          <span className="readable-material-divider" aria-hidden="true" />
          <div className="readable-material-related">
            <span>整体 {generalQuestions.length}</span>
            <span>功能相关 {material.questions.length - generalQuestions.length}</span>
          </div>
        </>}
        <span className="readable-material-hint">{currentTab.hint}</span>
      </header>

      <div className="readable-material-split">
        {tab === 'functions' ? <aside className="readable-material-list" aria-label="功能列表">
          {material.functions.map((feature) => {
            const featureItems = itemsOf(feature)
            const featureQuestions = material.questions.filter(question => question.functionIds.includes(feature.id)).length
            return <button
              type="button"
              key={feature.id}
              className={`readable-material-row${feature.id === activeFunction?.id ? ' is-active' : ''}`}
              onClick={() => selectFunction(feature.id)}
            >
              <span className="readable-material-row-id">{feature.id}</span>
              <span className="readable-material-row-main">
                <span className="readable-material-row-title">{feature.name || '未命名功能'}</span>
                <span className="readable-material-row-meta">{feature.sections.length} 章 · {featureItems.length} 条{featureQuestions ? ` · ${featureQuestions} 个待确认` : ''}</span>
              </span>
            </button>
          })}
          {!material.functions.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无功能" /> : null}
        </aside> : <aside className="readable-material-list" aria-label="待确认问题列表">
          {material.questions.map((question, index) => <button
            type="button"
            key={`${question.id}-${index}`}
            className={`readable-material-row${index === safeQuestionIndex ? ' is-active' : ''}`}
            onClick={() => setQuestionIndex(index)}
          >
            <span className="readable-material-row-id">{question.id || index + 1}</span>
            <span className="readable-material-row-main">
              <span className="readable-material-row-title">{question.question || '未记录问题'}</span>
              <Tag color={question.functionIds.length ? undefined : 'blue'}>{questionScope(question)}</Tag>
            </span>
          </button>)}
          {!material.questions.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待确认问题" /> : null}
        </aside>}
        <section className="readable-material-detail" aria-label={`${currentTab.label}详情`}>
          {tab === 'functions' ? renderFunctionDetail() : renderQuestionDetail()}
        </section>
      </div>
    </div>
  </div>
}
