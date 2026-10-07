import { useEffect, useMemo, type ReactNode, type Ref } from 'react'
import { Empty } from 'antd'
import { buildRelationsGraphModel, parseCaseRelationsContent, parseDetailedCaseMeta, type CaseRelationsCaseMeta, type RelationsGraphModel } from '../utils/caseRelationsGraph'
import { useRelationsHierarchyView } from '../hooks/useRelationsHierarchyView'
import { useHierarchyFlow } from '../hooks/useHierarchyFlow'
import { useHierarchyViewport } from '../hooks/useHierarchyViewport'
import { HierarchyGraphToolbar } from './HierarchyGraphToolbar'
import { HierarchyGraphCanvas } from './HierarchyGraphCanvas'
import { HierarchyCaseDetails } from './HierarchyCaseDetails'
import type { HierarchyCaseBadge } from './HierarchyGraphNodes'
import type { FunctionalCaseRelationsGraphHandle } from './FunctionalCaseRelationsGraph'
import '../styles/relations-hierarchy.css'

export type HierarchicalGraphProps = {
  content: string
  casesContent?: string
  onSelectionChange?: (id: string | null) => void
  handleRef: Ref<FunctionalCaseRelationsGraphHandle>
  renderCaseDetails?: (caseId: string) => ReactNode
  caseBadges?: Record<string, HierarchyCaseBadge>
  panelWidth?: number
}

function HierarchyGraphView({ model, caseMeta, onSelectionChange, handleRef, renderCaseDetails, caseBadges, panelWidth = 296 }: Omit<HierarchicalGraphProps, 'content' | 'casesContent'> & {
  model: RelationsGraphModel
  caseMeta: Map<string, CaseRelationsCaseMeta>
}) {
  const view = useRelationsHierarchyView(model)
  const graph = useHierarchyFlow(view, model, caseBadges)
  const viewport = useHierarchyViewport(view.layout, view.selectedId, handleRef, view.layoutAnchorId)
  const selected = view.selectedNode
  const selectedCaseId = selected?.meta.caseId ?? null
  useEffect(() => { onSelectionChange?.(selectedCaseId) }, [selectedCaseId, onSelectionChange])
  useEffect(() => () => onSelectionChange?.(null), [onSelectionChange])
  const visibleCases = new Set([...view.layout?.nodes.values() ?? []].map((node) => node.meta.caseId)).size
  return <div className="ai-relations-hierarchy">
    <div className="ai-hierarchy-body">
      <HierarchyGraphCanvas graph={graph} canvasRef={viewport.canvasRef} onSelect={view.select} onFit={() => viewport.fitView()} controls={<HierarchyGraphToolbar view={view} />} />
      {selected ? <HierarchyCaseDetails selected={selected} model={model} meta={caseMeta.get(selected.meta.caseId)} width={panelWidth}
        onClose={() => view.select(null)} onNavigate={view.navigate} renderCaseDetails={renderCaseDetails} /> : null}
    </div>
    <footer className="ai-hierarchy-footer" aria-live="polite"><span>当前显示 {visibleCases}/{model.nodes.length} 个用例 · {graph.drawnCount}/{model.edges.length} 条关联</span>
      <span>{graph.routing.pending ? '正在调整其余关联连线' : '拖动空白平移 · 滚轮缩放 · 点击用例聚焦关联'}</span></footer>
  </div>
}

export function HierarchicalCaseRelationsGraph({ content, casesContent, ...props }: HierarchicalGraphProps) {
  const data = useMemo(() => parseCaseRelationsContent(content), [content])
  const caseMeta = useMemo(() => parseDetailedCaseMeta(casesContent), [casesContent])
  const model = useMemo(() => data ? buildRelationsGraphModel(data, caseMeta) : null, [data, caseMeta])
  if (!model?.nodes.length) return <div className="ai-relations-graph"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={data ? '图谱暂无用例节点' : '图谱数据暂不可解析，请在 json 页签查看原始数据'} /></div>
  return <HierarchyGraphView key={content} model={model} caseMeta={caseMeta} {...props} />
}
