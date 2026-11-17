import { resolveTestingTab } from '@/features/testing/components/testingTab'

export function testingTabForLocation(pathname: string, search: string) {
  return pathname.startsWith('/test-orders') ? 'orders'
    : pathname.startsWith('/bugs') ? 'bugs'
      : pathname.startsWith('/api-automation') ? 'api'
        : pathname.startsWith('/ui-automation') ? 'ui'
        : pathname.startsWith('/performance') ? 'perf'
          : pathname === '/testing'
            ? resolveTestingTab(new URLSearchParams(search).get('tab')) : null
}

export type AssetLibraryTab = 'cases' | 'interfaces' | 'repositories'

export const ASSET_LIBRARY_TABS = [
  { key: 'cases', label: '用例库' },
  { key: 'interfaces', label: '接口库' },
  { key: 'repositories', label: '软件仓库' },
] as const satisfies readonly { key: AssetLibraryTab; label: string }[]

export function assetTabForLocation(pathname: string, search: string): AssetLibraryTab | null {
  if (!pathname.startsWith('/asset-library')) return null
  if (pathname.startsWith('/asset-library/interfaces')) return 'interfaces'
  const tab = new URLSearchParams(search).get('tab')
  if (tab === 'apps') return 'repositories'
  return tab === 'interfaces' || tab === 'repositories' ? tab : 'cases'
}

// Order follows the visible top-level navigation; null denotes an unrelated page.
// 迭代 0 → 需求 1 → 测试 2 → Bug 列表 3 → 资产库 4 → 基础服务 5
export function navigationIndex(pathname: string, search: string, bugOnly: boolean): number | null {
  const testingTab = testingTabForLocation(pathname, search)
  if (bugOnly) return testingTab === 'bugs' ? 3 : null
  if (pathname.startsWith('/requirements')) return 1
  if (pathname.startsWith('/projects')) return new URLSearchParams(search).get('board') === 'requirements' ? 1 : 0
  if (testingTab === 'bugs') return 3
  if (testingTab) return 2
  if (assetTabForLocation(pathname, search)) return 4
  if (pathname.startsWith('/base-services')) return 5
  return null
}
