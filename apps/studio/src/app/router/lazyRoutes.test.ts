import { describe, expect, it } from 'vitest'
import appShellSource from '../layouts/AppShell.tsx?raw'
import assetLibrarySource from '../pages/AssetLibraryPage.tsx?raw'
import testingPageSource from '../pages/TestingPage.tsx?raw'
import routesSource from './routes.tsx?raw'

describe('route-level lazy loading', () => {
  it.each([
    'AppShell',
    'AuthPage',
    'TestOrderGraphPage',
  ])('lazy-loads %s from the root route table', (page) => {
    expect(routesSource).toContain(`const ${page} = lazy(() => import(`)
  })

  it.each([
    'ProjectsPage',
    'TestingPage',
    'BaseServicesPage',
    'BugDetailPage',
    'PerformanceSuiteDetailPage',
    'PerformanceRunDetailPage',
    'PerformanceCaseRunDetailPage',
  ])('lazy-loads the %s route', (page) => {
    expect(appShellSource).toContain(`const ${page} = lazy(() => import(`)
  })

  it('lazy-loads testing and asset-library tabs instead of importing them eagerly', () => {
    for (const page of ['ApiAutomationPage', 'PerformancePage', 'BugListPage', 'UiAutomationPage']) {
      expect(testingPageSource).toContain(`const ${page} = lazy(() => import(`)
    }
    for (const page of ['CaseLibraryPage', 'InterfaceLibraryPage', 'SoftwareRepositoriesPage']) {
      expect(assetLibrarySource).toContain(`const ${page} = lazy(() => import(`)
    }
  })
})
