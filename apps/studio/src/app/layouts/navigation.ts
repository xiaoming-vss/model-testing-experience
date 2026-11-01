import { resolveTestingTab } from '@/features/testing/components/testingTab'

export function testingTabForLocation(pathname: string, search: string) {
  return pathname.startsWith('/test-orders') ? 'orders'
    : pathname.startsWith('/bugs') ? 'bugs'
      : pathname.startsWith('/api-automation') ? 'api'
        : pathname.startsWith('/ui-automation') ? 'ui'
          : pathname.startsWith('/test-cases') ? 'library' : pathname === '/testing'
            ? resolveTestingTab(new URLSearchParams(search).get('tab')) : null
}

// Order follows the visible top-level navigation; null denotes an unrelated page.
export function navigationIndex(pathname: string, search: string, bugOnly: boolean): number | null {
  const testingTab = testingTabForLocation(pathname, search)
  if (bugOnly) return testingTab === 'bugs' ? 3 : null
  if (pathname.startsWith('/requirements')) return 1
  if (pathname.startsWith('/projects')) return new URLSearchParams(search).get('board') === 'requirements' ? 1 : 0
  if (testingTab === 'bugs') return 3
  if (testingTab) return 2
  if (pathname.startsWith('/base-services')) return 4
  return null
}
