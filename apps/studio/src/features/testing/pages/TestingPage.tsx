import { useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { ApiAutomationPage } from '@/features/api-automation/pages/ApiAutomationPage'
import { BugListPage } from '@/features/bugs/pages/BugListPage'
import { PerformancePage } from '@/features/performance/pages/PerformancePage'
import { TestOrderPage } from '@/features/test-orders/pages/TestOrderPage'
import {
  isLegacyLibraryTab,
  resolveTestingTab,
  type TestingTab,
} from '@/features/testing/components/testingTab'
import { UiAutomationPage } from '@/features/ui-automation/pages/UiAutomationPage'
import { PaneActivityProvider } from '@/shared/ui/PaneActivityProvider'

const TESTING_TAB_PAGES = [
  { key: 'api', Page: ApiAutomationPage },
  { key: 'ui', Page: UiAutomationPage },
  { key: 'perf', Page: PerformancePage },
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
      <div className="testing-tab-panel flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden max-[680.01px]:overflow-visible">
        {TESTING_TAB_PAGES.map(({ key, Page }) => {
          if (!visitedTabs.has(key)) return null
          return (
            <div key={key} className={`testing-tab-pane min-h-0 min-w-0 flex-1 flex-col [&>.workbench-page]:min-h-0 [&>.workbench-page]:flex-1 [&>.workbench-page]:p-0 [&>.api-automation-page]:h-full [&>.api-automation-page]:min-h-0 [&>.api-automation-page]:overflow-hidden ${activeTab === key ? 'flex' : 'hidden'}`} id={`testing-panel-${key}`} hidden={activeTab !== key}>
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
