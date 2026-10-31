import { Button, Popover } from 'antd'
import type { UiGenerationSourceInputs } from '../api/generationChain.api'
import '../styles/ui-generation-inputs.css'

export function UiGenerationSourceTrace({ source, loading = false }: {
  source?: UiGenerationSourceInputs | null
  loading?: boolean
}) {
  if (loading) return <span className="gc-trace-chip">正在读取生成来源</span>
  if (!source) return <span className="gc-trace-chip">源码与功能用例 <b>历史来源未记录</b></span>
  return <Popover trigger="click" placement="topLeft" destroyOnHidden content={
    <section className="gc-ui-source-details" aria-label="生成输入快照">
      <h3>生成时的输入快照</h3>
      <p>源码：{source.archive.filename || '历史源码（文件名未记录）'}</p>
      {source.archive.fileId ? <p>文件编号：{source.archive.fileId}</p> : null}
      {source.archive.sha256 ? <p>SHA256：{source.archive.sha256}</p> : null}
      <h4>功能用例 · {source.cases.length} 条</h4>
      {source.cases.map(item => <details key={item.caseId}>
        <summary>{item.title} · {item.caseId}</summary>
        <p>{item.suiteName}{item.module ? ` / ${item.module}` : ''}</p>
        <pre>{JSON.stringify(item.content ?? {}, null, 2)}</pre>
      </details>)}
    </section>
  }>
    <Button type="link" size="small" className="gc-ui-source-trigger" aria-label="查看源码和功能用例快照">
      源码：{source.archive.filename || '历史源码'} · 功能用例：{source.cases.length} 条
    </Button>
  </Popover>
}
