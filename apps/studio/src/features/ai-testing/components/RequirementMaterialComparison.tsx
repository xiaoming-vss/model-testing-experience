import { pendingRequirementQuestions } from '@/domain/requirements/requirementArtifact'
import { RequirementArtifactValue } from '@/domain/requirements/RequirementArtifactView'
import { LinkOutlined, SearchOutlined } from '@ant-design/icons'
import { Alert, Button, Collapse, Empty, Input, Segmented, Select, Tag } from 'antd'
import { useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react'
import { extractedFactText, materialTarget, readExtractionArtifact, sourceForSelection, type ExtractionArtifact, type MaterialQuestion, type MaterialSelection } from '../utils/materialComparison'
import { RequirementSourcePanel } from './RequirementSourcePanel'
import '../styles/material-comparison.css'

const categories: Record<string, string> = { scope: '范围', actor: '角色', entry: '入口', operation: '操作', control: '控件', option: '选项', default: '默认值', trigger: '触发', dependency: '联动', result: '结果', pagination: '分页', sorting: '排序', validation: '校验', business_rule: '业务规则', other: '其他' }
const statuses: Record<string, { label: string; color?: string }> = { confirmed: { label: '有明确依据', color: 'success' }, unconfirmed: { label: '待确认', color: 'warning' }, conflicting: { label: '存在冲突', color: 'error' }, example: { label: '示例', color: 'blue' }, not_applicable: { label: '不适用' } }

function Questions({ artifact, questions, onActivate }: { artifact: ExtractionArtifact; questions: MaterialQuestion[]; onActivate?: (id: string) => void }) {
  if (!questions.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待确认问题" />
  return <Collapse ghost accordion onChange={keys => { const id = Array.isArray(keys) ? keys[0] : keys; if (id) onActivate?.(String(id)) }} items={questions.map(q => ({
    key: q.id,
    label: <span className="requirement-material-question-label"><span>{q.question}</span><Tag color="warning">未解决</Tag></span>,
    children: <RequirementArtifactValue artifact={artifact} value={q} />,
  }))} />
}

function ComparisonContent({ artifact }: { artifact: ExtractionArtifact }) {
  const [selection, setSelection] = useState<MaterialSelection | undefined>(() => artifact.extractedFacts[0] ? { kind: 'fact', id: artifact.extractedFacts[0].id } : undefined)
  const [sourceId, setSourceId] = useState(() => selection ? sourceForSelection(artifact, selection) : artifact.sources[0]?.id)
  const [selectedTab, setTab] = useState('facts')
  const pendingQuestions = pendingRequirementQuestions(artifact.questions)
  const tab = selectedTab === 'questions' && !pendingQuestions.length ? 'facts' : selectedTab
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [locateVersion, requestLocate] = useReducer(v => v + 1, 0)
  const factPane = useRef<HTMLDivElement>(null)
  const factElements = useRef(new Map<string, HTMLElement>())
  const target = useMemo(() => materialTarget(artifact, selection), [artifact, selection])
  const facts = artifact.extractedFacts.filter(f => (status === 'all' || f.fact.confirmationStatus === status) && extractedFactText(artifact, f).includes(search))
  const questions = pendingQuestions.filter(q => q.question.includes(search))

  useLayoutEffect(() => {
    const right = factPane.current
    const selectedFact = selection?.kind === 'fact' && factElements.current.get(selection.id)
    if (right && selectedFact && locateVersion > 0) right.scrollTop = Math.max(0, right.scrollTop + selectedFact.getBoundingClientRect().top - right.getBoundingClientRect().top - 12)
  }, [locateVersion, selection]) // The material/fact refs are updated before this layout effect.

  function locate(next: MaterialSelection) {
    setSelection(next)
    setSourceId(sourceForSelection(artifact, next))
    requestLocate()
  }

  return <div className="requirement-material-comparison" role="region" aria-label="材料与提取结果对照" tabIndex={0}>
    <RequirementSourcePanel artifact={artifact} sources={artifact.sources} blocks={artifact.contentBlocks} sourceId={sourceId} onSourceChange={value => { setSourceId(value); requestLocate() }} linkedBlockIds={target.blockIds} locateVersion={locateVersion} />
    <section className="requirement-material-panel">
      <header className="requirement-material-panel-head">
        <Segmented aria-label="提取内容分类" value={tab} onChange={value => { setTab(String(value)); setSearch('') }} options={[{ value: 'facts', label: '提取的事实' }, ...(pendingQuestions.length ? [{ value: 'questions', label: '待确认问题' }] : [])]} />
        <span className="requirement-material-count">{tab === 'facts' ? `${artifact.extractedFacts.length} 条事实` : `${pendingQuestions.length} 个待确认问题`}</span>
      </header>
      <div className="requirement-material-filter"><Input aria-label={tab === 'facts' ? '搜索事实' : '搜索问题'} placeholder={tab === 'facts' ? '搜索事实内容' : '搜索待确认问题'} prefix={<SearchOutlined />} allowClear value={search} onChange={e => setSearch(e.target.value)} />{tab === 'facts' && <Select aria-label="事实确认状态" value={status} onChange={setStatus} options={[{ value: 'all', label: '全部状态' }, ...Object.entries(statuses).map(([value, meta]) => ({ value, label: meta.label }))]} />}</div>
      <div className="requirement-material-extracted" ref={factPane} role="region" aria-label={tab === 'facts' ? '提取事实' : '待确认问题'} tabIndex={0}>
        {tab === 'questions' ? <Questions artifact={artifact} questions={questions} onActivate={id => locate({ kind: 'question', id })} /> : facts.length ? facts.map(f => {
          const active = selection?.kind === 'fact' && selection.id === f.id
          const meta = statuses[f.fact.confirmationStatus] ?? { label: f.fact.confirmationStatus }
          return <article key={f.id} ref={element => { if (element) factElements.current.set(f.id, element); else factElements.current.delete(f.id) }} className={`requirement-material-fact${active ? ' is-selected' : ''}`}>
            <button className="requirement-material-fact-select" aria-label={`定位材料：${extractedFactText(artifact, f)}`} aria-pressed={active} onClick={() => locate({ kind: 'fact', id: f.id })}>
              <span className="requirement-material-fact-meta"><Tag>{categories[f.category] ?? f.category}</Tag><Tag color={meta.color}>{meta.label}</Tag><LinkOutlined /></span>
              <span className="requirement-material-fact-text">{extractedFactText(artifact, f)}</span>
              <span className="requirement-material-fact-locator">{f.fact.sourceReferences.map(r => r.locator).join('；') || '来源尚未明确'}</span>
            </button>
            {active && <div className="requirement-material-fact-evidence">
              <strong>依据来源与摘录</strong>
              {f.fact.sourceReferences.map((ref, index) => <div key={index}><Button type="link" size="small" onClick={() => { setSourceId(ref.sourceId); requestLocate() }}>{artifact.sources.find(s => s.id === ref.sourceId)?.name ?? ref.sourceId}</Button>{ref.excerpt && <blockquote>{ref.excerpt}</blockquote>}</div>)}
              {pendingQuestions.some(q => f.fact.relatedQuestionIds.includes(q.id)) && <Questions artifact={artifact} questions={pendingQuestions.filter(q => f.fact.relatedQuestionIds.includes(q.id))} />}
            </div>}
          </article>
        }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配的提取事实" />}
      </div>
      <footer className="requirement-material-panel-foot"><span><LinkOutlined /> 选择事实或问题，对照对应材料</span></footer>
    </section>
  </div>
}

export function RequirementMaterialComparison({ content }: { content: unknown }) {
  const result = useMemo(() => { try { return { artifact: readExtractionArtifact(content) } } catch (error) { return { error: error instanceof Error ? error.message : '材料提取内容无法读取' } } }, [content])
  if (!result.artifact) return <Alert type="error" showIcon title={result.error} />
  const artifact = result.artifact
  return <div className="requirement-material-host">
    <div className="requirement-material-overview"><strong>{artifact.documentTitle}</strong><span>{artifact.sources.length} 个来源 · {artifact.contentBlocks.length} 个内容块 · {artifact.extractedFacts.length} 条事实 · {pendingRequirementQuestions(artifact.questions).length} 个待确认问题</span></div>
    <ComparisonContent artifact={artifact} />
  </div>
}
