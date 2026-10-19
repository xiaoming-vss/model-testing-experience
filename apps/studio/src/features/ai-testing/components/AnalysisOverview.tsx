import { useId, useState } from 'react'
import { ArrowRightOutlined } from '@ant-design/icons'
import { Empty } from 'antd'
import { toRecordArray } from '@/shared/utils/value'
import { formatTextList, toDisplayText } from '@/features/ai-testing/utils/functionalOutput'
import '@/features/ai-testing/styles/analysis-overview.css'

const boundaries = [
  { key: 'actors', title: '参与角色' },
  { key: 'applicableObjects', title: '适用对象' },
  { key: 'explicitExclusions', title: '明确排除范围' },
]
const display = (value: unknown) => formatTextList(value) || (Array.isArray(value) ? '无' : '未明确')

export function AnalysisOverview({ overview }: {
  overview: Record<string, unknown>
}) {
  const [selectedIndex, setSelectedIndex] = useState<number>()
  const detailId = useId()
  const entries = toRecordArray(overview.entryPoints)
  const selected = selectedIndex === undefined ? undefined : entries[selectedIndex]

  return <section className="ai-analysis-overview" aria-label="功能概览">
    <section className="ai-analysis-module-map" aria-label="业务模块导航">
      <header className="ai-analysis-overview-heading">
        <div><h2>沿着业务模块理解需求</h2><p>功能概览 · {entries.length} 个业务模块 · 按原文顺序展示</p></div>
      </header>
      {entries.length ? <div className="ai-analysis-module-track">
        {entries.map((entry, index) => <button
          type="button" key={index} className="ai-analysis-module"
          aria-expanded={selectedIndex === index} aria-controls={detailId}
          onClick={() => setSelectedIndex(selectedIndex === index ? undefined : index)}
        >
          <strong>{toDisplayText(entry.function) || `入口 ${index + 1}`}</strong>
          <span>{selectedIndex === index ? '收起模块详情' : '查看模块详情'} <ArrowRightOutlined aria-hidden /></span>
        </button>)}
      </div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无业务模块" />}
      <div id={detailId}>
        {selected && <article className="ai-analysis-module-detail" aria-label="业务模块详情">
          <h3>{toDisplayText(selected.function) || `入口 ${(selectedIndex ?? 0) + 1}`}</h3>
          <dl><dt>入口路径</dt><dd>{display(selected.path)}</dd><dt>操作</dt><dd>{display(selected.action)}</dd></dl>
        </article>}
      </div>
    </section>
    <div className="ai-analysis-overview-main">
        <section className="ai-analysis-purpose-panel"><h3>功能目的</h3><p className="ai-analysis-overview-purpose">{display(overview.purpose)}</p></section>
        <section className="ai-analysis-boundaries"><h3>需求边界</h3>
          <div className="ai-analysis-boundary-grid">{boundaries.map(({ key, title }) => {
            const items = formatTextList(overview[key]).split('\n').filter((item) => item.trim())
            return <section className="ai-analysis-boundary" key={key} aria-label={title}>
              <h4>{title}</h4>
              {items.length ? <ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p>{display(overview[key])}</p>}
            </section>
          })}</div>
        </section>
    </div>
  </section>
}
