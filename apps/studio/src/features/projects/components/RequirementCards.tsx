import type { ReactNode } from 'react'
import { FileTextOutlined } from '@ant-design/icons'
import { Link, useNavigate } from 'react-router-dom'
import type { Requirement } from '@/features/requirements/types'
import { getRequirementDocumentSummary, getRequirementDocumentTypeLabel, hasRequirementDocument } from '@/features/requirements/utils/requirementDocument'
import { normalizeRequirementId } from '@/utils/format'
import { RequirementCodeSummary, RequirementCreatedTime } from './RequirementMetadata'
import { EntityCard } from '@/shared/components/EntityCard'
import { entityCardGridClass } from '@/shared/utils/surfaceClasses'

export function RequirementCards<T extends Requirement & { sprintName: string }>({ requirements, renderActions, renderBinding }: {
  requirements: T[]
  renderActions: (requirement: T) => ReactNode
  renderBinding?: (requirement: T) => ReactNode
}) {
  const navigate = useNavigate()
  return <div className={`entity-card-grid requirements-card-grid ${entityCardGridClass}`} aria-label="需求列表">
    {requirements.map(requirement => {
      const id = normalizeRequirementId(requirement)
      const openRequirement = () => {
        if (id) navigate(`/requirements/${id}`)
      }
      const bindingStatus = renderBinding?.(requirement)
      const hasDocument = hasRequirementDocument(requirement)
      const documentSummary = getRequirementDocumentSummary(requirement)
      return <EntityCard key={id} className="requirements-card max-[680.01px]:[&_.entity-card-foot]:flex-wrap" titleId={`requirement-title-${id}`}
        title={<Link to={`/requirements/${id}`} title={requirement.name}>{requirement.name}</Link>}
        meta={[
          {
            label: '迭代版本',
            value: <span className="requirements-card-version inline-flex items-center gap-[5px]"><span className="requirements-card-version-dot h-[5px] w-[5px] flex-none rounded-full bg-[var(--app-action-read)]" aria-hidden="true" />{requirement.sprintName || '—'}</span>,
          },
          { label: '创建时间', value: <RequirementCreatedTime requirement={requirement} /> },
        ]}
        footerNote={<>
          {bindingStatus}
          {bindingStatus ? <span className="requirements-binding-separator text-[var(--srf-text-muted)] opacity-[0.55]" aria-hidden="true">·</span> : null}
          <RequirementCodeSummary requirement={requirement} variant="status" />
        </>}
        footerNoteClassName="requirements-card-bindings flex min-w-0 flex-[1_1_auto] flex-wrap items-center gap-2.5 whitespace-normal text-[10.5px] leading-[18px] text-[var(--srf-text-secondary)] max-[680.01px]:flex-[1_1_100%]"
        actions={renderActions(requirement)}
        actionsClassName="requirements-card-actions flex flex-none items-center justify-end max-[680.01px]:ml-auto"
        onOpen={openRequirement}>
        <div className="requirements-card-doc m-0 mb-2.5 flex min-h-[22px] min-w-0 items-center gap-2 text-[10.5px] leading-4 text-[var(--srf-text-secondary)]">
          <span className="requirements-card-doc-icon inline-flex h-[22px] w-[22px] flex-none items-center justify-center rounded-[6px] bg-[var(--app-accent-surface)] text-[13px] text-[var(--app-action-read)]" aria-hidden="true"><FileTextOutlined /></span>
          {hasDocument ?
            <span className="requirements-card-doc-file flex min-w-0 items-center gap-[5px]" title={documentSummary}>
              <span className="requirements-card-doc-type flex-none font-medium">{getRequirementDocumentTypeLabel(requirement.documentType)}</span>
              <span className="requirements-card-doc-separator flex-none text-[var(--srf-text-muted)]" aria-hidden="true">·</span>
              <span className="requirements-card-doc-name min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">{documentSummary}</span>
            </span> : <span className="requirements-card-doc-empty text-[var(--srf-text-secondary)]">未提供文档</span>}
        </div>
      </EntityCard>
    })}
  </div>
}
