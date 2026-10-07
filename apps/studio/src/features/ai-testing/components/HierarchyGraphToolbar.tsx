import { Button } from 'antd'
import type { useRelationsHierarchyView } from '../hooks/useRelationsHierarchyView'

export type HierarchyView = ReturnType<typeof useRelationsHierarchyView>

export function HierarchyGraphToolbar({ view }: { view: HierarchyView }) {
  if (!view.canExpand) return null
  return <div className="ai-hierarchy-toolbar">
    <Button size="small" onClick={view.toggleAll}>{view.allExpanded ? '折叠全部' : '展开全部'}</Button>
  </div>
}
