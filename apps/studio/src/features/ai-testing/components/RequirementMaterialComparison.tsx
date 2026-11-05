import { pendingRequirementQuestions } from '@/domain/requirements/requirementArtifact'
import { RequirementArtifactValue } from '@/domain/requirements/RequirementArtifactView'
import { SearchOutlined } from '@ant-design/icons'
import { Alert, Collapse, Empty, Input, Segmented, Select, Tag } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { extractedFactText, readExtractionArtifact, type ExtractionArtifact, type ExtractedFact, type MaterialQuestion } from '../utils/materialComparison'
import { PendingQuestionsLabel } from './PendingQuestionsLabel'
import { useViewMotion } from '@/shared/ui/useViewMotion'
import '../styles/material-comparison.css'

const categories: Record<string, string> = { scope: '范围', actor: '角色', entry: '入口', operation: '操作', control: '控件', option: '选项', default: '默认值', trigger: '触发', dependency: '联动', result: '结果', pagination: '分页', sorting: '排序', validation: '校验', business_rule: '业务规则', other: '其他' }
const statuses: Record<string, { label: string; color?: string }> = { confirmed: { label: '有明确依据', color: 'success' }, unconfirmed: { label: '待确认', color: 'warning' }, conflicting: { label: '存在冲突', color: 'error' }, example: { label: '示例', color: 'blue' }, not_applicable: { label: '不适用' } }
const questionStatuses: Record<string, string> = { open: '未解决', resolved: '已答复' }

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
  const [expandedFactId, setExpandedFactId] = useState<string | undefined>(() => artifact.extractedFacts[0]?.id)
  const [selectedTab, setTab] = useState('facts')
  const pendingQuestions = pendingRequirementQuestions(artifact.questions)
  const tab = selectedTab === 'questions' && !pendingQuestions.length ? 'facts' : selectedTab
  const panelRef = useViewMotion(tab === 'facts' ? 0 : 1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const facts = artifact.extractedFacts.filter(f => (status === 'all' || f.fact.confirmationStatus === status) && extractedFactText(artifact, f).includes(search))
  const questions = pendingQuestions.filter(q => q.question.includes(search))
  const editing = Boolean(editable && onEdit)
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

  return <div className="requirement-material-comparison" role="region" aria-label="材料提取结果" tabIndex={0}>
    <section className="requirement-material-panel">
      <div className="requirement-material-filter">{pendingQuestions.length > 0 && <Segmented className="tab-view-switch" aria-label="提取内容分类" value={tab} onChange={value => { setTab(String(value)); setSearch('') }} options={[{ value: 'facts', label: '提取的事实' }, { value: 'questions', label: <PendingQuestionsLabel count={pendingQuestions.length} /> }]} />}<Input aria-label={tab === 'facts' ? '搜索事实' : '搜索问题'} placeholder={tab === 'facts' ? '搜索事实内容' : '搜索待确认问题'} prefix={<SearchOutlined />} allowClear value={search} onChange={e => setSearch(e.target.value)} />{tab === 'facts' && <Select aria-label="事实确认状态" value={status} onChange={setStatus} options={[{ value: 'all', label: '全部状态' }, ...Object.entries(statuses).map(([value, meta]) => ({ value, label: meta.label }))]} />}</div>
      <div ref={panelRef} className="requirement-material-extracted" role="region" aria-label={tab === 'facts' ? '提取事实' : '待确认问题'} tabIndex={0}>
        {tab === 'questions' ? <Questions artifact={artifact} questions={questions} editable={editing} onUpdateQuestion={updateQuestion} /> : facts.length ? facts.map(f => {
          const active = expandedFactId === f.id
          const meta = statuses[f.fact.confirmationStatus] ?? { label: f.fact.confirmationStatus }
          return <article key={f.id} className={`requirement-material-fact${active ? ' is-selected' : ''}${editing ? ' is-editing' : ''}`}>
            {editing ? <div className="requirement-material-fact-edit">
              <FactEditor fact={f}
                onChangeValue={value => updateFact(f.id, { value })}
                onChangeCategory={value => updateFact(f.id, { category: value })}
                onChangeStatus={value => updateFact(f.id, { confirmationStatus: value })} />
              <button type="button" className="requirement-material-fact-locator requirement-material-fact-evidence-toggle"
                aria-label={`查看依据：${extractedFactText(artifact, f)}`} aria-expanded={active}
                onClick={() => setExpandedFactId(current => current === f.id ? undefined : f.id)}>
                {f.fact.sourceReferences.map(r => r.locator).join('；') || '来源尚未明确'} · {active ? '收起依据' : '查看依据'}
              </button>
            </div> : <button className="requirement-material-fact-select" aria-label={`查看依据：${extractedFactText(artifact, f)}`} aria-expanded={active} aria-pressed={active} onClick={() => setExpandedFactId(current => current === f.id ? undefined : f.id)}>
              <span className="requirement-material-fact-meta"><Tag>{categories[f.category] ?? f.category}</Tag><Tag color={meta.color}>{meta.label}</Tag></span>
              <span className="requirement-material-fact-text">{extractedFactText(artifact, f)}</span>
              <span className="requirement-material-fact-locator">{f.fact.sourceReferences.map(r => r.locator).join('；') || '来源尚未明确'}</span>
            </button>}
            {active && <div className="requirement-material-fact-evidence">
              <strong>依据来源与摘录</strong>
              {f.fact.sourceReferences.map((ref, index) => <div key={index}><span className="requirement-material-evidence-source">{artifact.sources.find(s => s.id === ref.sourceId)?.name ?? ref.sourceId}</span>{ref.excerpt && <blockquote>{ref.excerpt}</blockquote>}</div>)}
              {pendingQuestions.some(q => f.fact.relatedQuestionIds.includes(q.id)) && <Questions artifact={artifact} editable={editing} onUpdateQuestion={updateQuestion} questions={pendingQuestions.filter(q => f.fact.relatedQuestionIds.includes(q.id))} />}
            </div>}
          </article>
        }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配的提取事实" />}
      </div>
    </section>
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
