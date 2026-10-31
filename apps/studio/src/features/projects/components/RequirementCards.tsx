import type { ReactNode } from 'react'
import { FileTextOutlined } from '@ant-design/icons'
import { Link, useNavigate } from 'react-router-dom'
import type { Requirement } from '@/features/requirements/types'
import { getRequirementDocumentSummary, getRequirementDocumentTypeLabel, hasRequirementDocument } from '@/features/requirements/utils/requirementDocument'
import { normalizeRequirementId } from '@/utils/format'
import { RequirementCodeSummary, RequirementCreatedTime } from './RequirementMetadata'
import { isInteractiveCardTarget } from '../utils/cardNavigation'
import '../styles/requirements-list.css'

export function RequirementCards<T extends Requirement & { sprintName: string }>({ requirements, renderActions, renderBinding }: {
  requirements: T[]
  renderActions: (requirement: T) => ReactNode
  renderBinding?: (requirement: T) => ReactNode
}) {
  const navigate = useNavigate()
  return <div className="requirements-card-grid" aria-label="需求列表">
    {requirements.map(requirement => {
      const id = normalizeRequirementId(requirement)
      const openRequirement = () => {
        if (id) navigate(`/requirements/${id}`)
      }
      const bindingStatus = renderBinding?.(requirement)
      const hasDocument = hasRequirementDocument(requirement)
      const documentSummary = getRequirementDocumentSummary(requirement)
      return <article className="requirements-card" key={id} aria-labelledby={`requirement-title-${id}`}
        onClick={(event) => {
          if (isInteractiveCardTarget(event.target)) return
          openRequirement()
        }}>
        <div className="requirements-card-main">
          <h2 className="requirements-card-title" id={`requirement-title-${id}`}>
            <Link to={`/requirements/${id}`} title={requirement.name}>{requirement.name}</Link>
          </h2>
          <div className="requirements-card-doc">
            <span className="requirements-card-doc-icon" aria-hidden="true"><FileTextOutlined /></span>
            {hasDocument ?
              <span className="requirements-card-doc-file" title={documentSummary}>
                <span className="requirements-card-doc-type">{getRequirementDocumentTypeLabel(requirement.documentType)}</span>
                <span className="requirements-card-doc-separator" aria-hidden="true">·</span>
                <span className="requirements-card-doc-name">{documentSummary}</span>
              </span> : <span className="requirements-card-doc-empty">未提供文档</span>}
          </div>
          <dl className="requirements-card-meta">
            <div>
              <dt>迭代版本</dt>
              <dd className="requirements-card-version"><span className="requirements-card-version-dot" aria-hidden="true" />{requirement.sprintName || '—'}</dd>
            </div>
            <div><dt>创建时间</dt><dd><RequirementCreatedTime requirement={requirement} /></dd></div>
          </dl>
        </div>
        <footer className="requirements-card-foot">
          <div className="requirements-card-bindings">
            {bindingStatus}
            {bindingStatus ? <span className="requirements-binding-separator" aria-hidden="true">·</span> : null}
            <RequirementCodeSummary requirement={requirement} variant="status" />
          </div>
          <div className="requirements-card-actions">{renderActions(requirement)}</div>
        </footer>
      </article>
    })}
  </div>
}
