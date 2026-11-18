import { Empty } from 'antd'
import type { UiTestCaseRun } from '@/services/api'

export function UiRunVariables({ run }: { run: UiTestCaseRun | null }) {
  const used = run?.usedVariables ?? []
  const writes = run?.variableWrites ?? []
  return <section className="ui-wb-run-variables [&_.ui-wb-console-snapshot-block+.ui-wb-console-snapshot-block]:mt-3" aria-label="运行变量详情">
    <div className="ui-wb-card-head"><strong>运行变量</strong><span className="ui-wb-console-meta max-w-[220px] overflow-hidden text-ellipsis whitespace-nowrap font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace]">{used.length} 次引用 / {writes.length} 次写回</span></div>
    {!used.length && !writes.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次运行没有变量记录" /> : null}
    {used.length ? <div className="ui-wb-console-snapshot-block"><div className="ui-wb-console-snapshot-label text-[11px] text-[var(--srf-text-muted)]">使用变量</div><ul className="ui-wb-variable-list m-0 mt-1 flex list-none flex-col gap-1 p-0 font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-[11px] leading-[18px]">
      {used.map((item, index) => <li className="grid grid-cols-[44px_minmax(80px,1fr)_minmax(0,1.6fr)] gap-2" key={`used-${item.name ?? ''}-${item.orderNo ?? ''}-${index}`}><span className="ui-wb-variable-order text-[var(--srf-text-muted)]">#{item.orderNo ?? '-'}</span><span className="ui-wb-variable-name overflow-hidden text-ellipsis whitespace-nowrap text-[var(--srf-text-secondary)]">{item.name ?? '-'}</span><span className="ui-wb-variable-value break-words text-[var(--srf-text)] [overflow-wrap:anywhere]">{item.secret ? '********' : item.value ?? ''}</span></li>)}
    </ul></div> : null}
    {writes.length ? <div className="ui-wb-console-snapshot-block"><div className="ui-wb-console-snapshot-label text-[11px] text-[var(--srf-text-muted)]">写回变量</div><ul className="ui-wb-variable-list m-0 mt-1 flex list-none flex-col gap-1 p-0 font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] text-[11px] leading-[18px]">
      {writes.map((item, index) => <li className="grid grid-cols-[44px_minmax(80px,1fr)_minmax(0,1.6fr)] gap-2" key={`write-${item.name ?? ''}-${item.orderNo ?? ''}-${index}`}><span className="ui-wb-variable-order text-[var(--srf-text-muted)]">#{item.orderNo ?? '-'}</span><span className="ui-wb-variable-name overflow-hidden text-ellipsis whitespace-nowrap text-[var(--srf-text-secondary)]">{item.name ?? '-'}</span><span className="ui-wb-variable-value break-words text-[var(--srf-text)] [overflow-wrap:anywhere]">{item.created ? '新建' : item.previousValue ?? '-'} → {item.value ?? ''}</span></li>)}
    </ul></div> : null}
  </section>
}
