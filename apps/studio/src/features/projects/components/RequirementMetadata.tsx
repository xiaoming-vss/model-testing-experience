import { Tooltip, Typography } from 'antd'
import { AppIcon } from '@/shared/icons'
import type { Requirement } from '@/features/requirements/types'
import { formatTime, pickCreatedAt } from '@/utils/format'

const { Text } = Typography

export function RequirementCodeSummary({ requirement, variant = 'summary' }: { requirement: Requirement; variant?: 'summary' | 'status' }) {
  const bindings = requirement.codeBindings
  const label = (binding: { repository: string; branch: string; baselineBranch?: string }) =>
    `${binding.repository}${binding.branch ? ` · ${binding.branch}` : ''}${binding.baselineBranch ? ` → ${binding.baselineBranch}` : ''}`
  if (variant === 'status') {
    const count = bindings?.length ?? 0
    const bound = count > 0
    const labels = (bindings ?? []).map(label)
    return <Tooltip title={bound ? <>{labels.map((item, index) => <div key={index}>{item}</div>)}</> : undefined}>
      <span className={`requirements-binding-item${bound ? ' is-bound' : ''}`} tabIndex={bound ? 0 : undefined}>
        <AppIcon name="gitlab" size={14} />
        <span>软件仓库 {bound ? `已关联${count > 1 ? `（${count}）` : ''}` : '未关联'}</span>
      </span>
    </Tooltip>
  }
  if (!bindings) return <Text type="secondary">—</Text>
  if (!bindings.length) return <Text type="secondary">未关联</Text>
  const labels = bindings.map(label)
  return <Tooltip title={<>{labels.map((item, index) => <div key={index}>{item}</div>)}</>}>
    <div className="requirements-list-wrap" tabIndex={0}>{labels[0]}{labels.length > 1 ? `（共 ${labels.length} 项）` : ''}</div>
  </Tooltip>
}

export function RequirementCreatedTime({ requirement }: { requirement: Requirement }) {
  const time = formatTime(pickCreatedAt(requirement))
  return <Tooltip title={time}><Text>{time.replace(/:\d{2}$/, '')}</Text></Tooltip>
}

