import '../styles/requirement-workspace-tabs.css'
import { Tooltip } from 'antd'
import type { KeyboardEvent } from 'react'
import type { RequirementDesignKind } from '../api/requirementDesign.api'
import { requirementDesignKinds } from '../utils/requirementDesign'
import type { RequirementWorkspaceTab } from './RequirementDesignWorkspace'

export function RequirementWorkspaceTabs({ activeTab, includeDocument, counts, countError, codeRiskCount, codeRiskCountError, disabled, onChange }: {
  activeTab: RequirementWorkspaceTab; includeDocument: boolean
  counts?: Partial<Record<RequirementDesignKind, number>>; countError: boolean
  codeRiskCount?: number; codeRiskCountError?: boolean; disabled: boolean
  onChange: (tab: RequirementWorkspaceTab) => void
}) {
  const tabs: { key: RequirementWorkspaceTab; label: string }[] = [
    ...(includeDocument ? [{ key: 'content' as const, label: '需求文档' }] : []), ...requirementDesignKinds,
    { key: 'codeRisk' as const, label: '代码风险' },
  ]
  function navigateTabs(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
    const current = buttons.indexOf(event.target as HTMLButtonElement)
    if (current < 0) return
    event.preventDefault()
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
      : (current + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length
    onChange(tabs[next].key)
    buttons[next].focus()
    buttons[next].scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }
  return <div role="tablist" aria-label="需求工作区" className="ai-requirement-workspace-tabs" onKeyDown={navigateTabs}>
    {tabs.map(item => {
      const count = item.key === 'content' ? undefined : item.key === 'codeRisk' ? codeRiskCount : counts?.[item.key]
      const description = item.key === 'content' ? undefined : item.key === 'codeRisk'
        ? codeRiskCountError ? '运行次数读取失败，请在运行记录中重试读取。'
          : count === undefined ? '正在读取本需求的历史运行次数。'
          : `本需求的代码风险分析历史运行共 ${count} 次，含所有状态。`
        : countError ? '运行次数读取失败，请在运行记录中重试读取。'
        : count === undefined ? '正在读取本需求的历史运行次数。'
        : `本需求的${item.label}历史运行共 ${count} 次，含所有状态。`
      return <Tooltip key={item.key} id={`requirement-tab-${item.key}-count-description`} title={description} trigger={['hover', 'focus']}>
        <button role="tab" type="button" id={`requirement-tab-${item.key}`}
          aria-controls={item.key === 'content' ? 'requirement-panel-content'
            : item.key === 'codeRisk' ? 'requirement-panel-codeRisk' : 'requirement-panel-design'}
          aria-selected={activeTab === item.key} aria-description={description}
          tabIndex={activeTab === item.key ? 0 : -1} disabled={disabled} onClick={() => onChange(item.key)}>
          {item.label}{count !== undefined ? <span className="tp-chip-count">{count}</span> : null}
        </button>
      </Tooltip>
    })}
  </div>
}
