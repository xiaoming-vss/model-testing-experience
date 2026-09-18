import { AppIcon } from '@/shared/icons'
import type { ReactNode } from 'react'
import type { TestingTab } from './testingTab'

const tabOptions: Array<{
  key: TestingTab
  label: string
  icon: ReactNode
}> = [
  { key: 'functional', label: '功能测试', icon: <AppIcon name="functional" /> },
  { key: 'api', label: 'API测试', icon: <AppIcon name="api" /> },
  { key: 'ui', label: 'UI测试', icon: <AppIcon name="ui" /> },
]

export function TestingTabSwitcher({
  activeTab,
  onChange,
}: {
  activeTab: TestingTab
  onChange: (tab: TestingTab) => void
}) {
  return (
    <div className="testing-tab-switcher" role="tablist" aria-label="测试模块切换">
      {tabOptions.map((option) => {
        const active = option.key === activeTab
        return (
          <button
            key={option.key}
            type="button"
            role="tab"
            aria-selected={active}
            className={`testing-tab${active ? ' active' : ''}`}
            onClick={() => onChange(option.key)}
          >
            <span className="testing-tab-icon">{option.icon}</span>
            <span>{option.label}</span>
          </button>
        )
      })}
    </div>
  )
}
