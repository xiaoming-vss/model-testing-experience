import { useMemo, useRef, useState } from 'react'
import { Empty, Tag } from 'antd'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from '../utils/functionalOutput'
import { MaterialBlockContent, type MaterialBlock } from './ReadableRequirementMaterial'
import '@/features/ai-testing/styles/test-scope-analysis.css'

const categories = [
  { key: 'testObjects', label: '测试对象', hint: '识别需要关注的业务对象与操作' },
  { key: 'impactAreas', label: '业务影响范围', hint: '从变更出发，梳理已知业务关联和影响' },
  { key: 'risks', label: '风险', hint: '关注可能影响业务判断或测试覆盖的因素' },
  { key: 'openQuestions', label: '待确认问题', hint: '材料未明确、需要进一步确认的事项' },
] as const

type Category = typeof categories[number]['key']
const status: Record<string, { label: string; color: string }> = {
  confirmed: { label: '明确', color: 'green' },
  inferred: { label: '推测', color: 'blue' },
  unconfirmed: { label: '待确认', color: 'orange' },
}

export function TestScopeAnalysisView({ analysis, materialContent }: {
  analysis: Record<string, unknown>
  materialContent?: string
}) {
  const [active, setActive] = useState<Category>('testObjects')
  const [selection, setSelection] = useState<{ key: string; sourceIds: string[] } | null>(null)
  const evidenceRef = useRef<HTMLElement>(null)
  const material = useMemo(() => {
    try { return toRecord(JSON.parse(materialContent || '')) } catch { return undefined }
  }, [materialContent])
  const blocks = toRecordArray(material?.materialBlocks)
  const sources = toRecordArray(material?.sources)
  const selectedBlocks = selection?.sourceIds.map((id) => blocks.find((block) => block.id === id)) ?? []
  const current = categories.find((category) => category.key === active)!
  const entries = toRecordArray(analysis[active])
  return <div className={`ai-test-scope${selection ? ' has-evidence' : ''}`}>
    <nav className="ai-test-scope-nav" aria-label="测试范围风险分析分类">
      <div className="ai-test-scope-nav-title">分析目录</div>
      {categories.map((category) => <button type="button" key={category.key}
        className={active === category.key ? 'is-active' : ''}
        aria-current={active === category.key ? 'page' : undefined}
        onClick={() => { setActive(category.key); setSelection(null) }}>
        <span>{category.label}</span><span>{toRecordArray(analysis[category.key]).length}</span>
      </button>)}
    </nav>
    <div className="ai-test-scope-content">
      <header className="ai-test-scope-header"><div><strong>{current.label}</strong><p>{current.hint}</p></div><span>共 {entries.length} 项</span></header>
      {entries.length ? entries.map((entry, index) => {
        const id = toDisplayText(entry.id) || String(index + 1)
        const title = toDisplayText(entry.name ?? entry.area ?? entry.question) || (active === 'risks' ? '风险关注' : '未命名')
        const description = toDisplayText(active === 'impactAreas' ? entry.impact : entry.description)
        const sourceIds = Array.isArray(entry.sourceBlockIds) ? entry.sourceBlockIds.filter((value): value is string => typeof value === 'string') : []
        const state = status[toDisplayText(entry.basisStatus)]
        const entryKey = `${active}-${id}-${index}`
        const isOpen = selection?.key === entryKey
        const content = <><div className="ai-test-scope-item-title"><span>{id}</span><strong>{title}</strong>{state ? <Tag color={state.color}>{state.label}</Tag> : null}</div>
          {description ? <p>{description}</p> : null}</>
        return <article className="ai-test-scope-item" key={`${id}-${index}`}>
          {sourceIds.length && blocks.length ? <button type="button" className="ai-test-scope-item-action" aria-expanded={isOpen}
            onClick={() => {
              setSelection({ key: entryKey, sourceIds })
              if (window.matchMedia?.('(max-width: 760px)').matches) {
                setTimeout(() => evidenceRef.current?.scrollIntoView?.({ behavior: 'smooth' }), 0)
              }
            }}>{content}</button> : content}
        </article>
      }) : <Empty description={`暂无${current.label}`} />}
    </div>
    {selection ? <aside ref={evidenceRef} className="ai-test-scope-evidence" aria-label="材料依据">
      <div className="ai-test-scope-evidence-head"><h3>材料依据</h3><button type="button" aria-label="关闭材料依据" onClick={() => setSelection(null)}>×</button></div>
      {selectedBlocks.map((block, index) => {
        if (!block) return <article key={selection.sourceIds[index]}><p>未找到对应材料。</p></article>
        const source = sources.find((item) => item.id === block.sourceId)
        return <article key={selection.sourceIds[index]}>
          <strong>{toDisplayText(source?.name) || '来源未找到'}</strong>
          <small>{toDisplayText(block.locator) || '未找到材料位置'}</small>
          <MaterialBlockContent block={block as MaterialBlock} />
        </article>
      })}
    </aside> : null}
  </div>
}
