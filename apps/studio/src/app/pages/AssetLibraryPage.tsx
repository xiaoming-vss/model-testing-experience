import { lazy, useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { RouteSuspense } from '@/app/router/RouteSuspense'
import { PaneActivityProvider } from '@/shared/ui/PaneActivityProvider'
import type { AssetLibraryTab } from '@/app/layouts/navigation'

const CaseLibraryPage = lazy(() => import('@/features/test-cases/pages/CaseLibraryPage').then(({ CaseLibraryPage }) => ({ default: CaseLibraryPage })))
const SoftwareRepositoriesPage = lazy(() => import('@/features/interface-library/pages/SoftwareRepositoriesPage').then(({ SoftwareRepositoriesPage }) => ({ default: SoftwareRepositoriesPage })))
const InterfaceLibraryPage = lazy(() => import('@/features/interface-library/pages/InterfaceLibraryPage').then(({ InterfaceLibraryPage }) => ({ default: InterfaceLibraryPage })))

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
    <div className="workbench-page asset-library-page flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="asset-library-tab-panel flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {ASSET_TAB_PAGES.map(({ key, Page }) => {
          if (!visitedTabs.has(key)) return null
          return (
            <div key={key} className="asset-library-tab-pane flex min-h-0 min-w-0 flex-1 flex-col [&[hidden]]:hidden [&>.workbench-page]:min-h-0 [&>.workbench-page]:flex-auto [&>.workbench-page]:p-0" id={`asset-panel-${key}`} hidden={activeTab !== key}>
              <PaneActivityProvider active={activeTab === key}>
                <RouteSuspense>
                  <Page />
                </RouteSuspense>
              </PaneActivityProvider>
            </div>
          )
        })}
      </div>
    </div>
  )
}
