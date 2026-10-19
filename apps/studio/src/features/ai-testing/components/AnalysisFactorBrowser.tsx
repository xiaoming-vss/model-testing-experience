import { AnalysisContentBrowser } from './AnalysisContentBrowser'
import { formatTextList, toDisplayText } from '@/features/ai-testing/utils/functionalOutput'
import '@/features/ai-testing/styles/analysis-rule-details.css'
import '@/features/ai-testing/styles/analysis-factor-details.css'

const display = (value: unknown) => formatTextList(value) || (Array.isArray(value) ? '无' : '未明确')

function FactorDetails({ item }: { item: Record<string, unknown> }) {
  const values = (Array.isArray(item.confirmedValues) ? item.confirmedValues : [item.confirmedValues])
    .map(formatTextList).filter((value) => value.trim())
  return <div className="ai-analysis-rule-layout ai-analysis-factor-layout">
    <section className="ai-analysis-rule-panel" aria-label="已确认取值">
      <h4>已确认取值{values.length > 0 && <span className="ai-analysis-factor-count">{values.length} 项</span>}</h4>
      {values.length ? <ul className={values.length > 6 ? 'ai-analysis-factor-values is-multicolumn' : 'ai-analysis-factor-values'}>
        {values.map((value, index) => <li key={index}>{value}</li>)}
      </ul> : <p>{display(item.confirmedValues)}</p>}
    </section>
    <div className="ai-analysis-rule-pair">
      <section className="ai-analysis-rule-panel" aria-label="默认值"><h4>默认值</h4><p>{display(item.defaultValue)}</p></section>
      <section className="ai-analysis-rule-panel" aria-label="待澄清内容"><h4>待澄清内容</h4><p>{display(item.clarificationNeeded)}</p></section>
    </div>
    {values.length > 6 && <p className="ai-analysis-factor-reading">取值按原文顺序纵向阅读，各列依次衔接。</p>}
  </div>
}

export function AnalysisFactorBrowser({ entries }: { entries: Record<string, unknown>[] }) {
  return <AnalysisContentBrowser title="场景因素" compact entries={entries.map((item, index) => ({
    key: `${toDisplayText(item.factorId)}-${index}`,
    code: toDisplayText(item.factorId) || `${index + 1}`,
    title: toDisplayText(item.name) || `因素 ${index + 1}`,
    searchText: Object.values(item).map(formatTextList).join(' '),
    content: <FactorDetails item={item} />,
  }))} />
}
