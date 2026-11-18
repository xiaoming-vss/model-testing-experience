import type { ReactNode } from 'react'
import { ArrowLeftOutlined, EditOutlined, SwapOutlined } from '@ant-design/icons'
import { Button, Space, Tooltip } from 'antd'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import type { Bug, BugAction } from '../types'
import { getBugActions, getBugStateLabel, formatBugNo, getBugActionLabel, getBugStatusTone } from '../utils/bugMeta'

export function BugDetailHeader({ bug, onBack, onTransition, onEdit, onTransfer, editingActions }: {
  editingActions?: ReactNode
  bug: Bug; onBack: () => void; onTransition: (action: BugAction) => void; onEdit: () => void; onTransfer: () => void
}) {
  const actions = getBugActions(bug)
  return (
        <section className="bugs-detail-topbar tp-list-toolbar sticky top-0 z-[3] flex flex-wrap items-center gap-3 bg-[var(--srf-card)]">
          <Button
            type="text"
            className="bug-back-button"
            aria-label="返回 Bug 列表"
            icon={<ArrowLeftOutlined />}
            onClick={onBack}
          >
            返回
          </Button>
          <span className="bug-no-chip inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-[var(--srf-chip)] px-2 py-0.5 text-xs text-[var(--srf-chip-text)]"><strong>{formatBugNo(bug.bugNo)}</strong></span>
          <span className={`bug-status-pill inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-[var(--srf-tone-border,var(--srf-card-border))] bg-[var(--srf-tone-bg,var(--srf-chip))] px-2 py-0.5 text-[11px] font-medium leading-[16px] text-[var(--srf-tone-text,var(--srf-chip-text))] tone-${getBugStatusTone(bug.status)}`}>
            <span className="bug-status-dot h-1.5 w-1.5 rounded-full bg-current" />
            {getBugStateLabel(bug)}
          </span>
          <Space wrap size={8} className="bug-detail-actions ml-auto whitespace-nowrap max-[720.01px]:ml-0 max-[720.01px]:basis-full">
            {editingActions ?? <>
            {actions.map((action) => (
              <ProjectActionButton action="bug_handle" projectId={bug.projectId}
                key={action}
                size="small"
                type={action === actions[0] ? 'primary' : 'default'}
                className={action === actions[0] ? 'bug-detail-primary-action' : undefined}
                danger={action === 'activate'}
                onClick={() => onTransition(action)}
              >
                {getBugActionLabel(action)}
              </ProjectActionButton>
            ))}
            <Tooltip title="编辑信息">
              <ProjectActionButton action="write" projectId={bug.projectId} size="small" icon={<EditOutlined />} aria-label="编辑 Bug" onClick={onEdit}>
                编辑
              </ProjectActionButton>
            </Tooltip>
            <Tooltip title="转派责任人">
              <ProjectActionButton action="bug_handle" projectId={bug.projectId} size="small" icon={<SwapOutlined />} aria-label="转派 Bug" onClick={onTransfer}>
                转派
              </ProjectActionButton>
            </Tooltip>
            </>}
          </Space>
        </section>
  )
}
