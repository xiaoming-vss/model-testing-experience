import type { KeyboardEvent } from 'react'
import type { AssetLibraryTab } from '@/app/layouts/navigation'
import '@/shared/styles/page-navigation-tabs.css'
import '@/app/styles/asset-library.css'

const tabs: { key: AssetLibraryTab; label: string }[] = [
  { key: 'cases', label: '用例库' },
  { key: 'interfaces', label: '接口库' },
  { key: 'apps', label: '应用' },
]

type Props = {
  activeTab: AssetLibraryTab
  onSelect: (tab: AssetLibraryTab) => void
}

/** 资产库页签；列表外壳与接口库工作区共用同一组导航。 */
export function AssetLibraryTabs({ activeTab, onSelect }: Props) {
  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    const buttons = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'),
    )
    const index = buttons.indexOf(event.target as HTMLButtonElement)
    if (index < 0) return
    event.preventDefault()
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
      : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
    onSelect(tabs[next].key)
    buttons[next].focus()
  }

  return (
    <header className="asset-library-navigation">
      <div
        className="page-navigation-tabs"
        role="tablist"
        data-tab-motion-scoped
        aria-label="资产库"
        onKeyDown={handleKeyDown}
      >
        {tabs.map(tab => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            id={`asset-tab-${tab.key}`}
            aria-selected={activeTab === tab.key}
            aria-controls={`asset-panel-${tab.key}`}
            tabIndex={activeTab === tab.key ? 0 : -1}
            onClick={() => onSelect(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </header>
  )
}
