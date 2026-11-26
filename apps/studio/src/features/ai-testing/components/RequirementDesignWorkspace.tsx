import { ARTIFACT_MODAL_WIDTH } from './artifactModalLayout'
import { useState, type ReactNode } from 'react'
import { Modal } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import type { RequirementDesignKind } from '../api/requirementDesign.api'
import { RequirementDesignConfigurationModal } from './RequirementDesignConfigurationModal'
import { RequirementCodeRiskPanel } from './RequirementCodeRiskPanel'
import { RequirementGenerationPanorama, type RequirementReadingNode } from './RequirementGenerationPanorama'
import { useRequirementCodeRiskWorkspace } from '../hooks/useRequirementCodeRiskWorkspace'
import '@/shared/styles/list-table.css'
import taskStyles from '../styles/ai-task-detail.module.css'

/** 需求详情正文：生成全景是唯一入口，文档、代码风险和生成设置从泳道入口打开。 */
export function RequirementDesignWorkspace({ requirementId, projectId, canWrite, onOpenDocument, documentPreview, onReadingNodeChange, inspectorHost }: {
  requirementId: string
  projectId: string
  canWrite: boolean
  documentPreview?: ReactNode
  onOpenDocument?: () => void
  onReadingNodeChange?: (node: RequirementReadingNode | null) => void
  inspectorHost?: HTMLElement | null
}) {
  const [riskOpen, setRiskOpen] = useState(false)
  const [configureKind, setConfigureKind] = useState<RequirementDesignKind>()
  const client = useQueryClient()
  const codeRisk = useRequirementCodeRiskWorkspace(requirementId, projectId, riskOpen)
  const openPanoramaTab = (next: 'content' | RequirementDesignKind | 'codeRisk') => {
    if (next === 'content') { onOpenDocument?.(); return }
    if (next === 'codeRisk') { setRiskOpen(true); return }
    if (canWrite && (next === 'api' || next === 'ui')) setConfigureKind(next)
  }
  return <div className="ai-requirement-design tp-surface tp-list-surface flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden text-[var(--srf-text)] [&_.ant-empty]:px-4 [&_.ant-empty]:py-8">
    <div className="ai-requirement-design-panel ai-requirement-generation-panel flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <RequirementGenerationPanorama requirementId={requirementId} projectId={projectId} canWrite={canWrite} onOpenTab={openPanoramaTab} documentPreview={documentPreview} onReadingNodeChange={onReadingNodeChange} inspectorHost={inspectorHost} />
    </div>
    <Modal open={riskOpen} onCancel={() => setRiskOpen(false)} footer={null} width={ARTIFACT_MODAL_WIDTH} centered destroyOnHidden
      rootClassName={taskStyles.scope}
      className="requirement-code-risk-dialog" title="代码风险分析">
      <RequirementCodeRiskPanel workspace={codeRisk} canWrite={canWrite} />
    </Modal>
    {configureKind ? <RequirementDesignConfigurationModal key={configureKind} requirementId={requirementId} projectId={projectId} kind={configureKind}
      onClose={() => setConfigureKind(undefined)}
      onSaved={() => {
        setConfigureKind(undefined)
        void client.invalidateQueries({ queryKey: ['generationChain', requirementId] })
        void client.invalidateQueries({ queryKey: ['requirementDesignOverview', requirementId] })
      }} /> : null}
  </div>
}
