import '@/shared/styles/page-navigation-tabs.css'
import type { KeyboardEvent } from 'react'
import type { TestingTab } from './testingTab'
import '../styles/navigation.css'

const tabs = [
  { key: 'orders', label: '测试单' },
  { key: 'library', label: '用例库' },
  { key: 'api', label: 'API测试' },
  { key: 'ui', label: 'UI测试' },
] as const

export function TestingNavigation({ activeTab, onChange }: {
  activeTab: TestingTab
  onChange: (tab: TestingTab) => void
}) {
  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
    const index = buttons.indexOf(event.target as HTMLButtonElement)
    if (index < 0) return
    event.preventDefault()
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
      : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
    onChange(tabs[next].key)
    buttons[next].focus()
    buttons[next].scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }

  return <header className="testing-navigation">
    <div className="testing-navigation-tabs page-navigation-tabs" role="tablist" aria-label="测试工作区" onKeyDown={handleKeyDown}>
      {tabs.map(tab => <button key={tab.key} type="button" role="tab" id={`testing-tab-${tab.key}`}
        aria-selected={activeTab === tab.key} aria-controls={`testing-panel-${tab.key}`}
        tabIndex={activeTab === tab.key ? 0 : -1} onClick={() => onChange(tab.key)}>
        {tab.label}
      </button>)}
    </div>
  </header>
}
