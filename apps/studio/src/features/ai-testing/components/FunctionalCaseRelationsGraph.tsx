import { forwardRef, type ReactNode } from 'react'
import { ReactFlowProvider } from '@xyflow/react'
import { HierarchicalCaseRelationsGraph } from './HierarchicalCaseRelationsGraph'
import type { HierarchyCaseBadge } from './HierarchyGraphNodes'

export type FunctionalCaseRelationsGraphHandle = {
  fitView: () => void
  locateSelected: () => void
}

export const FunctionalCaseRelationsGraph = forwardRef<FunctionalCaseRelationsGraphHandle, {
  content: string
  casesContent?: string
  onSelectionChange?: (caseId: string | null) => void
  children?: ReactNode
  renderCaseDetails?: (caseId: string) => ReactNode
  caseBadges?: Record<string, HierarchyCaseBadge>
  panelWidth?: number
}>(function FunctionalCaseRelationsGraph({ content, casesContent, onSelectionChange, renderCaseDetails, caseBadges, panelWidth }, ref) {
  return (
    <ReactFlowProvider>
      <HierarchicalCaseRelationsGraph content={content} casesContent={casesContent} onSelectionChange={onSelectionChange} handleRef={ref}
        renderCaseDetails={renderCaseDetails} caseBadges={caseBadges} panelWidth={panelWidth} />
    </ReactFlowProvider>
  )
})
