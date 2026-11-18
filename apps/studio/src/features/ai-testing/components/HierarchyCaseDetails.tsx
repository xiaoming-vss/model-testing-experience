import { Button, Tag } from 'antd'
import type { ReactNode } from 'react'
import type { CaseRelationsCaseMeta, RelationsGraphModel } from '../utils/caseRelationsGraph'
import type { HierarchyPlacedNode } from '../utils/relationsHierarchyLayout'

function DetailSection({ label, items }: { label: string; items?: string[] }) {
  return <div className="panel-section mt-1.5 flex flex-col gap-2.5"><strong className="text-[12.5px]">{label}</strong>{items?.length ? <ol className="panel-list m-0 flex list-none flex-col gap-2.5 p-0 text-[13px] leading-[1.72] [counter-reset:hierarchy-detail]">{items.map((item, index) => <li className="relative break-words pl-[26px] [counter-increment:hierarchy-detail]" key={index}>{item}</li>)}</ol> : <p className="panel-empty m-0 text-[12px] text-[var(--ant-color-text-tertiary)]">无</p>}</div>
}

export function HierarchyCaseDetails({ selected, model, meta, width, onClose, onNavigate, renderCaseDetails }: {
  selected: HierarchyPlacedNode
  model: RelationsGraphModel
  meta?: CaseRelationsCaseMeta
  width: number
  onClose: () => void
  onNavigate: (id: string) => void
  renderCaseDetails?: (id: string) => ReactNode
}) {
  const caseId = selected.meta.caseId
  const incoming = model.edges.filter((edge) => edge.toCaseId === caseId)
  const outgoing = model.edges.filter((edge) => edge.fromCaseId === caseId)
  const associations = <div className="ai-hierarchy-associations flex flex-col gap-2.5 rounded-[10px] border border-[var(--ant-color-border-secondary)] bg-[var(--ant-color-fill-quaternary)] px-3.5 py-3">
    {([{ label: '前置关联', edges: incoming, incoming: true }, { label: '后续 / 分支', edges: outgoing, incoming: false }]).map((section) => <div key={section.label}>
      <span className="ai-hierarchy-association-title text-[11.5px] text-[var(--ant-color-text-secondary)]">{section.label} · {section.edges.length}</span>
      {section.edges.map((edge) => {
        const id = section.incoming ? edge.fromCaseId : edge.toCaseId
        const title = model.nodeById.get(id)?.title ?? id
        const label = `${section.incoming ? '前置' : edge.relationType === 'next' ? '后续' : '分支'}：${title}`
        return <Button key={edge.edgeId} type="text" size="small" title={`${label} · ${edge.edgeId}`} onClick={() => onNavigate(id)}>{label}<span>{edge.edgeId}</span></Button>
      })}
    </div>)}
  </div>
  return <aside className="ai-relations-panel ai-hierarchy-details static m-0 min-h-0 max-w-[52%] flex-[0_1_auto] gap-3 rounded-none border-0 border-l border-[var(--ant-color-border-secondary)] px-[18px] pb-5 pt-4 shadow-none max-[768.01px]:max-w-full max-[768.01px]:border-l-0 max-[768.01px]:border-t" style={{ width }} aria-label="选中用例详情">
    <header className="panel-head flex items-center justify-between text-[12px] text-[var(--ant-color-text-secondary)]"><span>选中用例 / {String(selected.meta.number).padStart(2, '0')}</span><Button size="small" type="text" aria-label="关闭选中用例面板" onClick={onClose}>×</Button></header>
    {renderCaseDetails ? <>{associations}{renderCaseDetails(caseId)}</> : <>
      <div className="panel-tags flex flex-wrap gap-1.5"><Tag color={selected.main ? 'blue' : 'default'}>{selected.reference ? '主线引用' : selected.main ? '主线用例' : '分支用例'}</Tag>{meta?.priority ? <Tag color="orange">P{meta.priority}</Tag> : null}{meta?.caseType ? <Tag color="cyan">{meta.caseType}</Tag> : null}</div>
      <h3 className="panel-title m-0 text-[15px] leading-[1.55] break-words">{selected.meta.title}</h3><p className="panel-uuid m-0 break-all font-mono text-[11px] text-[var(--ant-color-text-tertiary)]">{caseId}</p>
      {associations}
      <DetailSection label="前置条件" items={meta?.precondition} /><DetailSection label="测试步骤" items={meta?.testSteps} /><DetailSection label="预期结果" items={meta?.expectedResults} />
    </>}
  </aside>
}
