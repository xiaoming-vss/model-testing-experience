import { BugDetailPanel } from './BugDetailPanel'
import { recognizeJsonDescription } from '../utils/jsonDescription'
import { useMemo, useState } from 'react'
import { Segmented } from 'antd'
import { RichTextViewer } from '@/shared/components/RichTextEditor'
import { useViewMotion } from '@/shared/ui/useViewMotion'

export function BugDescriptionView({ html }: { html: string }) {
  const displayHtml = useMemo(() => recognizeJsonDescription(html), [html])
  const [mode, setMode] = useState('render')
  const viewRef = useViewMotion(mode === 'render' ? 0 : 1)
  return <BugDetailPanel>
    <div className="bug-detail-section-heading mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-[var(--srf-divider)] pb-3">
      <h2 className="bug-panel-title m-0 flex items-center gap-2 border-0 p-0 text-[14px] font-semibold text-[var(--srf-text)]">问题描述与复现依据</h2>
      <Segmented className="tab-view-switch" size="small" aria-label="描述显示方式" value={mode} onChange={setMode}
        options={[{ label: '渲染视图', value: 'render' }, { label: 'RAW 代码', value: 'raw' }]} />
    </div>
    <div ref={viewRef}>{mode === 'raw' ? <pre className="bug-description-raw max-h-[480px] overflow-auto whitespace-pre-wrap break-words bg-[var(--srf-hover)] p-4 text-[var(--srf-text-secondary)]">{html}</pre> : <RichTextViewer html={displayHtml} ariaLabel="问题描述" />}</div>
  </BugDetailPanel>
}
