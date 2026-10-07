import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { Button, Tag } from 'antd'
import type { HierarchyPlacedNode } from '../utils/relationsHierarchyLayout'

export type HierarchyCaseBadge = { label: string; color: string }
export type HierarchyNodeData = {
  placed: HierarchyPlacedNode
  badge?: HierarchyCaseBadge
  dimmed: boolean
  count: number
  expanded: boolean
  onToggle: (id: string) => void
}
export type HierarchyCaseNode = Node<HierarchyNodeData, 'hierarchyCase'>

export function HierarchyNode({ id, data }: NodeProps<HierarchyCaseNode>) {
  const { placed, badge, dimmed } = data
  const { meta, main, depth, reference, groupLabel } = placed
  const level = ['', '一级分支', '二级分支', '三级分支'][depth] ?? `第 ${depth} 级分支`
  const label = meta.isolated ? '独立用例' : reference ? '主线引用' : main ? `${groupLabel} · ${meta.shared ? '共享用例' : '主线用例'}` : level
  return <div className={`ai-relations-node ai-hierarchy-node${main ? ' main' : ''}${dimmed ? ' dimmed' : ''}`} title={meta.title}>
    <Handle type="source" position={Position.Top} isConnectable={false} style={{ opacity: 0 }} />
    <Handle type="target" position={Position.Top} isConnectable={false} style={{ opacity: 0 }} />
    <span className="node-head"><span className="node-no">{String(meta.number).padStart(2, '0')}</span><span className="node-kind">{label}</span></span>
    <span className="node-title">{meta.title}</span>
    <div className="ai-hierarchy-node-footer">
      {badge ? <Tag color={badge.color} aria-label={`执行状态：${badge.label}`}>{badge.label}</Tag> : <span className="ai-hierarchy-node-id">{meta.caseId.slice(0, 8)}</span>}
      {data.count ? <Button size="small" type="link" className="nodrag" aria-label={`${data.expanded ? '收起' : '展开'}用例 ${meta.number} 的 ${data.count} 个关联`} aria-expanded={data.expanded}
        onClick={(event) => { event.stopPropagation(); data.onToggle(id) }}>{data.expanded ? '收起' : '分支'} {data.count}</Button> : null}
    </div>
  </div>
}
