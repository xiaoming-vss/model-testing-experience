import { Alert, Empty, Spin } from 'antd'
import { ProjectAccessScope } from '@/domain/projects/components/ProjectAccessScope'
import { getErrorMessage } from '@/utils/format'
import { workbenchTabsCompactClass } from '@/shared/utils/surfaceClasses'
import { TestReportHistoryDrawer } from '../components/TestReportHistoryDrawer'
import { SprintOverviewView } from '../components/SprintOverviewView'
import { TestReportGenerateDrawer } from '../components/SprintReportGenerateDrawer'
import { TestReportMarkdownModal } from '../components/SprintReportMarkdownModal'
import { useSprintDetailPage } from '../hooks/useSprintDetailPage'
import sprintOverviewStyles from '../styles/sprint-overview.module.css'

export function SprintDetailPage() {
  const page = useSprintDetailPage()
  const {
    sprintQuery,
    projectId,
    projectScopeError,
    sprintId,
    todayDate,
    reportDrawerOpen,
    reportHistoryOpen,
    setReportHistoryOpen,
    reportModalRunId,
    reportForm,
    reportRunDetailQuery,
    createReportRunMutation,
    downloadReportPdfMutation,
    closeReportDrawer,
    handleCreateReportRun,
    handleViewReport,
    closeReportModal,
    handleDownloadReportPdf,
  } = page

  return (<ProjectAccessScope projectId={projectId} resourceError={projectScopeError}>{(
    <div className={`workbench-page sprint-overview-page tp-surface overflow-hidden p-[var(--app-page-gutter)] ${sprintOverviewStyles.root}`}>
      {sprintQuery.isLoading ? (
        <div className={`workbench-tabs ${workbenchTabsCompactClass}`}>
          <section className="workbench-panel workbench-panel-flat sprint-overview-panel sprint-overview-panel-unified sprint-overview-state-panel overflow-hidden">
            <Spin />
          </section>
        </div>
      ) : sprintQuery.data ? (
        <SprintOverviewView page={page} />
      ) : (
        <div className={`workbench-tabs ${workbenchTabsCompactClass}`}>
          {sprintQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintQuery.error)} /> : null}
          <section className="workbench-panel workbench-panel-flat sprint-overview-panel sprint-overview-panel-unified sprint-overview-state-panel overflow-hidden">
            <Empty description="未找到迭代信息" />
          </section>
        </div>
      )}
      <TestReportGenerateDrawer
        open={reportDrawerOpen}
        projectId={projectId}
        form={reportForm}
        snapshotDate={todayDate}
        loading={createReportRunMutation.isPending}
        error={createReportRunMutation.error}
        onClose={closeReportDrawer}
        onFinish={handleCreateReportRun}
      />
      <TestReportHistoryDrawer key={`${projectId}:${sprintId}`} open={reportHistoryOpen} projectId={projectId} sprintId={sprintId}
        onClose={() => setReportHistoryOpen(false)} onView={run => { setReportHistoryOpen(false); handleViewReport(run) }} />
      <TestReportMarkdownModal
        open={Boolean(reportModalRunId)}
        run={reportRunDetailQuery.data}
        loading={reportRunDetailQuery.isLoading}
        error={reportRunDetailQuery.error ?? downloadReportPdfMutation.error}
        downloading={downloadReportPdfMutation.isPending}
        onClose={closeReportModal}
        onDownloadPdf={handleDownloadReportPdf}
      />
    </div>
  )}</ProjectAccessScope>)
}
