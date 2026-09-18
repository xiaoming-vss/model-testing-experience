export type TestingTab = 'api' | 'ui' | 'functional'

export function resolveTestingTab(tab?: string | null): TestingTab {
  if (tab === 'ui' || tab === 'functional' || tab === 'api') return tab
  return 'functional'
}
