import { Navigate, useSearchParams } from 'react-router-dom'
import { UnifiedAiTestingPage } from './UnifiedAiTestingPage'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-list-v2.css'

export function AiTestingOverviewPage() {
  const [searchParams] = useSearchParams()
  if (searchParams.get('tab') === 'skills') {
    return <Navigate to="/base-services?tab=skills" replace />
  }
  return (
    <div className="workbench-page ai-testing-page tp-list-surface ai-testing-overview-page tp-surface">
      <UnifiedAiTestingPage embedded />
    </div>
  )
}
