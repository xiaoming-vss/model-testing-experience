import { useSearchParams } from 'react-router-dom'
import { ApiAutomationPage } from '@/features/api-automation/pages/ApiAutomationPage'
import { CaseLibraryPage } from '@/features/test-cases/pages/CaseLibraryPage'
import { TestOrderPage } from '@/features/test-orders/pages/TestOrderPage'
import { resolveTestingTab } from '@/features/testing/components/testingTab'
import { UiAutomationPage } from '@/features/ui-automation/pages/UiAutomationPage'
import '@/features/testing/styles/index.css'

export function TestingPage() {
  const [searchParams] = useSearchParams()
  const activeTab = resolveTestingTab(searchParams.get('tab'))

  return (
    <div className="workbench-page testing-page">
      <div className="testing-tab-panel">
        {activeTab === 'api' ? <ApiAutomationPage /> : null}
        {activeTab === 'ui' ? <UiAutomationPage /> : null}
        {activeTab === 'library' ? <CaseLibraryPage /> : null}
        {activeTab === 'orders' ? <TestOrderPage /> : null}
      </div>
    </div>
  )
}
