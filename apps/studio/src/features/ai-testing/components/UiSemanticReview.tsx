import { Alert, Button } from 'antd'
import { parseMaybeJsonValue, toRecord, toRecordArray } from '@/shared/utils/value'

const errorLabels: Record<string, string> = {
  timeout: '复核超时',
  model_error: '复核服务调用失败',
  invalid_report: '复核报告格式不合法',
  truncated: '复核报告被截断',
}

/** Model advice belongs to its original draft, never to the executable YAML. */
export function UiSemanticReview({ summary, dirty, onRevise }: {
  summary: unknown
  dirty: boolean
  onRevise?: (instruction: string) => void
}) {
  const report = toRecord(toRecord(parseMaybeJsonValue(summary))?.uiSemanticReview)
  if (!report) return null
  const modules = toRecordArray(report.modules)
  const count = modules.reduce((total, module) => total + toRecordArray(module.issues).length, 0)
  const stale = dirty || report.status === 'stale'
  const incomplete = report.status !== 'completed'
  const title = stale ? '草稿已修改，以下复核意见仅供参考'
    : incomplete ? 'AI 复核未完成，已保留用例草稿'
      : count ? `AI 复核提出 ${count} 条建议，由你决定是否修改`
        : 'AI 复核未发现问题，仍需人工审核'
  return <section className="ui-semantic-review" aria-label="AI 辅助复核">
    <Alert type={stale || incomplete || count ? 'warning' : 'info'} showIcon title={title} />
    {modules.length > 0 && (count > 0 || incomplete) ? <details>
      <summary>查看复核详情</summary>
      <div className="ui-semantic-review-details">
        {stale ? <p>报告对应修改前的草稿，用例和步骤位置可能已变化。请对照当前内容审核。</p> : null}
        {modules.map((module, moduleIndex) => <div key={moduleIndex}>
          <strong>{String(module.module ?? '未分组')}</strong>
          {module.status !== 'completed' ? <p>{errorLabels[String(module.errorCode)] ?? '复核未完成'}。可以人工核对草稿，或通过“继续优化”补充检查要求。</p> : null}
          {toRecordArray(module.issues).map((issue, issueIndex) => {
            const location = `用例 ${String(issue.caseIndex)}「${String(issue.caseName ?? '')}」· 步骤 ${String(issue.stepIndex)}`
            const instruction = `请核查以下 AI 复核意见，仅修正证据成立的问题，保留原业务预期和其他有效内容。\n${location}\n证据：${String(issue.evidence ?? '')}\n建议：${String(issue.repair ?? '')}`
            return <div className="ui-semantic-review-issue" key={issueIndex}>
              <strong>{location}</strong>
              <p>证据：{String(issue.evidence ?? '')}</p>
              <p>建议：{String(issue.repair ?? '')}</p>
              {onRevise ? <Button size="small" disabled={stale} onClick={() => onRevise(instruction)}>带入继续优化</Button> : null}
            </div>
          })}
        </div>)}
      </div>
    </details> : null}
  </section>
}
