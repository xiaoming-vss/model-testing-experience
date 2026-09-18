export type TestingTab = 'api' | 'ui' | 'functional' | 'library'

export function resolveTestingTab(tab?: string | null): TestingTab {
  if (tab === 'ui' || tab === 'functional' || tab === 'api' || tab === 'library') return tab
  return 'functional'
}
