import type { ReactNode } from 'react'
import { FileTextOutlined } from '@ant-design/icons'
import { Link, useNavigate } from 'react-router-dom'
import type { Requirement } from '@/features/requirements/types'
import { getRequirementDocumentSummary, getRequirementDocumentTypeLabel, hasRequirementDocument } from '@/features/requirements/utils/requirementDocument'
import { normalizeRequirementId } from '@/utils/format'
import { RequirementCodeSummary, RequirementCreatedTime } from './RequirementMetadata'
import { EntityCard } from '@/shared/components/EntityCard'

export function RequirementCards<T extends Requirement & { sprintName: string }>({ requirements, renderActions, renderBinding }: {
  requirements: T[]
  renderActions: (requirement: T) => ReactNode
  renderBinding?: (requirement: T) => ReactNode
}) {
  const navigate = useNavigate()
  return <div className="entity-card-grid requirements-card-grid" aria-label="需求列表">
    {requirements.map(requirement => {
      const id = normalizeRequirementId(requirement)
      const openRequirement = () => {
        if (id) navigate(`/requirements/${id}`)
      }
      const bindingStatus = renderBinding?.(requirement)
      const hasDocument = hasRequirementDocument(requirement)
      const documentSummary = getRequirementDocumentSummary(requirement)
      return <EntityCard key={id} className="requirements-card" titleId={`requirement-title-${id}`}
        title={<Link to={`/requirements/${id}`} title={requirement.name}>{requirement.name}</Link>}
        meta={[
          {
            label: '迭代版本',
            value: <span className="requirements-card-version"><span className="requirements-card-version-dot" aria-hidden="true" />{requirement.sprintName || '—'}</span>,
          },
          { label: '创建时间', value: <RequirementCreatedTime requirement={requirement} /> },
        ]}
        footerNote={<>
          {bindingStatus}
          {bindingStatus ? <span className="requirements-binding-separator" aria-hidden="true">·</span> : null}
          <RequirementCodeSummary requirement={requirement} variant="status" />
        </>}
        footerNoteClassName="requirements-card-bindings"
        actions={renderActions(requirement)}
        actionsClassName="requirements-card-actions"
        onOpen={openRequirement}>
        <div className="requirements-card-doc">
          <span className="requirements-card-doc-icon" aria-hidden="true"><FileTextOutlined /></span>
          {hasDocument ?
            <span className="requirements-card-doc-file" title={documentSummary}>
              <span className="requirements-card-doc-type">{getRequirementDocumentTypeLabel(requirement.documentType)}</span>
              <span className="requirements-card-doc-separator" aria-hidden="true">·</span>
              <span className="requirements-card-doc-name">{documentSummary}</span>
            </span> : <span className="requirements-card-doc-empty">未提供文档</span>}
        </div>
      </EntityCard>
    })}
  </div>
}
