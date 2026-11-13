import { useMemo, useRef, useState } from 'react'
import { Alert, Input } from 'antd'
import { parseRequirementArtifact } from '../../../domain/requirements/requirementArtifact'
import { downloadStoredFile } from '../../../shared/api/files'
import { saveBlob } from '../../../shared/utils/download'
import '../styles/readable-requirement-material.css'

export type MaterialBlock = { id: string; sourceId: string; kind: string; locator: string; content: Record<string, unknown> }
type Source = { id: string; name: string; location: string | null }
type Item = { text: string; status: string; materialBlockIds: string[] }
type Section = { title: string; items: Item[] }
type Material = { artifactType: string; title: string; sources: Source[]; materialBlocks: MaterialBlock[]; functions: { id: string; name: string; sections: Section[] }[]; questions: { id: string; question: string; reason: string; materialBlockIds: string[]; functionIds: string[] }[] }
const statusLabels: Record<string, string> = { unconfirmed: '待确认', conflicting: '有冲突', example: '示例' }
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

const categories = ['功能目标与背景', '页面入口', '功能使用与业务规则', '完整业务流程', '待确认问题'] as const

export function ReadableRequirementMaterial({ content, editable, onChange }: { content: unknown; editable?: boolean; onChange?: (content: string) => void }) {
  const [selection, setSelection] = useState<string[] | null>(null)
  const [downloadError, setDownloadError] = useState('')
  const [featureId, setFeatureId] = useState<string | null>(null)
  const [category, setCategory] = useState<string | null>(null)
  const evidenceRef = useRef<HTMLElement>(null)
  const parsed = useMemo(() => { try { return { value: parse(content) } } catch (error) { return { error: error instanceof Error ? error.message : '无法读取材料整理结果' } } }, [content])
  if (!parsed.value) return <Alert type="error" showIcon title={parsed.error} />
  const material = parsed.value
  const generalQuestions = material.questions.filter(q => q.functionIds.length === 0)
  const activeFeature = material.functions.find(f => f.id === featureId) ?? material.functions[0]
  const activeId = activeFeature?.id
  const featureQuestions = material.questions.filter(q => q.functionIds.includes(activeId ?? ''))
  const visibleCategories: string[] = categories.filter(name => name === '待确认问题' ? featureQuestions.length > 0 : activeFeature?.sections.some(section => section.title === name && section.items.length > 0))
  const general = (category === '整体待确认' || (!activeFeature && category !== '完整材料')) && generalQuestions.length > 0
  const allMaterials = category === '完整材料'
  const activeCategory = general ? '整体待确认' : allMaterials ? category : (category && visibleCategories.includes(category) ? category : visibleCategories[0])
  const sectionIndex = activeFeature?.sections.findIndex(section => section.title === activeCategory) ?? -1
  const section = sectionIndex >= 0 ? activeFeature.sections[sectionIndex] : undefined
  const fi = material.functions.findIndex(f => f.id === activeId)
  const currentQuestions = general ? generalQuestions : featureQuestions
  const update = (itemIndex: number, text: string) => {
    if (!onChange || fi < 0 || sectionIndex < 0) return
    const next = structuredClone(material)
    next.functions[fi].sections[sectionIndex].items[itemIndex].text = text
    onChange(JSON.stringify(next, null, 2))
  }
  const updateQuestion = (id: string, question: string) => {
    if (!onChange) return
    const next = structuredClone(material)
    const item = next.questions.find(q => q.id === id)
    if (item) item.question = question
    onChange(JSON.stringify(next, null, 2))
  }
  const selected = material.materialBlocks.filter(block => selection?.includes(block.id))
  const showEvidence = (ids: string[]) => {
    setSelection(ids)
    if (window.matchMedia?.('(max-width: 760px)').matches) setTimeout(() => evidenceRef.current?.scrollIntoView?.({ behavior: 'smooth' }), 0)
  }
  const downloadSource = async (fileId: string) => {
    try {
      setDownloadError('')
      const { blob, filename } = await downloadStoredFile(fileId)
      saveBlob(blob, filename || '需求原始材料')
    } catch { setDownloadError('原始材料下载失败，请重试。') }
  }
  const switchFeature = (id: string) => { setFeatureId(id); setCategory(null); setSelection(null) }
  const switchCategory = (name: string) => { setCategory(name); setSelection(null) }
  const categoryIndex = visibleCategories.indexOf(activeCategory ?? '')
  return <div className={`readable-material ${selection !== null ? 'has-evidence' : ''}`} role="region" aria-label="材料整理结果">
    <nav className="readable-material-nav" aria-label="功能和章节导航">
      <div className="readable-material-nav-label">功能</div>
      {material.functions.map(feature => <button type="button" key={feature.id} className={`readable-material-feature-button ${activeId === feature.id ? 'active' : ''}`} onClick={() => switchFeature(feature.id)}>{feature.name}</button>)}
      {activeFeature && <><div className="readable-material-nav-label readable-material-nav-heading">内容章节</div>{visibleCategories.map((name, index) => <button type="button" key={name} className={`readable-material-category-button ${!general && !allMaterials && activeCategory === name ? 'active' : ''}`} onClick={() => switchCategory(name)}><span>{String(index + 1).padStart(2, '0')}</span>{name}</button>)}</>}
      {generalQuestions.length > 0 && <button type="button" className={`readable-material-extra ${general ? 'active' : ''}`} onClick={() => switchCategory('整体待确认')}>整体待确认 <span>{generalQuestions.length}</span></button>}
      <button type="button" className={`readable-material-extra ${allMaterials ? 'active' : ''}`} onClick={() => switchCategory('完整材料')}>查看完整材料</button>
    </nav>
    <main className="readable-material-content">
      <header><div className="readable-material-eyebrow">材料整理 · 功能说明</div><h2>{material.title}</h2><span>{material.functions.length} 项功能 · {material.questions.length} 个待确认问题</span></header>
      <div className="readable-material-reading"><div className="readable-material-context">{general ? '所有功能' : allMaterials ? '原始材料' : activeFeature?.name}</div><h3>{activeCategory ?? '暂无可展示内容'}</h3>
        {section?.items.map((item, index) => <div className="readable-material-item" key={index}>{editable ? <Input.TextArea aria-label={`${activeFeature.name} ${section.title} 内容 ${index + 1}`} autoSize onClick={() => showEvidence(item.materialBlockIds)} value={item.text} onChange={event => update(index, event.target.value)} /> : <button type="button" className="readable-material-text" onClick={() => showEvidence(item.materialBlockIds)}>{item.text}</button>}<div className="readable-material-item-meta">{statusLabels[item.status] && <span>{statusLabels[item.status]}</span>}</div></div>)}
        {(general || activeCategory === '待确认问题') && currentQuestions.map((question, index) => <div className="readable-material-item readable-material-question" key={question.id}><span className="readable-material-number">{question.id}</span><div>{editable ? <Input.TextArea aria-label={`待确认问题 ${index + 1}`} autoSize onClick={() => showEvidence(question.materialBlockIds)} value={question.question} onChange={event => updateQuestion(question.id, event.target.value)} /> : <button type="button" className="readable-material-text" onClick={() => showEvidence(question.materialBlockIds)}>{question.question}</button>}</div></div>)}
        {allMaterials && material.materialBlocks.map(block => <article className="readable-material-source-block" key={block.id}><small>{material.sources.find(source => source.id === block.sourceId)?.name} · {block.locator}</small><MaterialBlockContent block={block} /></article>)}
        {categoryIndex >= 0 && visibleCategories.length > 1 && <div className="readable-material-pagination">{categoryIndex > 0 ? <button type="button" onClick={() => switchCategory(visibleCategories[categoryIndex - 1])}>← {visibleCategories[categoryIndex - 1]}</button> : <span />}{categoryIndex < visibleCategories.length - 1 && <button type="button" onClick={() => switchCategory(visibleCategories[categoryIndex + 1])}>{visibleCategories[categoryIndex + 1]} →</button>}</div>}
      </div>
    </main>
    {selection !== null && <aside ref={evidenceRef} className="readable-material-evidence" aria-label="材料依据"><div className="readable-material-evidence-head"><h3>材料依据</h3><button type="button" aria-label="关闭材料依据" onClick={() => setSelection(null)}>×</button></div>{downloadError && <Alert type="error" title={downloadError} />}{selected.length ? selected.map(block => {
      const source = material.sources.find(item => item.id === block.sourceId)
      const match = source?.location?.match(/^\/v1\/files\/([^/]+)\/download$/)
      return <article key={block.id}><strong>{source?.name ?? '来源未找到'}</strong><small>{block.locator}</small><MaterialBlockContent block={block} />{match && <button type="button" onClick={() => void downloadSource(match[1])}>下载原始材料</button>}</article>
    }) : <p>未找到对应材料。</p>}</aside>}
  </div>
}
