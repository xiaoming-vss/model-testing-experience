import { lazy, useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { RouteSuspense } from '@/app/router/RouteSuspense'
import { PaneActivityProvider } from '@/shared/ui/PaneActivityProvider'
import { resolveAssetLibraryTab, type AssetLibraryTab } from '@/app/layouts/navigation'
import {
  ASSET_LIBRARY_PAGE_CLASS,
  ASSET_LIBRARY_TAB_PANEL_CLASS,
  ASSET_LIBRARY_TAB_PANE_CLASS,
} from '@/shared/ui/assetLibraryShell'

const CaseLibraryPage = lazy(() => import('@/features/test-cases/pages/CaseLibraryPage').then(({ CaseLibraryPage }) => ({ default: CaseLibraryPage })))
const SoftwareRepositoriesPage = lazy(() => import('@/features/interface-library/pages/SoftwareRepositoriesPage').then(({ SoftwareRepositoriesPage }) => ({ default: SoftwareRepositoriesPage })))
const InterfaceLibraryPage = lazy(() => import('@/features/interface-library/pages/InterfaceLibraryPage').then(({ InterfaceLibraryPage }) => ({ default: InterfaceLibraryPage })))
const ElementLibraryPage = lazy(() => import('@/features/element-library/pages/ElementLibraryPage').then(({ ElementLibraryPage }) => ({ default: ElementLibraryPage })))

const ASSET_TAB_PAGES = [
  { key: 'cases', Page: CaseLibraryPage },
  { key: 'interfaces', Page: InterfaceLibraryPage },
  { key: 'elements', Page: ElementLibraryPage },
  { key: 'repositories', Page: SoftwareRepositoriesPage },
] as const

export function AssetLibraryPage() {
  const [searchParams] = useSearchParams()
  const activeTab = resolveAssetLibraryTab(searchParams.get('tab'))
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
    <div className={ASSET_LIBRARY_PAGE_CLASS}>
      <div className={ASSET_LIBRARY_TAB_PANEL_CLASS}>
        {ASSET_TAB_PAGES.map(({ key, Page }) => {
          if (!visitedTabs.has(key)) return null
          return (
            <div key={key} className={ASSET_LIBRARY_TAB_PANE_CLASS} id={`asset-panel-${key}`} hidden={activeTab !== key}>
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
