import { useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { ApiAutomationPage } from '@/features/api-automation/pages/ApiAutomationPage'
import { BugListPage } from '@/features/bugs/pages/BugListPage'
import { TestOrderPage } from '@/features/test-orders/pages/TestOrderPage'
import {
  isLegacyLibraryTab,
  resolveTestingTab,
  type TestingTab,
} from '@/features/testing/components/testingTab'
import { UiAutomationPage } from '@/features/ui-automation/pages/UiAutomationPage'
import { PaneActivityProvider } from '@/shared/ui/PaneActivityProvider'
import '@/features/testing/styles/index.css'

const TESTING_TAB_PAGES = [
  { key: 'api', Page: ApiAutomationPage },
  { key: 'ui', Page: UiAutomationPage },
  { key: 'orders', Page: TestOrderPage },
  { key: 'bugs', Page: BugListPage },
] as const

export function TestingPage() {
  const [searchParams] = useSearchParams()
  const rawTab = searchParams.get('tab')
  const activeTab = resolveTestingTab(rawTab)
  // 访问过的标签页保持挂载、用 hidden 切换显示：卸载重挂会让每次切标签
  // 都重渲染全量数据并重发全部请求，是用例库切换卡顿的根源。
  const [visitedTabs, setVisitedTabs] = useState(() => new Set<TestingTab>([activeTab]))
  useEffect(() => {
    setVisitedTabs(previous => {
      if (previous.has(activeTab)) return previous
      const next = new Set(previous)
      next.add(activeTab)
      return next
    })
  }, [activeTab])

  if (isLegacyLibraryTab(rawTab)) {
    return <Navigate to="/asset-library?tab=cases" replace />
  }

  return (
    <div className="workbench-page testing-page">
      <div className="testing-tab-panel">
        {TESTING_TAB_PAGES.map(({ key, Page }) => {
          if (!visitedTabs.has(key)) return null
          return (
            <div key={key} className="testing-tab-pane" id={`testing-panel-${key}`} hidden={activeTab !== key}>
              <PaneActivityProvider active={activeTab === key}>
                <Page />
              </PaneActivityProvider>
            </div>
          )
        })}
      </div>
    </div>
  )
}
