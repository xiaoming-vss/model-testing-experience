import { useState, type ReactNode } from 'react'
import { Modal } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import type { RequirementDesignKind } from '../api/requirementDesign.api'
import { RequirementDesignConfigurationModal } from './RequirementDesignConfigurationModal'
import { RequirementCodeRiskPanel } from './RequirementCodeRiskPanel'
import { RequirementGenerationPanorama } from './RequirementGenerationPanorama'
import { useRequirementCodeRiskWorkspace } from '../hooks/useRequirementCodeRiskWorkspace'
import '../styles/index.css'
import '../styles/task-detail-v2.css'
import '@/shared/styles/list-table.css'
import '../styles/requirement-design.css'

/** 需求详情正文：生成全景是唯一入口，文档、代码风险和生成设置从泳道入口打开。 */
export function RequirementDesignWorkspace({ requirementId, projectId, canWrite, onOpenDocument, documentPreview }: {
  requirementId: string
  projectId: string
  canWrite: boolean
  documentPreview?: ReactNode
  onOpenDocument?: () => void
}) {
  const [riskOpen, setRiskOpen] = useState(false)
  const [configureKind, setConfigureKind] = useState<RequirementDesignKind>()
  const client = useQueryClient()
  const codeRisk = useRequirementCodeRiskWorkspace(requirementId, projectId, riskOpen)
  const openPanoramaTab = (next: 'content' | RequirementDesignKind | 'codeRisk') => {
    if (next === 'content') { onOpenDocument?.(); return }
    if (next === 'codeRisk') { setRiskOpen(true); return }
    setConfigureKind(next)
  }
  return <div className="ai-requirement-design tp-surface tp-list-surface">
    <div className="ai-requirement-design-panel ai-requirement-generation-panel">
      <RequirementGenerationPanorama requirementId={requirementId} projectId={projectId} canWrite={canWrite} onOpenTab={openPanoramaTab} documentPreview={documentPreview} />
    </div>
    <Modal open={riskOpen} onCancel={() => setRiskOpen(false)} footer={null} width="min(2000px, calc(100vw - 56px))" centered destroyOnHidden
      className="requirement-code-risk-dialog" title="代码风险分析">
      <RequirementCodeRiskPanel workspace={codeRisk} canWrite={canWrite} />
    </Modal>
    {configureKind ? <RequirementDesignConfigurationModal key={configureKind} requirementId={requirementId} kind={configureKind} tasks={[]}
      onClose={() => setConfigureKind(undefined)}
      onSaved={() => {
        setConfigureKind(undefined)
        void client.invalidateQueries({ queryKey: ['generationChain', requirementId] })
      }} /> : null}
  </div>
}
