import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-review.css'
export function CaseComparison<T extends object>({ fields, existing, generated, formatValue }: {
  fields: Array<{ key: keyof T; label: string }>
  existing: T
  generated: T
  formatValue: (value: unknown) => string
}) {
  return (
    <div className="api-import-conflict-comparison">
      <div className="api-import-conflict-heading">字段</div>
      <div className="api-import-conflict-heading">当前正式用例</div>
      <div className="api-import-conflict-heading">已批准候选用例</div>
      {fields.map(({ key, label }) => (
        <div className="api-import-conflict-row" key={String(key)}>
          <div className="api-import-conflict-label">{label}</div>
          <pre className="api-import-conflict-value">{formatValue(existing[key])}</pre>
          <pre className="api-import-conflict-value">{formatValue(generated[key])}</pre>
        </div>
      ))}
    </div>
  )
}
