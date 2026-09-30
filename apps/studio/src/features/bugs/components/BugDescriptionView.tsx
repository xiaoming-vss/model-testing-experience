import { useMemo, useState } from 'react'
import { Segmented } from 'antd'
import { RichTextViewer } from '@/shared/components/RichTextEditor'

import { splitBugDescription } from '../utils/splitBugDescription'

export function BugDescriptionView({ html }: { html: string }) {
  const [mode, setMode] = useState('render')
  const sections = useMemo(() => splitBugDescription(html), [html])
  return <section className="bug-detail-panel">
    <div className="bug-detail-section-heading">
      <h2 className="bug-panel-title">问题描述与复现依据</h2>
      <Segmented size="small" aria-label="描述显示方式" value={mode} onChange={setMode}
        options={[{ label: '渲染视图', value: 'render' }, { label: 'RAW 代码', value: 'raw' }]} />
    </div>
    {mode === 'raw' ? <pre className="bug-description-raw">{html}</pre> : <div className="bug-description-sections">
      {sections.length ? sections.map((section, index) => <section key={index} className={`bug-description-section is-${section.kind}`}>
        {section.title && <h3>{section.title}</h3>}
        <RichTextViewer html={section.html} ariaLabel={section.title || '问题描述'} />
      </section>) : <RichTextViewer html={html} ariaLabel="问题描述" />}
    </div>}
  </section>
}
