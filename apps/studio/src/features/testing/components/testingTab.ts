export type TestingTab = 'orders' | 'bugs' | 'api' | 'ui'

/** 顶部「测试」入口展开的页签；Bug 列表是独立一级入口，不在这组页签内。 */
export const TESTING_TAB_OPTIONS = [
  { key: 'orders', label: '测试单' },
  { key: 'api', label: 'API测试' },
  { key: 'ui', label: 'UI测试' },
] as const satisfies readonly { key: Exclude<TestingTab, 'bugs'>; label: string }[]

export type TestingWorkspaceTab = (typeof TESTING_TAB_OPTIONS)[number]['key']

export function resolveTestingTab(tab?: string | null): TestingTab {
  if (tab === 'orders' || tab === 'bugs' || tab === 'ui' || tab === 'api') return tab
  return 'orders'
}

/** 旧用例库入口已迁到资产库，由路由层统一跳转。 */
export function isLegacyLibraryTab(tab?: string | null) {
  return tab === 'library' || tab === 'functional'
}
