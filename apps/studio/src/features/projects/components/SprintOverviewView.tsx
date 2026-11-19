import { SprintHealthSummary, TestExecutionOverviewCard, BugRiskOverviewCard } from './SprintDashboardCards'
import { SprintOverviewToolbar } from './SprintOverviewToolbar'
import { SprintTrendPanel } from './SprintTrendPanel'
import { workbenchTabsCompactClass } from '@/shared/utils/surfaceClasses'
import type { SprintDetailPageModel } from '../hooks/useSprintDetailPage'

export function SprintOverviewView({ page }: { page: SprintDetailPageModel }) {
  return (
    <section className="tp-board tp-list-panel sprint-overview-frame min-h-0 [&>.workbench-tabs]:p-0">
      <SprintOverviewToolbar page={page} />

      <div className={`workbench-tabs ${workbenchTabsCompactClass}`}>
        <section className="workbench-panel workbench-panel-flat sprint-overview-panel sprint-overview-panel-unified overflow-hidden">
          <div className="sprint-overview-panel-body flex min-h-0 flex-1 flex-col overflow-auto p-4">
            <div className="sprint-overview-layout grid min-h-0 grid-rows-[auto] content-start gap-4 max-[1200.01px]:flex max-[1200.01px]:flex-col min-[1281px]:min-h-0 min-[1281px]:flex-auto min-[1281px]:grid-rows-[auto_minmax(260px,1fr)_minmax(0,1.18fr)] min-[1281px]:content-stretch">
              <SprintHealthSummary metrics={page.latestMetrics} />

              <div className="sprint-dashboard-main-grid grid grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] gap-4 max-[1280.01px]:grid-cols-1">
                <TestExecutionOverviewCard metrics={page.latestMetrics} />
                <BugRiskOverviewCard bug={page.latestMetrics.bug} />
              </div>

              <SprintTrendPanel page={page} />
            </div>
          </div>
        </section>
      </div>
    </section>
  )
}
