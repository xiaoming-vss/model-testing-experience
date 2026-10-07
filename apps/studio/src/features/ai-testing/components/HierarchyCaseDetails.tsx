import { Button, Tag } from 'antd'
import type { ReactNode } from 'react'
import type { CaseRelationsCaseMeta, RelationsGraphModel } from '../utils/caseRelationsGraph'
import type { HierarchyPlacedNode } from '../utils/relationsHierarchyLayout'

function DetailSection({ label, items }: { label: string; items?: string[] }) {
  return <div className="panel-section"><strong>{label}</strong>{items?.length ? <ol className="panel-list">{items.map((item, index) => <li key={index}>{item}</li>)}</ol> : <p className="panel-empty">无</p>}</div>
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
  return <aside className="ai-relations-panel ai-hierarchy-details" style={{ width }} aria-label="选中用例详情">
    <header className="panel-head"><span>选中用例 / {String(selected.meta.number).padStart(2, '0')}</span><Button size="small" type="text" aria-label="关闭选中用例面板" onClick={onClose}>×</Button></header>
    <div className="ai-hierarchy-associations">
      {([{ label: '前置关联', edges: incoming, incoming: true }, { label: '后续 / 分支', edges: outgoing, incoming: false }]).map((section) => <div key={section.label}>
        <span className="ai-hierarchy-association-title">{section.label} · {section.edges.length}</span>
        {section.edges.map((edge) => {
          const id = section.incoming ? edge.fromCaseId : edge.toCaseId
          const title = model.nodeById.get(id)?.title ?? id
          const label = `${section.incoming ? '前置' : edge.relationType === 'next' ? '后续' : '分支'}：${title}`
          return <Button key={edge.edgeId} type="text" size="small" title={`${label} · ${edge.edgeId}`} onClick={() => onNavigate(id)}>{label}<span>{edge.edgeId}</span></Button>
        })}
      </div>)}
    </div>
    {renderCaseDetails ? renderCaseDetails(caseId) : <>
      <div className="panel-tags"><Tag color={selected.main ? 'blue' : 'default'}>{selected.reference ? '主线引用' : selected.main ? '主线用例' : '分支用例'}</Tag>{meta?.priority ? <Tag color="orange">P{meta.priority}</Tag> : null}{meta?.caseType ? <Tag color="cyan">{meta.caseType}</Tag> : null}</div>
      <h3 className="panel-title">{selected.meta.title}</h3><p className="panel-uuid">{caseId}</p>
      <DetailSection label="前置条件" items={meta?.precondition} /><DetailSection label="测试步骤" items={meta?.testSteps} /><DetailSection label="预期结果" items={meta?.expectedResults} />
    </>}
  </aside>
}
