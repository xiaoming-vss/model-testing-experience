import { pendingRequirementQuestions } from '@/domain/requirements/requirementArtifact'
import { RequirementArtifactValue } from '@/domain/requirements/RequirementArtifactView'
import { FileTextOutlined, SearchOutlined } from '@ant-design/icons'
import { Alert, Collapse, Empty, Input, Segmented, Select, Tag } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { extractedFactText, readExtractionArtifact, type ExtractionArtifact, type ExtractedFact, type MaterialQuestion } from '../utils/materialComparison'
import { PendingQuestionsLabel } from './PendingQuestionsLabel'
import { useViewMotion } from '@/shared/ui/useViewMotion'
import '../styles/material-comparison.css'

const categories: Record<string, string> = { scope: '范围', actor: '角色', entry: '入口', operation: '操作', control: '控件', option: '选项', default: '默认值', trigger: '触发', dependency: '联动', result: '结果', pagination: '分页', sorting: '排序', validation: '校验', business_rule: '业务规则', other: '其他' }
const statuses: Record<string, { label: string; color?: string }> = { confirmed: { label: '有明确依据', color: 'success' }, unconfirmed: { label: '待确认', color: 'warning' }, conflicting: { label: '存在冲突', color: 'error' }, example: { label: '示例', color: 'blue' }, not_applicable: { label: '不适用' } }
const questionStatuses: Record<string, string> = { open: '未解决', resolved: '已答复' }

/** 用首条来源定位生成事实所属章节，避免在列表里重复整段来源路径。 */
function factSectionLabel(fact: ExtractedFact) {
  const locator = fact.fact.sourceReferences[0]?.locator ?? ''
  const parts = locator.split('/').map(part => part.trim()).filter(Boolean)
  if (!parts.length) return '来源未标注章节'
  if (parts.length > 1 && /^[12]\./.test(parts[0])) return `${parts[0]} / ${parts[1]}`
  return parts[0]
}

type ArtifactMutation = (mutate: (raw: Record<string, unknown>) => void) => void
type FactUpdate = (factId: string, patch: { category?: string; confirmationStatus?: string; value?: unknown }) => void
type QuestionUpdate = (questionId: string, patch: { question?: string; status?: string; answer?: unknown }) => void

const asRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)

function readArtifactSource(content: unknown): Record<string, unknown> | null {
  if (typeof content === 'string') {
    try {
      const parsed: unknown = JSON.parse(content)
      return asRecord(parsed) ? parsed : null
    } catch {
      return null
    }
  }
  return asRecord(content) ? structuredClone(content) : null
}

function FactEditor({ fact, onChangeValue, onChangeCategory, onChangeStatus }: {
  fact: ExtractedFact
  onChangeValue: (value: unknown) => void
  onChangeCategory: (value: string) => void
  onChangeStatus: (value: string) => void
}) {
  const value = fact.fact.value
  const multiline = Array.isArray(value)
  const text = multiline ? value.map(String).join('\n') : value == null ? '' : String(value)
  /*
   * 事实正文先在本地保存草稿，停止输入后再回写整份产物：
   * 每敲一个字都 JSON.parse + stringify 整个材料在事实较多时会明显卡顿。
   */
  const [draft, setDraft] = useState(text)
  const draftRef = useRef(text)
  const committedRef = useRef(text)
  const timerRef = useRef<number | undefined>(undefined)
  const commitRef = useRef({ text, multiline, value, onChangeValue })
  useEffect(() => {
    commitRef.current = { text, multiline, value, onChangeValue }
  }, [multiline, onChangeValue, text, value])
  useEffect(() => {
    setDraft(text)
    draftRef.current = text
    committedRef.current = text
    window.clearTimeout(timerRef.current)
  }, [text])
  // 输入后 150ms 内切换页签/视图会卸载编辑器，未提交的草稿要在卸载前回写。
  useEffect(() => () => {
    window.clearTimeout(timerRef.current)
    const current = commitRef.current
    const pending = draftRef.current
    if (pending === current.text || pending === committedRef.current) return
    if (current.multiline) current.onChangeValue(pending.split(/\r?\n/).map(line => line.trim()).filter(Boolean))
    else current.onChangeValue(pending || (current.value == null ? null : ''))
  }, [])
  function commit(next: string) {
    const current = commitRef.current
    if (next === current.text) return
    committedRef.current = next
    if (current.multiline) current.onChangeValue(next.split(/\r?\n/).map(line => line.trim()).filter(Boolean))
    else current.onChangeValue(next || (current.value == null ? null : ''))
  }
  function handleChange(next: string) {
    setDraft(next)
    draftRef.current = next
    window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => commit(next), 150)
  }
  return <div className="requirement-material-fact-edit">
    <div className="requirement-material-fact-meta">
      <Select size="small" variant="borderless" className="requirement-material-fact-category" aria-label={`事实分类 ${fact.id}`}
        value={fact.category} options={Object.entries(categories).map(([key, label]) => ({ value: key, label }))} onChange={onChangeCategory} />
      <Select size="small" variant="borderless" className="requirement-material-fact-status" aria-label={`确认状态 ${fact.id}`}
        value={fact.fact.confirmationStatus} options={Object.entries(statuses).map(([key, meta]) => ({ value: key, label: meta.label }))} onChange={onChangeStatus} />
    </div>
    <Input.TextArea aria-label={`事实内容 ${fact.id}`} variant="borderless" autoSize={{ minRows: 1, maxRows: 8 }}
      className="requirement-material-fact-editor" value={draft} placeholder="未明确，可直接填写"
      onChange={event => handleChange(event.target.value)}
      onBlur={event => {
        window.clearTimeout(timerRef.current)
        commit(event.target.value)
      }} />
  </div>
}

function Questions({ artifact, questions, editable = false, onUpdateQuestion }: {
  artifact: ExtractionArtifact
  questions: MaterialQuestion[]
  editable?: boolean
  onUpdateQuestion?: QuestionUpdate
}) {
  if (!questions.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待确认问题" />
  if (editable && onUpdateQuestion) return <div className="requirement-material-question-list">
    {questions.map(q => <section className="requirement-material-question" key={q.id}>
      <div className="requirement-material-question-head">
        <Input.TextArea aria-label={`问题内容 ${q.id}`} variant="borderless" autoSize={{ minRows: 1, maxRows: 6 }}
          value={q.question} onChange={event => onUpdateQuestion(q.id, { question: event.target.value })} placeholder="填写待确认问题" />
        <Select size="small" variant="borderless" aria-label={`问题状态 ${q.id}`} value={q.status}
          options={Object.entries(questionStatuses).map(([value, label]) => ({ value, label }))}
          onChange={value => onUpdateQuestion(q.id, { status: value })} />
      </div>
      {q.answer == null || typeof q.answer === 'string'
        ? <Input.TextArea aria-label={`问题答复 ${q.id}`} variant="borderless" autoSize={{ minRows: 1, maxRows: 6 }}
          value={q.answer ?? ''} placeholder="填写答复后可将问题标记为已答复" onChange={event => onUpdateQuestion(q.id, { answer: event.target.value || null })} />
        : null}
      <details className="requirement-material-question-detail">
        <summary>影响与依据</summary>
        <RequirementArtifactValue artifact={artifact} value={Object.fromEntries([
          ['impacts', q.impacts],
          ['affectedRefs', q.affectedRefs],
          ['sourceReferences', q.sourceReferences],
          ...(typeof q.answer === 'object' ? [['answer', q.answer]] : []),
        ])} />
      </details>
    </section>)}
  </div>
  return <Collapse ghost accordion items={questions.map(q => ({
    key: q.id,
    label: <span className="requirement-material-question-label"><span>{q.question}</span><Tag color="warning">未解决</Tag></span>,
    children: <RequirementArtifactValue artifact={artifact} value={q} />,
  }))} />
}

function ComparisonContent({ artifact, editable = false, onEdit }: { artifact: ExtractionArtifact; editable?: boolean; onEdit?: ArtifactMutation }) {
  const [selectedTab, setTab] = useState('facts')
  const [selectedCategory, setCategory] = useState('all')
  const [selectedFactId, setSelectedFactId] = useState<string | undefined>(() => artifact.extractedFacts[0]?.id)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const pendingQuestions = pendingRequirementQuestions(artifact.questions)
  const tab = selectedTab === 'questions' && !pendingQuestions.length ? 'facts' : selectedTab
  const panelRef = useViewMotion(tab === 'facts' ? 0 : 1)
  const editing = Boolean(editable && onEdit)

  const filteredFacts = useMemo(() => artifact.extractedFacts.filter(fact =>
    (status === 'all' || fact.fact.confirmationStatus === status)
    && (selectedCategory === 'all' || fact.category === selectedCategory)
    && extractedFactText(artifact, fact).includes(search),
  ), [artifact, search, selectedCategory, status])
  const filteredQuestions = useMemo(
    () => pendingQuestions.filter(question => question.question.includes(search)),
    [pendingQuestions, search],
  )
  useEffect(() => {
    if (tab !== 'facts') return
    if (filteredFacts.some(fact => fact.id === selectedFactId)) return
    setSelectedFactId(filteredFacts[0]?.id)
  }, [filteredFacts, selectedFactId, tab])
  const activeFact = filteredFacts.find(fact => fact.id === selectedFactId) ?? filteredFacts[0]
  const categoryCounts = useMemo(
    () => Object.entries(categories)
      .map(([key, label]) => ({ key, label, count: artifact.extractedFacts.filter(fact => fact.category === key).length }))
      .filter(item => item.count > 0),
    [artifact.extractedFacts],
  )
  const maxCategoryCount = Math.max(1, ...categoryCounts.map(item => item.count))
  const groupedFacts = useMemo(() => {
    if (selectedCategory !== 'all') return [{ label: undefined, facts: filteredFacts }]
    const groups: { label: string; facts: ExtractedFact[] }[] = []
    const indexes = new Map<string, number>()
    for (const fact of filteredFacts) {
      const label = factSectionLabel(fact)
      let index = indexes.get(label)
      if (index === undefined) {
        index = groups.length
        indexes.set(label, index)
        groups.push({ label, facts: [] })
      }
      groups[index].facts.push(fact)
    }
    return groups
  }, [filteredFacts, selectedCategory])
  const sourceName = (sourceId: string) => artifact.sources.find(source => source.id === sourceId)?.name ?? sourceId
  const relatedQuestions = activeFact
    ? pendingQuestions.filter(question => activeFact.fact.relatedQuestionIds.includes(question.id))
    : []

  const updateFact: FactUpdate = (factId, patch) => onEdit?.(raw => {
    const fact = (Array.isArray(raw.extractedFacts) ? raw.extractedFacts : []).find(item => asRecord(item) && item.id === factId)
    if (!asRecord(fact) || !asRecord(fact.fact)) return
    if (patch.category !== undefined) fact.category = patch.category
    if (patch.confirmationStatus !== undefined) fact.fact.confirmationStatus = patch.confirmationStatus
    if ('value' in patch) fact.fact.value = patch.value
  })
  const updateQuestion: QuestionUpdate = (questionId, patch) => onEdit?.(raw => {
    const question = (Array.isArray(raw.questions) ? raw.questions : []).find(item => asRecord(item) && item.id === questionId)
    if (!asRecord(question)) return
    if (patch.question !== undefined) question.question = patch.question
    if (patch.status !== undefined) question.status = patch.status
    if ('answer' in patch) question.answer = patch.answer
  })

  return <div className={`requirement-material-comparison${tab === 'questions' ? ' is-questions' : ''}`} role="region" aria-label="材料提取结果" tabIndex={0}>
    {tab === 'facts' ? <aside className="requirement-material-rail" aria-label="事实分类">
      <div className="requirement-material-summary">
        <div><b>{artifact.extractedFacts.length}</b><span>提取事实</span></div>
        <div><b>{artifact.extractedFacts.filter(fact => fact.category === 'business_rule').length}</b><span>业务规则</span></div>
        <div><b>{artifact.sources.length}</b><span>来源文件</span></div>
      </div>
      <section className="requirement-material-rail-block">
        <h3>按分类浏览</h3>
        <button type="button" className={`requirement-material-cat-row${selectedCategory === 'all' ? ' is-active' : ''}`}
          aria-pressed={selectedCategory === 'all'} onClick={() => setCategory('all')}>
          <span>全部事实</span><span className="requirement-material-cat-count">{artifact.extractedFacts.length}</span>
        </button>
        {categoryCounts.map(item => <button type="button" key={item.key}
          className={`requirement-material-cat-row${selectedCategory === item.key ? ' is-active' : ''}`}
          aria-pressed={selectedCategory === item.key} onClick={() => setCategory(item.key)}>
          <span>{item.label}</span>
          <span className="requirement-material-cat-bar" aria-hidden="true"><i style={{ width: `${Math.max(8, item.count / maxCategoryCount * 100)}%` }} /></span>
          <span className="requirement-material-cat-count">{item.count}</span>
        </button>)}
      </section>
      <section className="requirement-material-rail-block">
        <h3>来源文件</h3>
        {artifact.sources.map(source => <div className="requirement-material-source-card" key={source.id}>
          <FileTextOutlined aria-hidden />
          <span>{source.name}</span>
        </div>)}
      </section>
    </aside> : null}

    <section className="requirement-material-list">
      <div className="requirement-material-list-head">
        <div><h2>{tab === 'facts' ? '提取事实' : '待确认问题'}</h2><p>{tab === 'facts' ? `${filteredFacts.length} 条事实` : `${filteredQuestions.length} 个未解决问题`}</p></div>
        <Input aria-label={tab === 'facts' ? '搜索事实' : '搜索问题'} placeholder={tab === 'facts' ? '搜索事实内容' : '搜索待确认问题'} prefix={<SearchOutlined />} allowClear value={search} onChange={event => setSearch(event.target.value)} />
      </div>
      <div className="requirement-material-list-tools">
        {pendingQuestions.length > 0 ? <Segmented className="tab-view-switch" aria-label="提取内容分类" value={tab} onChange={value => { setTab(String(value)); setSearch('') }} options={[{ value: 'facts', label: '提取的事实' }, { value: 'questions', label: <PendingQuestionsLabel count={pendingQuestions.length} /> }]} /> : null}
        {tab === 'facts' ? <Select aria-label="事实确认状态" value={status} onChange={setStatus} options={[{ value: 'all', label: '全部状态' }, ...Object.entries(statuses).map(([value, meta]) => ({ value, label: meta.label }))]} /> : null}
        <span className="requirement-material-count">{tab === 'facts' ? `${filteredFacts.length} 条` : `${filteredQuestions.length} 个`}</span>
      </div>
      <div ref={panelRef} className="requirement-material-extracted" role="region" aria-label={tab === 'facts' ? '提取事实' : '待确认问题'} tabIndex={0}>
        {tab === 'questions' ? <Questions artifact={artifact} questions={filteredQuestions} editable={editing} onUpdateQuestion={updateQuestion} /> : filteredFacts.length ? groupedFacts.map(group => <div key={group.label ?? 'all'}>
          {group.label ? <div className="requirement-material-fact-group"><span>{group.label}</span><b>{group.facts.length}</b></div> : null}
          {group.facts.map(fact => {
            const meta = statuses[fact.fact.confirmationStatus] ?? { label: fact.fact.confirmationStatus }
            const active = activeFact?.id === fact.id
            const text = extractedFactText(artifact, fact)
            return <button type="button" key={fact.id} className={`requirement-material-fact-row${active ? ' is-selected' : ''}`}
              aria-label={`查看依据：${text}`} aria-pressed={active} onClick={() => setSelectedFactId(fact.id)}>
              <span className="requirement-material-fact-row-id">{fact.id}</span>
              <span className="requirement-material-fact-row-copy">
                <span className="requirement-material-fact-row-meta"><Tag>{categories[fact.category] ?? fact.category}</Tag><span>{fact.fact.sourceReferences.length} 条依据</span></span>
                <span className="requirement-material-fact-row-text">{text}</span>
                <span className="requirement-material-fact-row-locator">{factSectionLabel(fact)}</span>
              </span>
              <span className={`requirement-material-fact-row-state${meta.color ? ` is-${meta.color}` : ''}`}><i aria-hidden />{meta.label}</span>
            </button>
          })}
        </div>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配的提取事实" />}
      </div>
    </section>

    {tab === 'facts' ? <aside className="requirement-material-detail" aria-label="事实详情">
      {activeFact ? <>
        <div className="requirement-material-detail-head"><span className="requirement-material-detail-id">{activeFact.id}</span>{!editing ? <><Tag>{categories[activeFact.category] ?? activeFact.category}</Tag><Tag color={statuses[activeFact.fact.confirmationStatus]?.color}>{statuses[activeFact.fact.confirmationStatus]?.label ?? activeFact.fact.confirmationStatus}</Tag></> : null}</div>
        <div className="requirement-material-detail-section">{factSectionLabel(activeFact)}</div>
        {editing ? <FactEditor fact={activeFact}
          onChangeValue={value => updateFact(activeFact.id, { value })}
          onChangeCategory={value => updateFact(activeFact.id, { category: value })}
          onChangeStatus={value => updateFact(activeFact.id, { confirmationStatus: value })} />
          : <p className="requirement-material-detail-text">{extractedFactText(artifact, activeFact)}</p>}
        <div className="requirement-material-detail-meta"><span>{factSectionLabel(activeFact)}</span><span>{activeFact.fact.sourceReferences.length} 条依据</span></div>
        <section className="requirement-material-detail-evidence">
          <h4>依据与摘录</h4>
          {activeFact.fact.sourceReferences.map((ref, index) => <div className="requirement-material-evidence-item" key={`${ref.sourceId}-${index}`}>
            <span className="requirement-material-evidence-source">{sourceName(ref.sourceId)}</span>
            <span className="requirement-material-evidence-locator">{ref.locator}</span>
            {ref.excerpt ? <blockquote>{ref.excerpt}</blockquote> : null}
          </div>)}
        </section>
        {relatedQuestions.length ? <section className="requirement-material-detail-evidence">
          <h4>关联待确认问题</h4>
          <Questions artifact={artifact} questions={relatedQuestions} editable={editing} onUpdateQuestion={updateQuestion} />
        </section> : null}
      </> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一条事实查看详情" />}
    </aside> : null}
  </div>
}

export function RequirementMaterialComparison({ content, editable = false, onChange }: { content: unknown; editable?: boolean; onChange?: (content: string) => void }) {
  const result = useMemo(() => { try { return { artifact: readExtractionArtifact(content) } } catch (error) { return { error: error instanceof Error ? error.message : '材料提取内容无法读取' } } }, [content])
  const onEdit = useMemo<ArtifactMutation | undefined>(() => {
    if (!editable || !onChange) return undefined
    return mutate => {
      const raw = readArtifactSource(content)
      if (!raw) return
      mutate(raw)
      onChange(JSON.stringify(raw, null, 2))
    }
  }, [content, editable, onChange])
  if (!result.artifact) return <Alert type="error" showIcon title={result.error} />
  const artifact = result.artifact
  return <div className="requirement-material-host requirement-extraction-workspace">
    <ComparisonContent artifact={artifact} editable={editable} onEdit={onEdit} />
  </div>
}
