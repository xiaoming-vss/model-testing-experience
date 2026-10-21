import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Typography } from 'antd'
import type { Requirement } from '@/features/requirements/types'
import { getRequirementDocumentSummary, getRequirementDocumentTypeLabel, hasRequirementDocument } from '@/features/requirements/utils/requirementDocument'
import { normalizeRequirementId } from '@/utils/format'
import { RequirementCodeSummary, RequirementCreatedTime } from './RequirementMetadata'
import '../styles/requirements-list.css'

const { Text } = Typography

export function RequirementCards<T extends Requirement & { sprintName: string }>({ requirements, renderActions, renderBinding }: {
  requirements: T[]
  renderActions: (requirement: T) => ReactNode
  renderBinding?: (requirement: T) => ReactNode
}) {
  return <div className="requirements-card-grid" aria-label="需求列表">
    {requirements.map(requirement => {
      const id = normalizeRequirementId(requirement)
      return <article className="requirements-card" key={id} aria-labelledby={`requirement-title-${id}`}>
        <header className="requirements-card-heading">
          <h2 id={`requirement-title-${id}`}><Link to={`/requirements/${id}`} title={requirement.name}>{requirement.name}</Link></h2>
        </header>
        <dl className="requirements-card-details">
          <div className="requirements-card-document"><dt>需求文档</dt><dd>{hasRequirementDocument(requirement) ?
            <div className="requirements-list-file" title={getRequirementDocumentSummary(requirement)}>
              <span className="requirements-list-file-type">{getRequirementDocumentTypeLabel(requirement.documentType)}</span>
              <span className="requirements-list-filename">{getRequirementDocumentSummary(requirement)}</span>
            </div> : <Text type="secondary">未提供文档</Text>}</dd></div>
          <div><dt>所属迭代</dt><dd>{requirement.sprintName || '—'}</dd></div>
          <div><dt>创建时间</dt><dd><RequirementCreatedTime requirement={requirement} /></dd></div>
          <div><dt>禅道绑定</dt><dd>{renderBinding?.(requirement) ?? <Text type="secondary">未绑定</Text>}</dd></div>
          <div><dt>代码绑定</dt><dd><RequirementCodeSummary requirement={requirement} /></dd></div>
        </dl>
        <footer className="requirements-card-actions">{renderActions(requirement)}</footer>
      </article>
    })}
  </div>
}
