import { resolveTestingTab } from '@/features/testing/components/testingTab'

export function testingTabForLocation(pathname: string, search: string) {
  return pathname.startsWith('/test-orders') ? 'orders'
    : pathname.startsWith('/bugs') ? 'bugs'
      : pathname.startsWith('/api-automation') ? 'api'
        : pathname.startsWith('/ui-automation') ? 'ui'
          : pathname === '/testing'
            ? resolveTestingTab(new URLSearchParams(search).get('tab')) : null
}

export type AssetLibraryTab = 'cases' | 'interfaces' | 'apps'

export function assetTabForLocation(pathname: string, search: string): AssetLibraryTab | null {
  if (!pathname.startsWith('/asset-library')) return null
  if (pathname.startsWith('/asset-library/interfaces')) return 'interfaces'
  const tab = new URLSearchParams(search).get('tab')
  return tab === 'interfaces' || tab === 'apps' ? tab : 'cases'
}

// Order follows the visible top-level navigation; null denotes an unrelated page.
export function navigationIndex(pathname: string, search: string, bugOnly: boolean): number | null {
  const testingTab = testingTabForLocation(pathname, search)
  if (bugOnly) return testingTab === 'bugs' ? 4 : null
  if (pathname.startsWith('/requirements')) return 1
  if (pathname.startsWith('/projects')) return new URLSearchParams(search).get('board') === 'requirements' ? 1 : 0
  if (testingTab === 'bugs') return 4
  if (testingTab) return 2
  if (assetTabForLocation(pathname, search)) return 3
  if (pathname.startsWith('/base-services')) return 5
  return null
}
