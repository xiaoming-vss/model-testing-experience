export type TestingTab = 'orders' | 'bugs' | 'api' | 'ui'

export function resolveTestingTab(tab?: string | null): TestingTab {
  if (tab === 'orders' || tab === 'bugs' || tab === 'ui' || tab === 'api') return tab
  return 'orders'
}

/** 旧用例库入口已迁到资产库，由路由层统一跳转。 */
export function isLegacyLibraryTab(tab?: string | null) {
  return tab === 'library' || tab === 'functional'
}
