import { useMemo, useState } from 'react'
import { Empty, Tag } from 'antd'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from '../utils/functionalOutput'
import { MaterialBlockContent, type MaterialBlock } from './ReadableRequirementMaterial'
import '@/features/ai-testing/styles/test-scope-analysis.css'

const categories = [
  { key: 'testObjects', label: '测试对象', hint: '识别需要关注的业务对象与操作' },
  { key: 'impactAreas', label: '影响范围', hint: '从变更出发，梳理已知业务关联和影响' },
  { key: 'risks', label: '风险', hint: '可能影响业务判断或测试覆盖的因素' },
  { key: 'openQuestions', label: '待确认', hint: '材料未明确、需要进一步确认的事项' },
] as const

type Category = (typeof categories)[number]['key']

const status: Record<string, { label: string; color: string }> = {
  confirmed: { label: '明确', color: 'green' },
  inferred: { label: '推测', color: 'blue' },
  unconfirmed: { label: '待确认', color: 'orange' },
}

function refIds(record: Record<string, unknown>, field: string) {
  return Array.isArray(record[field]) ? record[field].map(toDisplayText).filter(Boolean) : []
}

function entryId(entry: Record<string, unknown>, index: number) {
  return toDisplayText(entry.id) || String(index + 1)
}

function entryTitle(category: Category, entry: Record<string, unknown>) {
  const value = category === 'testObjects'
    ? entry.name
    : category === 'impactAreas'
      ? entry.area
      : category === 'risks'
        ? entry.description
        : entry.question
  return toDisplayText(value) || '未命名'
}

function Field({ label, value }: { label: string; value: string }) {
  return <div className="ai-test-scope-field">
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
  return <section className="ai-test-scope-refs">
    <h4>{title}<span>{values.length}</span></h4>
    <div className="ai-test-scope-chips">
      {values.map((id) => {
        const label = resolve(id)
        return <span key={id}>{label ? `${id} ${label}` : id}</span>
      })}
    </div>
  </section>
}

function Evidence({ blockIds, blockById, sourceById }: {
  blockIds: string[]
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
}) {
  return <section className="ai-test-scope-evidence" aria-label="材料依据">
    <h4>材料依据<span>{blockIds.length}</span></h4>
    {blockIds.length ? <div className="ai-test-scope-evidence-list">
      {blockIds.map((id) => {
        const block = blockById.get(id)
        if (!block) return <div key={id} className="ai-test-scope-evidence-missing">{id}：未找到对应材料</div>
        const source = sourceById.get(toDisplayText(block.sourceId))
        return <article key={id} className="ai-test-scope-evidence-item">
          <div className="ai-test-scope-evidence-head">
            <strong>{toDisplayText(source?.name) || '来源未找到'}</strong>
            <span>{toDisplayText(block.locator)}</span>
          </div>
          <MaterialBlockContent block={block as MaterialBlock} />
        </article>
      })}
    </div> : <p className="ai-test-scope-empty-ref">暂无材料依据</p>}
  </section>
}

export function TestScopeAnalysisView({ analysis, materialContent }: {
  analysis: Record<string, unknown>
  materialContent?: string
}) {
  const [active, setActive] = useState<Category>('testObjects')
  const [selected, setSelected] = useState<Partial<Record<Category, number>>>({})

  const material = useMemo(() => {
    try { return toRecord(JSON.parse(materialContent || '')) } catch { return undefined }
  }, [materialContent])

  const blocks = toRecordArray(material?.materialBlocks)
  const sources = toRecordArray(material?.sources)
  const materialQuestions = toRecordArray(material?.questions)
  const blockById = useMemo(() => new Map(blocks.map(block => [toDisplayText(block.id), block])), [blocks])
  const sourceById = useMemo(() => new Map(sources.map(source => [toDisplayText(source.id), source])), [sources])
  const questionById = useMemo(() => new Map(materialQuestions.map(question => [toDisplayText(question.id), toDisplayText(question.question)])), [materialQuestions])

  const objects = toRecordArray(analysis.testObjects)
  const areas = toRecordArray(analysis.impactAreas)
  const risks = toRecordArray(analysis.risks)
  const objectNameById = useMemo(() => new Map(objects.map((entry, index) => [entryId(entry, index), entryTitle('testObjects', entry)])), [objects])
  const areaNameById = useMemo(() => new Map(areas.map((entry, index) => [entryId(entry, index), entryTitle('impactAreas', entry)])), [areas])
  const riskNameById = useMemo(() => new Map(risks.map((entry, index) => [entryId(entry, index), entryTitle('risks', entry)])), [risks])

  const entries = toRecordArray(analysis[active])
  const activeIndex = Math.min(selected[active] ?? 0, Math.max(entries.length - 1, 0))
  const activeEntry = entries[activeIndex]
  const current = categories.find(category => category.key === active)!
  const activeStatus = activeEntry ? status[toDisplayText(activeEntry.basisStatus)] : undefined

  const breakdown = { confirmed: 0, inferred: 0, unconfirmed: 0 }
  entries.forEach((entry) => {
    const key = toDisplayText(entry.basisStatus)
    if (key in breakdown) breakdown[key as keyof typeof breakdown] += 1
  })

  const questionRelated = {
    objects: new Set(entries.flatMap(entry => refIds(entry, 'testObjectIds'))).size,
    areas: new Set(entries.flatMap(entry => refIds(entry, 'impactAreaIds'))).size,
    risks: new Set(entries.flatMap(entry => refIds(entry, 'riskIds'))).size,
  }

  const select = (index: number) => setSelected(currentValue => ({ ...currentValue, [active]: index }))

  return <div className="ai-test-scope">
    <div className="ai-test-scope-tabs" role="tablist" aria-label="测试范围风险分析">
      {categories.map((category) => {
        const count = toRecordArray(analysis[category.key]).length
        return <button
          key={category.key}
          type="button"
          role="tab"
          aria-selected={active === category.key}
          className={`ai-test-scope-tab${active === category.key ? ' is-active' : ''}`}
          onClick={() => setActive(category.key)}
        >
          {category.label}
          <span className={`ai-test-scope-count${category.key === 'openQuestions' && count ? ' is-warn' : ''}`}>{count}</span>
        </button>
      })}
    </div>
    <div className="ai-test-scope-page" role="tabpanel" aria-label={current.label}>
      <header className="ai-test-scope-head">
        <div className="ai-test-scope-stat">
          <span>{current.label}</span>
          <strong>{entries.length}</strong>
        </div>
        <span className="ai-test-scope-divider" aria-hidden="true" />
        {active === 'openQuestions'
          ? <div className="ai-test-scope-related">
            <span>涉及测试对象 {questionRelated.objects}</span>
            <span>影响范围 {questionRelated.areas}</span>
            <span>风险 {questionRelated.risks}</span>
          </div>
          : <div className="ai-test-scope-breakdown">
            <span><i className="ai-test-scope-dot is-confirmed" aria-hidden="true" />明确 {breakdown.confirmed}</span>
            <span><i className="ai-test-scope-dot is-inferred" aria-hidden="true" />推测 {breakdown.inferred}</span>
            <span><i className="ai-test-scope-dot is-unconfirmed" aria-hidden="true" />待确认 {breakdown.unconfirmed}</span>
          </div>}
        <span className="ai-test-scope-hint">{current.hint}</span>
      </header>
      {entries.length ? <div className="ai-test-scope-split">
        <aside className="ai-test-scope-list" aria-label={`${current.label}列表`}>
          {entries.map((entry, index) => {
            const entryStatus = status[toDisplayText(entry.basisStatus)]
            return <button
              key={`${entryId(entry, index)}-${index}`}
              type="button"
              className={`ai-test-scope-row${index === activeIndex ? ' is-active' : ''}`}
              onClick={() => select(index)}
            >
              <span className="ai-test-scope-row-id">{entryId(entry, index)}</span>
              <span className="ai-test-scope-row-main">
                <span className="ai-test-scope-row-title">{entryTitle(active, entry)}</span>
                {entryStatus ? <Tag color={entryStatus.color}>{entryStatus.label}</Tag> : null}
              </span>
            </button>
          })}
        </aside>
        <section className="ai-test-scope-detail" aria-label={`${current.label}详情`}>
          {activeEntry ? <>
            <div className="ai-test-scope-kicker">
              <span className="ai-test-scope-badge">{current.label}</span>
              <span>{entryId(activeEntry, activeIndex)}</span>
              {activeStatus ? <Tag color={activeStatus.color}>{activeStatus.label}</Tag> : null}
            </div>
            <h2>{entryTitle(active, activeEntry)}</h2>
            {active === 'testObjects' ? <>
              <Field label="类型" value={toDisplayText(activeEntry.type)} />
              <Field label="描述" value={toDisplayText(activeEntry.description)} />
            </> : null}
            {active === 'impactAreas' ? <>
              <Field label="影响" value={toDisplayText(activeEntry.impact)} />
              <RefChips title="关联测试对象" values={refIds(activeEntry, 'testObjectIds')} resolve={id => objectNameById.get(id)} />
            </> : null}
            {active === 'risks' ? <>
              <RefChips title="关联测试对象" values={refIds(activeEntry, 'testObjectIds')} resolve={id => objectNameById.get(id)} />
              <RefChips title="关联影响范围" values={refIds(activeEntry, 'impactAreaIds')} resolve={id => areaNameById.get(id)} />
            </> : null}
            {active === 'openQuestions' ? <>
              <RefChips title="关联测试对象" values={refIds(activeEntry, 'testObjectIds')} resolve={id => objectNameById.get(id)} />
              <RefChips title="关联影响范围" values={refIds(activeEntry, 'impactAreaIds')} resolve={id => areaNameById.get(id)} />
              <RefChips title="关联风险" values={refIds(activeEntry, 'riskIds')} resolve={id => riskNameById.get(id)} />
              <RefChips title="来源问题" values={refIds(activeEntry, 'sourceQuestionIds')} resolve={id => questionById.get(id)} />
            </> : null}
            <Evidence blockIds={refIds(activeEntry, 'sourceBlockIds')} blockById={blockById} sourceById={sourceById} />
          </> : null}
        </section>
      </div> : <div className="ai-test-scope-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`暂无${current.label}`} /></div>}
    </div>
  </div>
}
