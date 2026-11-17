import { useMemo, useState } from 'react'
import { Alert, Empty, Input, Tag } from 'antd'
import {
  ArtifactBreakdown,
  ArtifactDetailTitle,
  ArtifactDivider,
  ArtifactEmpty,
  ArtifactEvidence,
  ArtifactEvidenceItem,
  ArtifactEvidenceMissing,
  ArtifactField,
  ArtifactHeader,
  ArtifactKicker,
  ArtifactListRow,
  ArtifactRefChips,
  ArtifactSectionHead,
  ArtifactSplit,
  ArtifactStat,
  ArtifactTabs,
} from '@/shared/components/ArtifactView'
import { parseRequirementArtifact } from '../../../domain/requirements/requirementArtifact'

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
    return <div className="mt-2 overflow-x-auto"><table><tbody>{value.rows.map((row, i) => <tr key={i}>{Array.isArray(row) && row.map((cell, j) => {
      const span = spans.find(s => s.row === i && s.column === j)
      if (!span && spans.some(s => i >= s.row && i < s.row + s.rowSpan && j >= s.column && j < s.column + s.columnSpan)) return null
      return <td key={j} className="border border-app-surface-border px-2 py-1.5" rowSpan={span?.rowSpan} colSpan={span?.columnSpan}>{typeof cell === 'string' ? cell : '无法识别'}</td>
    })}</tr>)}</tbody></table></div>
  }
  if (block.kind === 'list' && Array.isArray(value.items)) return <ul className="m-0 pl-[18px] text-[11px] leading-[1.7] text-app-surface-text">{value.items.map((item, i) => <li key={i}>{String(item)}</li>)}</ul>
  if (block.kind === 'image') return <><p className="m-0 whitespace-pre-wrap text-[11px] leading-[1.6] text-app-surface-text [overflow-wrap:anywhere]">{typeof value.description === 'string' ? value.description : '图片内容未识别'}</p>{value.readStatus !== 'complete' && <small className="mt-1 block text-[10px] text-app-surface-text-muted">图片内容可能未完整识别，请核对原始材料。</small>}</>
  return <p className="m-0 whitespace-pre-wrap text-[11px] leading-[1.6] text-app-surface-text [overflow-wrap:anywhere]">{typeof value.text === 'string' ? value.text : '材料内容不可读取'}</p>
}

function itemsOf(feature: Material['functions'][number]) {
  return feature.sections.flatMap(section => section.items)
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

  const renderEvidence = (blockIds: string[]) => <ArtifactEvidence title="材料依据" count={blockIds.length} className="mt-2">
    {blockIds.map((id) => {
      const block = material.materialBlocks.find(item => item.id === id)
      if (!block) return <ArtifactEvidenceMissing key={id}>{id}：未找到对应材料</ArtifactEvidenceMissing>
      const source = material.sources.find(item => item.id === block.sourceId)
      return <ArtifactEvidenceItem key={id} source={source?.name || '来源未找到'} locator={block.locator}>
        <MaterialBlockContent block={block} />
      </ArtifactEvidenceItem>
    })}
  </ArtifactEvidence>

  const renderFunctionDetail = () => {
    if (!activeFunction) return <ArtifactEmpty className="h-full" description="暂无功能说明" />
    const sections = activeFunction.sections
      .map((section, index) => ({ section, index }))
      .filter(({ section }) => section.items.length > 0)
    if (!sections.length) return <ArtifactEmpty className="h-full" description="该功能暂无内容" />
    return <>
      <ArtifactKicker badge="功能说明">
        <span>{activeFunction.id}</span>
      </ArtifactKicker>
      <ArtifactDetailTitle>{activeFunction.name || '未命名功能'}</ArtifactDetailTitle>
      <div className="mt-4">
        {sections.map(({ section, index: sectionIndex }) => <section className="[&+&]:mt-[18px] [&+&]:border-t [&+&]:border-app-surface-border [&+&]:pt-[14px]" key={`${section.title}-${sectionIndex}`}>
          <ArtifactSectionHead as="h3" title={section.title || '未命名章节'} count={`${section.items.length} 条`} spacing="tight" />
          {section.items.map((item, itemIndex) => {
            const evidenceKey = `${activeFunction.id}:${sectionIndex}:${itemIndex}`
            const evidenceOpen = expandedEvidence === evidenceKey
            const itemStatus = statusLabels[item.status]
            return <article className="border-b border-app-surface-border py-2.5 last:border-b-0 last:pb-0" key={evidenceKey}>
              <div>
                {editable && onChange
                  ? <Input.TextArea
                    className="w-full text-[11.5px] leading-[1.7]"
                    aria-label={`${activeFunction.name} ${section.title} 内容 ${itemIndex + 1}`}
                    autoSize
                    value={item.text}
                    onChange={event => updateItem(activeFunction.id, sectionIndex, itemIndex, event.target.value)}
                  />
                  : <p className="m-0 whitespace-pre-wrap text-[11.5px] leading-[1.7] text-app-surface-text [overflow-wrap:anywhere]">{item.text}</p>}
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  {itemStatus && item.status !== 'confirmed' ? <Tag color={itemStatus.color}>{itemStatus.label}</Tag> : null}
                  {item.materialBlockIds.length ? <button
                    type="button"
                    className="rounded-[3px] border-0 bg-transparent p-0 text-[10px] text-app-accent hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-app-accent"
                    aria-expanded={evidenceOpen}
                    onClick={() => setExpandedEvidence(evidenceOpen ? null : evidenceKey)}
                  >依据 {item.materialBlockIds.length}</button> : null}
                </div>
              </div>
              {evidenceOpen ? renderEvidence(item.materialBlockIds) : null}
            </article>
          })}
        </section>)}
      </div>
    </>
  }

  const renderQuestionDetail = () => {
    if (!activeQuestion) return <ArtifactEmpty className="h-full" description="暂无待确认问题" />
    return <>
      <ArtifactKicker badge="待确认">
        <span>{activeQuestion.id || '问题'}</span>
        <Tag color={activeQuestion.functionIds.length ? undefined : 'blue'}>{questionScope(activeQuestion)}</Tag>
      </ArtifactKicker>
      {editable && onChange
        ? <label className="mt-3 flex flex-col gap-1.5">
          <span className="text-[10px] text-app-surface-text-muted">问题</span>
          <Input.TextArea
            aria-label={`待确认问题 ${safeQuestionIndex + 1}`}
            autoSize
            value={activeQuestion.question}
            onChange={event => updateQuestion(activeQuestion.id, event.target.value)}
          />
        </label>
        : <ArtifactDetailTitle>{activeQuestion.question || '未记录问题'}</ArtifactDetailTitle>}
      <ArtifactField className="mt-3" label="原因" value={activeQuestion.reason} />
      <ArtifactRefChips className="mt-4" title="关联功能" values={activeQuestion.functionIds} resolve={id => functionNameById.get(id)} />
      {renderEvidence(activeQuestion.materialBlockIds)}
    </>
  }

  return <div className="flex h-full min-h-0 flex-col bg-app-surface" role="region" aria-label="材料整理结果">
    <ArtifactTabs
      ariaLabel="材料整理"
      active={tab}
      onChange={(key) => { setTab(key); setExpandedEvidence(null) }}
      tabs={tabs.map(item => ({
        key: item.key,
        label: item.label,
        count: tabCounts[item.key],
        tone: item.key === 'questions' && tabCounts[item.key] ? 'warn' : undefined,
      }))}
    />
    <div className="flex min-h-0 flex-1 flex-col gap-2.5 px-3 pb-3 pt-2.5 max-narrow:overflow-auto" role="tabpanel" aria-label={currentTab.label}>
      <ArtifactHeader hint={currentTab.hint} hintClassName="max-narrow:hidden">
        {tab === 'functions' ? <>
          <ArtifactStat label="功能" value={material.functions.length} />
          <ArtifactDivider />
          <ArtifactStat label="说明条目" value={allItems.length} />
          <ArtifactDivider />
          <ArtifactBreakdown items={[
            { label: '明确', value: statusCounts.confirmed, dot: 'ok' },
            { label: '待确认', value: statusCounts.unconfirmed, dot: 'warn' },
            { label: '有冲突', value: statusCounts.conflicting, dot: 'danger' },
            { label: '示例', value: statusCounts.example, dot: 'accent' },
          ]} />
        </> : <>
          <ArtifactStat label="待确认" value={material.questions.length} />
          <ArtifactDivider />
          <ArtifactBreakdown items={[
            { label: '整体', value: generalQuestions.length },
            { label: '功能相关', value: material.questions.length - generalQuestions.length },
          ]} />
        </>}
      </ArtifactHeader>

      <ArtifactSplit
        listLabel={tab === 'functions' ? '功能列表' : '待确认问题列表'}
        detailLabel={`${currentTab.label}详情`}
        list={tab === 'functions'
          ? <>
            {material.functions.map((feature) => {
              const featureItems = itemsOf(feature)
              const featureQuestions = material.questions.filter(question => question.functionIds.includes(feature.id)).length
              return <ArtifactListRow
                key={feature.id}
                id={feature.id}
                title={feature.name || '未命名功能'}
                meta={`${feature.sections.length} 章 · ${featureItems.length} 条${featureQuestions ? ` · ${featureQuestions} 个待确认` : ''}`}
                active={feature.id === activeFunction?.id}
                onClick={() => selectFunction(feature.id)}
              />
            })}
            {!material.functions.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无功能" /> : null}
          </>
          : <>
            {material.questions.map((question, index) => <ArtifactListRow
              key={`${question.id}-${index}`}
              id={question.id || index + 1}
              title={question.question || '未记录问题'}
              active={index === safeQuestionIndex}
              onClick={() => setQuestionIndex(index)}
            >
              <Tag color={question.functionIds.length ? undefined : 'blue'}>{questionScope(question)}</Tag>
            </ArtifactListRow>)}
            {!material.questions.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待确认问题" /> : null}
          </>}
        detail={tab === 'functions' ? renderFunctionDetail() : renderQuestionDetail()}
      />
    </div>
  </div>
}
