import { ListEmptyState } from '@/shared/components/ListEmptyState'
import { CasePushModal } from '../components/CasePushModal'
import { CaseEditorModal } from '../components/CaseEditorModal'
import { CaseLibraryCaseList } from '../components/CaseLibraryCaseList'
import { CaseLibrarySidebar } from '../components/CaseLibrarySidebar'
import { CaseLibraryToolbar } from '../components/CaseLibraryToolbar'
import { FunctionCaseImportModal } from '../components/FunctionCaseImportModal'
import { SuiteDrawer } from '../components/SuiteDrawer'
import { useCaseLibraryPage } from '../hooks/useCaseLibraryPage'
import caseLibraryStyles from '../styles/case-library.module.css'

/**
 * 用例库：左栏测试集（首项「全部用例」），右栏用例列表。
 * 点某一行在抽屉里查看用例，编辑、新建、导入也都在本页完成。
 */
export function CaseLibraryPage() {
  const page = useCaseLibraryPage()
  const { activeProjectId, sprints, sprintsQuery, zentaoImportTarget, setZentaoImportTarget } = page

  return (
    <div className={`workbench-page api-automation-page functional-test-page tp-list-surface case-library-page tp-surface h-full ${caseLibraryStyles.root}`}>
      <div className="api-automation-content h-full">
        <section className="workbench-panel workbench-panel-flat workbench-board-panel tp-board">
          <CaseLibraryToolbar page={page} />

          {!activeProjectId ? (
            <ListEmptyState description="请先选择项目" />
          ) : sprintsQuery.error && sprints.length === 0 ? null : !sprintsQuery.isLoading && sprints.length === 0 ? (
            <ListEmptyState description="当前项目下暂无迭代" />
          ) : (
            <div className="case-library-layout grid min-h-0 flex-1 grid-cols-[var(--app-sidebar-width)_minmax(0,1fr)] gap-4 overflow-hidden max-[1180.01px]:grid-cols-1">
              <CaseLibrarySidebar page={page} />
              <CaseLibraryCaseList page={page} />
            </div>
          )}
        </section>
      </div>

      <CaseEditorModal page={page} />
      <SuiteDrawer page={page} />
      <FunctionCaseImportModal page={page} />

      {zentaoImportTarget && activeProjectId && <CasePushModal
        key={`${activeProjectId}:${zentaoImportTarget.suiteId}`}
        projectId={activeProjectId}
        suiteId={zentaoImportTarget.suiteId}
        caseIds={zentaoImportTarget.caseIds}
        count={zentaoImportTarget.caseIds.length || zentaoImportTarget.suiteCaseCount}
        onClose={() => setZentaoImportTarget(null)}
      />}
    </div>
  )
}
