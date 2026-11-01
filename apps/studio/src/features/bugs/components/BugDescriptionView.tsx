import { recognizeJsonDescription } from '../utils/jsonDescription'
import { useMemo, useState } from 'react'
import { Segmented } from 'antd'
import { RichTextViewer } from '@/shared/components/RichTextEditor'
import { useViewMotion } from '@/shared/ui/useViewMotion'

export function BugDescriptionView({ html }: { html: string }) {
  const displayHtml = useMemo(() => recognizeJsonDescription(html), [html])
  const [mode, setMode] = useState('render')
  const viewRef = useViewMotion(mode === 'render' ? 0 : 1)
  return <section className="bug-detail-panel">
    <div className="bug-detail-section-heading">
      <h2 className="bug-panel-title">问题描述与复现依据</h2>
      <Segmented className="tab-view-switch" size="small" aria-label="描述显示方式" value={mode} onChange={setMode}
        options={[{ label: '渲染视图', value: 'render' }, { label: 'RAW 代码', value: 'raw' }]} />
    </div>
    <div ref={viewRef}>{mode === 'raw' ? <pre className="bug-description-raw">{html}</pre> : <RichTextViewer html={displayHtml} ariaLabel="问题描述" />}</div>
  </section>
}
