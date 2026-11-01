import { pendingRequirementQuestions } from '@/domain/requirements/requirementArtifact'
import { RequirementArtifactValue } from '@/domain/requirements/RequirementArtifactView'
import { SearchOutlined } from '@ant-design/icons'
import { Alert, Collapse, Empty, Input, Segmented, Select, Tag } from 'antd'
import { useMemo, useState } from 'react'
import { extractedFactText, readExtractionArtifact, type ExtractionArtifact, type MaterialQuestion } from '../utils/materialComparison'
import { PendingQuestionsLabel } from './PendingQuestionsLabel'
import { useViewMotion } from '@/shared/ui/useViewMotion'
import '../styles/material-comparison.css'

const categories: Record<string, string> = { scope: '范围', actor: '角色', entry: '入口', operation: '操作', control: '控件', option: '选项', default: '默认值', trigger: '触发', dependency: '联动', result: '结果', pagination: '分页', sorting: '排序', validation: '校验', business_rule: '业务规则', other: '其他' }
const statuses: Record<string, { label: string; color?: string }> = { confirmed: { label: '有明确依据', color: 'success' }, unconfirmed: { label: '待确认', color: 'warning' }, conflicting: { label: '存在冲突', color: 'error' }, example: { label: '示例', color: 'blue' }, not_applicable: { label: '不适用' } }

function Questions({ artifact, questions }: { artifact: ExtractionArtifact; questions: MaterialQuestion[] }) {
  if (!questions.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待确认问题" />
  return <Collapse ghost accordion items={questions.map(q => ({
    key: q.id,
    label: <span className="requirement-material-question-label"><span>{q.question}</span><Tag color="warning">未解决</Tag></span>,
    children: <RequirementArtifactValue artifact={artifact} value={q} />,
  }))} />
}

function ComparisonContent({ artifact }: { artifact: ExtractionArtifact }) {
  const [expandedFactId, setExpandedFactId] = useState<string | undefined>(() => artifact.extractedFacts[0]?.id)
  const [selectedTab, setTab] = useState('facts')
  const pendingQuestions = pendingRequirementQuestions(artifact.questions)
  const tab = selectedTab === 'questions' && !pendingQuestions.length ? 'facts' : selectedTab
  const panelRef = useViewMotion(tab === 'facts' ? 0 : 1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const facts = artifact.extractedFacts.filter(f => (status === 'all' || f.fact.confirmationStatus === status) && extractedFactText(artifact, f).includes(search))
  const questions = pendingQuestions.filter(q => q.question.includes(search))

  return <div className="requirement-material-comparison" role="region" aria-label="材料提取结果" tabIndex={0}>
    <section className="requirement-material-panel">
      <div className="requirement-material-filter">{pendingQuestions.length > 0 && <Segmented className="tab-view-switch" aria-label="提取内容分类" value={tab} onChange={value => { setTab(String(value)); setSearch('') }} options={[{ value: 'facts', label: '提取的事实' }, { value: 'questions', label: <PendingQuestionsLabel count={pendingQuestions.length} /> }]} />}<Input aria-label={tab === 'facts' ? '搜索事实' : '搜索问题'} placeholder={tab === 'facts' ? '搜索事实内容' : '搜索待确认问题'} prefix={<SearchOutlined />} allowClear value={search} onChange={e => setSearch(e.target.value)} />{tab === 'facts' && <Select aria-label="事实确认状态" value={status} onChange={setStatus} options={[{ value: 'all', label: '全部状态' }, ...Object.entries(statuses).map(([value, meta]) => ({ value, label: meta.label }))]} />}</div>
      <div ref={panelRef} className="requirement-material-extracted" role="region" aria-label={tab === 'facts' ? '提取事实' : '待确认问题'} tabIndex={0}>
        {tab === 'questions' ? <Questions artifact={artifact} questions={questions} /> : facts.length ? facts.map(f => {
          const active = expandedFactId === f.id
          const meta = statuses[f.fact.confirmationStatus] ?? { label: f.fact.confirmationStatus }
          return <article key={f.id} className={`requirement-material-fact${active ? ' is-selected' : ''}`}>
            <button className="requirement-material-fact-select" aria-label={`查看依据：${extractedFactText(artifact, f)}`} aria-expanded={active} aria-pressed={active} onClick={() => setExpandedFactId(current => current === f.id ? undefined : f.id)}>
              <span className="requirement-material-fact-meta"><Tag>{categories[f.category] ?? f.category}</Tag><Tag color={meta.color}>{meta.label}</Tag></span>
              <span className="requirement-material-fact-text">{extractedFactText(artifact, f)}</span>
              <span className="requirement-material-fact-locator">{f.fact.sourceReferences.map(r => r.locator).join('；') || '来源尚未明确'}</span>
            </button>
            {active && <div className="requirement-material-fact-evidence">
              <strong>依据来源与摘录</strong>
              {f.fact.sourceReferences.map((ref, index) => <div key={index}><span className="requirement-material-evidence-source">{artifact.sources.find(s => s.id === ref.sourceId)?.name ?? ref.sourceId}</span>{ref.excerpt && <blockquote>{ref.excerpt}</blockquote>}</div>)}
              {pendingQuestions.some(q => f.fact.relatedQuestionIds.includes(q.id)) && <Questions artifact={artifact} questions={pendingQuestions.filter(q => f.fact.relatedQuestionIds.includes(q.id))} />}
            </div>}
          </article>
        }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配的提取事实" />}
      </div>
    </section>
  </div>
}

export function RequirementMaterialComparison({ content }: { content: unknown }) {
  const result = useMemo(() => { try { return { artifact: readExtractionArtifact(content) } } catch (error) { return { error: error instanceof Error ? error.message : '材料提取内容无法读取' } } }, [content])
  if (!result.artifact) return <Alert type="error" showIcon title={result.error} />
  const artifact = result.artifact
  return <div className="requirement-material-host requirement-extraction-workspace">
    <ComparisonContent artifact={artifact} />
  </div>
}
