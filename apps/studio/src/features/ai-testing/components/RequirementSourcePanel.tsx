import { RequirementArtifactValue } from '@/domain/requirements/RequirementArtifactView'
import type { RequirementSourceReference } from '@/domain/requirements/requirementArtifact'
import { FileTextOutlined, InfoCircleOutlined, ReadOutlined } from '@ant-design/icons'
import { Button, Empty, Popover, Segmented, Select, Tag, Tabs } from 'antd'
import { useLayoutEffect, useMemo, useRef } from 'react'
import type { ExtractedFact, MaterialBlock, MaterialSource } from '../utils/materialComparison'
import '../styles/material-comparison.css'

const noFacts: ExtractedFact[] = []
const sourceTypes: Record<string, string> = { document: '需求文档', text: '文本材料', prototype: '原型', screenshot: '截图', design: '设计稿', user_confirmation: '用户明确答复', example: '示例材料' }

type Props = {
  artifact: unknown
  sources: MaterialSource[]
  blocks: MaterialBlock[]
  facts?: ExtractedFact[]
  sourceId?: string
  onSourceChange: (id: string) => void
  linkedBlockIds: Set<string>
  linkedFactIds?: Set<string>
  locateVersion: number
  mode?: 'materials' | 'facts'
  onModeChange?: (mode: 'materials' | 'facts') => void
  evidence?: RequirementSourceReference
  onSourceReference?: (ref: RequirementSourceReference) => void
  comparisonLayout?: boolean
  emptyMessage?: string
}

function BlockBody({ artifact, block }: { artifact: unknown; block: MaterialBlock }) {
  return <>
    {block.kind === 'paragraph' && <p>{block.text ?? '正文无法识别'}</p>}
    {block.kind === 'list' && <ul>{(block.items ?? []).map((item, index) => <li key={index}>{item}</li>)}</ul>}
    {block.kind === 'table' && <RequirementArtifactValue artifact={artifact} value={block.table} field="table" />}
    {block.kind === 'image' && <RequirementArtifactValue artifact={artifact} value={block.image} field="image" />}
    {block.parseStatus !== 'complete' && <Tag color="warning">{block.parseStatus === 'unreadable' ? '无法识别' : '部分已识别'}</Tag>}
  </>
}

export function RequirementSourcePanel({ artifact, sources, blocks: allBlocks, facts: allFacts = noFacts, sourceId, onSourceChange, linkedBlockIds, linkedFactIds, locateVersion, mode = 'materials', onModeChange, evidence, onSourceReference, emptyMessage, comparisonLayout = false }: Props) {
  const pane = useRef<HTMLDivElement>(null)
  const elements = useRef(new Map<string, HTMLElement>())
  const source = sourceId === 'all' ? undefined : sources.find(s => s.id === sourceId) ?? (sourceId ? undefined : sources[0])
  const blocks = useMemo(() => allBlocks.filter(b => b.sourceReferences.some(ref => ref.sourceId === source?.id)), [allBlocks, source?.id])
  const facts = useMemo(() => allFacts.filter(f => sourceId === 'all' || f.fact.sourceReferences.some(r => r.sourceId === source?.id) || blocks.some(b => f.relatedBlockIds.includes(b.id))), [allFacts, sourceId, source?.id, blocks])
  const visibleEvidence = evidence && (sourceId === 'all' || sourceId === evidence.sourceId || source?.id === evidence.sourceId) ? evidence : undefined
  useLayoutEffect(() => {
    const linked = mode === 'facts' ? facts.find(f => linkedFactIds?.has(f.id))?.id : blocks.find(b => linkedBlockIds.has(b.id))?.id
    const element = linked && elements.current.get(linked)
    if (pane.current) pane.current.scrollTop = element ? Math.max(0, pane.current.scrollTop + element.getBoundingClientRect().top - pane.current.getBoundingClientRect().top - 20) : 0
  }, [blocks, facts, linkedBlockIds, linkedFactIds, mode, locateVersion])
  function register(id: string, element: HTMLElement | null) { if (element) elements.current.set(id, element); else elements.current.delete(id) }
  return <section className={`requirement-material-panel${comparisonLayout ? ' requirement-source-comparison' : ''}`}>
    {comparisonLayout && onModeChange && <header className="requirement-material-panel-head"><Tabs className="requirement-understanding-nav" activeKey={mode} onChange={value => onModeChange(value as 'materials' | 'facts')} items={[{ key: 'materials', label: '原始材料' }, { key: 'facts', label: '提取事实' }]} /></header>}
    <header className="requirement-material-panel-head">
      {!comparisonLayout && (onModeChange ? <Segmented aria-label="核对依据分类" value={mode} onChange={value => onModeChange(value as 'materials' | 'facts')} options={[{ value: 'materials', label: '材料内容' }, { value: 'facts', label: '提取事实' }]} /> : <strong><ReadOutlined /> 材料内容</strong>)}
      <Select prefix={comparisonLayout ? <FileTextOutlined /> : undefined} aria-label="材料来源" value={sourceId === 'all' ? 'all' : source?.id} disabled={!sources.length} onChange={onSourceChange} options={[...(mode === 'facts' ? [{ value: 'all', label: '全部来源' }] : []), ...sources.map(s => ({ value: s.id, label: s.name, title: s.name }))]} />
      <Popover trigger="click" title="材料来源" content={source ? <div className="requirement-material-source-info"><strong>{source.name}</strong><span>{sourceTypes[source.type] ?? source.type}</span><span>版本：{source.version ?? '未提供'}</span><span>位置：{source.location ?? '未提供'}</span></div> : '请先选择一个材料来源'}>
        <Button type="text" size="small" aria-label="查看材料来源信息" icon={<InfoCircleOutlined />} />
      </Popover>
    </header>
    <div className="requirement-material-document" ref={pane} role="region" aria-label={mode === 'facts' ? '已审核提取事实' : '材料内容'} tabIndex={0}>
      {source && (!comparisonLayout || mode === 'facts') && <div className="requirement-material-document-title"><Tag>{sourceTypes[source.type] ?? source.type}</Tag><h3>{source.name}</h3></div>}
      {visibleEvidence && (!comparisonLayout || !linkedBlockIds.size || mode === 'facts') && <div className="requirement-understanding-evidence"><strong>依据定位</strong><p>{visibleEvidence.locator}</p>{visibleEvidence.excerpt && <blockquote>{visibleEvidence.excerpt}</blockquote>}</div>}
      {mode === 'facts' ? facts.length ? facts.map(f => <article key={f.id} ref={element => register(f.id, element)} data-extracted-fact={f.id} className={`requirement-material-block${linkedFactIds?.has(f.id) ? ' is-linked' : ''}`}><RequirementArtifactValue artifact={artifact} value={f.fact} onSourceReference={onSourceReference} /></article>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyMessage ?? '此来源暂无已记录的提取事实'} />
        : blocks.length ? blocks.map(block => <article key={block.id} ref={element => register(block.id, element)} data-material-block={block.id} aria-label={block.title ?? block.sourceReferences[0]?.locator} className={`requirement-material-block${block.kind === 'section' ? ' is-section' : ''}${linkedBlockIds.has(block.id) ? ' is-linked' : ''}`}>
          <div className="requirement-material-block-location"><span>{block.sourceReferences.filter(r => r.sourceId === source?.id).map(r => r.locator).join('；')}</span>{linkedBlockIds.has(block.id) && <Tag color="blue">关联依据</Tag>}</div>
          {block.title && <h4>{block.title}</h4>}<BlockBody artifact={artifact} block={block} />
        </article>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyMessage ?? (source ? '此来源暂无材料内容块，可查看已记录的来源摘录' : '暂无已记录材料')} />}
    </div>
    <footer className="requirement-material-panel-foot"><span><FileTextOutlined /> {sources.length} 个材料来源</span><span>{mode === 'facts' ? `当前 ${facts.length} / 全部 ${allFacts.length} 条提取事实` : `当前 ${blocks.length} / 全部 ${allBlocks.length} 个内容块`}</span></footer>
  </section>
}
