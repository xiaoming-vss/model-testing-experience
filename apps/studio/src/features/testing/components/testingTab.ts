export type TestingTab = 'library' | 'orders' | 'api' | 'ui'

export function resolveTestingTab(tab?: string | null): TestingTab {
  // 旧的 ?tab=functional 继续可用：功能测试已并入用例库。
  if (tab === 'functional' || tab === 'library') return 'library'
  if (tab === 'orders' || tab === 'ui' || tab === 'api') return tab
  return 'library'
}
