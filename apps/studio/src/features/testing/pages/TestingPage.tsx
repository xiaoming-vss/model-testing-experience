import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiAutomationPage } from '@/features/api-automation/pages/ApiAutomationPage'
import { TestCasePage } from '@/features/test-cases/pages/TestCasePage'
import { TestingTabSwitcher } from '@/features/testing/components/TestingTabSwitcher'
import { resolveTestingTab, type TestingTab } from '@/features/testing/components/testingTab'
import { UiAutomationPage } from '@/features/ui-automation/pages/UiAutomationPage'
import '@/features/testing/styles/index.css'

export function TestingPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const activeTab = useMemo<TestingTab>(() => resolveTestingTab(searchParams.get('tab')), [searchParams])

  function handleTabChange(nextTab: TestingTab) {
    const nextSearchParams = new URLSearchParams(searchParams)
    nextSearchParams.set('tab', nextTab)
    setSearchParams(nextSearchParams, { replace: true })
  }

  return (
    <div className="workbench-page testing-page">
      <section className="workbench-project-toolbar testing-toolbar">
        <TestingTabSwitcher activeTab={activeTab} onChange={handleTabChange} />
      </section>

      <div className="testing-tab-panel">
        {activeTab === 'api' ? <ApiAutomationPage /> : null}
        {activeTab === 'ui' ? <UiAutomationPage /> : null}
        {activeTab === 'functional' ? <TestCasePage /> : null}
      </div>
    </div>
  )
}
