import { useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import '@/shared/styles/page-navigation-tabs.css'
import '@/app/styles/asset-library.css'
import { AssetLibraryTabs } from './AssetLibraryTabs'
import { PaneActivityProvider } from '@/shared/ui/PaneActivityProvider'
import { CaseLibraryPage } from '@/features/test-cases/pages/CaseLibraryPage'
import { ApiAppsPage } from '@/features/interface-library/pages/ApiAppsPage'
import { InterfaceLibraryPage } from '@/features/interface-library/pages/InterfaceLibraryPage'
import type { AssetLibraryTab } from '@/app/layouts/navigation'

const ASSET_TAB_PAGES = [
  { key: 'cases', Page: CaseLibraryPage },
  { key: 'interfaces', Page: InterfaceLibraryPage },
  { key: 'apps', Page: ApiAppsPage },
] as const

function resolveAssetTab(value: string | null): AssetLibraryTab {
  return value === 'interfaces' || value === 'apps' ? value : 'cases'
}

export function AssetLibraryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = resolveAssetTab(searchParams.get('tab'))
  const [visitedTabs, setVisitedTabs] = useState(() => new Set<AssetLibraryTab>([activeTab]))

  useEffect(() => {
    setVisitedTabs(previous => {
      if (previous.has(activeTab)) return previous
      const next = new Set(previous)
      next.add(activeTab)
      return next
    })
  }, [activeTab])

  if (!searchParams.get('tab')) {
    return <Navigate to="/asset-library?tab=cases" replace />
  }

  function changeTab(tab: AssetLibraryTab) {
    const params = new URLSearchParams(searchParams)
    params.set('tab', tab)
    setSearchParams(params)
  }

  return (
    <div className="workbench-page asset-library-page" data-tab-motion-scope>
      <AssetLibraryTabs activeTab={activeTab} onSelect={changeTab} />
      <div className="asset-library-tab-panel" data-tab-motion-panel>
        {ASSET_TAB_PAGES.map(({ key, Page }) => {
          if (!visitedTabs.has(key)) return null
          return (
            <div
              key={key}
              className="asset-library-tab-pane"
              role="tabpanel"
              id={`asset-panel-${key}`}
              aria-labelledby={`asset-tab-${key}`}
              hidden={activeTab !== key}
            >
              <PaneActivityProvider active={activeTab === key}>
                <Page />
              </PaneActivityProvider>
            </div>
          )
        })}
      </div>
    </div>
  )
}
