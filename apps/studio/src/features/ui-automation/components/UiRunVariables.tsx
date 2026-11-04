import { Empty } from 'antd'
import type { UiTestCaseRun } from '@/services/api'

export function UiRunVariables({ run }: { run: UiTestCaseRun | null }) {
  const used = run?.usedVariables ?? []
  const writes = run?.variableWrites ?? []
  return <section className="ui-wb-run-variables" aria-label="运行变量详情">
    <div className="ui-wb-card-head"><strong>运行变量</strong><span className="ui-wb-console-meta">{used.length} 次引用 / {writes.length} 次写回</span></div>
    {!used.length && !writes.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次运行没有变量记录" /> : null}
    {used.length ? <div className="ui-wb-console-snapshot-block"><div className="ui-wb-console-snapshot-label">使用变量</div><ul className="ui-wb-variable-list">
      {used.map((item, index) => <li key={`used-${item.name ?? ''}-${item.orderNo ?? ''}-${index}`}><span className="ui-wb-variable-order">#{item.orderNo ?? '-'}</span><span className="ui-wb-variable-name">{item.name ?? '-'}</span><span className="ui-wb-variable-value">{item.secret ? '********' : item.value ?? ''}</span></li>)}
    </ul></div> : null}
    {writes.length ? <div className="ui-wb-console-snapshot-block"><div className="ui-wb-console-snapshot-label">写回变量</div><ul className="ui-wb-variable-list">
      {writes.map((item, index) => <li key={`write-${item.name ?? ''}-${item.orderNo ?? ''}-${index}`}><span className="ui-wb-variable-order">#{item.orderNo ?? '-'}</span><span className="ui-wb-variable-name">{item.name ?? '-'}</span><span className="ui-wb-variable-value">{item.created ? '新建' : item.previousValue ?? '-'} → {item.value ?? ''}</span></li>)}
    </ul></div> : null}
  </section>
}
