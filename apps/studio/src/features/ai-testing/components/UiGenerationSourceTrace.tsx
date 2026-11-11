import { Button, Popover } from 'antd'
import type { UiGenerationSourceInputs } from '../api/generationChain.api'
import '../styles/ui-generation-inputs.css'

export function UiGenerationSourceTrace({ source, loading = false }: {
  source?: UiGenerationSourceInputs | null
  loading?: boolean
}) {
  if (loading) return <span className="gc-trace-chip">正在读取生成来源</span>
  if (!source) return <span className="gc-trace-chip">仓库与功能用例 <b>历史来源未记录</b></span>
  const repository = source.repository
  const cases = source.cases ?? []
  const caseCount = cases.length
  return <Popover trigger="click" placement="topLeft" destroyOnHidden content={
    <section className="gc-ui-source-details" aria-label="生成输入快照">
      <h3>生成时的输入快照</h3>
      <h4>源码仓库</h4>
      {repository ? <dl className="gc-ui-source-repository">
        <div><dt>仓库</dt><dd>{repository.pathWithNamespace}</dd></div>
        <div><dt>分支</dt><dd>{repository.branch || '未记录'}</dd></div>
        <div><dt>Commit</dt><dd><code>{repository.commit || '未记录'}</code>（{repository.commitMode === 'latest' ? '分支最新 HEAD' : '画像 commit'}）</dd></div>
        <div><dt>画像版本</dt><dd>{repository.profileVersionNo ? `v${repository.profileVersionNo}` : repository.profileVersionId || '未记录'}</dd></div>
        <div><dt>源码根</dt><dd>整个仓库</dd></div>
      </dl> : <p>历史来源未记录仓库信息。</p>}
      <h4>功能用例 · {caseCount} 条</h4>
      {cases.map(item => <details key={item.caseId}>
        <summary>{item.title} · {item.caseId}</summary>
        <p>{item.suiteName}{item.module ? ` / ${item.module}` : ''}</p>
        <pre>{JSON.stringify(item.content ?? {}, null, 2)}</pre>
      </details>)}
    </section>
  }>
    <Button type="link" size="small" className="gc-ui-source-trigger" aria-label="查看仓库和功能用例快照">
      仓库：{repository?.pathWithNamespace || '历史来源未记录'} · 功能用例：{caseCount} 条
    </Button>
  </Popover>
}
