import { useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import '@/app/styles/asset-library.css'
import { PaneActivityProvider } from '@/shared/ui/PaneActivityProvider'
import { CaseLibraryPage } from '@/features/test-cases/pages/CaseLibraryPage'
import { SoftwareRepositoriesPage } from '@/features/interface-library/pages/SoftwareRepositoriesPage'
import { InterfaceLibraryPage } from '@/features/interface-library/pages/InterfaceLibraryPage'
import type { AssetLibraryTab } from '@/app/layouts/navigation'

const ASSET_TAB_PAGES = [
  { key: 'cases', Page: CaseLibraryPage },
  { key: 'interfaces', Page: InterfaceLibraryPage },
  { key: 'repositories', Page: SoftwareRepositoriesPage },
] as const

function resolveAssetTab(value: string | null): AssetLibraryTab {
  if (value === 'apps') return 'repositories'
  return value === 'interfaces' || value === 'repositories' ? value : 'cases'
}

export function AssetLibraryPage() {
  const [searchParams] = useSearchParams()
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

  return (
    <div className="workbench-page asset-library-page">
      <div className="asset-library-tab-panel">
        {ASSET_TAB_PAGES.map(({ key, Page }) => {
          if (!visitedTabs.has(key)) return null
          return (
            <div key={key} className="asset-library-tab-pane" id={`asset-panel-${key}`} hidden={activeTab !== key}>
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
