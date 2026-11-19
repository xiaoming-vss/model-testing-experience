import { Text } from '@/features/ui-automation/utils/detailView'
import { ProjectAccessScope } from '@/domain/projects/components/ProjectAccessScope'
import { UiSuiteCaseOverlays } from '@/features/ui-automation/components/UiSuiteCaseOverlays'
import { UiSuiteCaseWorkspace } from '@/features/ui-automation/components/UiSuiteCaseWorkspace'
import { useUiTestSuiteCasePage } from '@/features/ui-automation/hooks/useUiTestSuiteCasePage'
import '@/shared/styles/surface-tokens.css'
import suiteStyles from '@/features/ui-automation/styles/ui-suite.module.css'
import shellStyles from '@/features/ui-automation/styles/ui-detail-shell.module.css'

export function UiTestSuiteCasePage() {
  const page = useUiTestSuiteCasePage()
  const { sprintQuery, suiteQuery } = page

  return <ProjectAccessScope projectId={sprintQuery.data?.projectId ?? sprintQuery.data?.project_id ?? ''}>
    <div className={`workbench-page api-automation-page functional-test-page tp-list-surface ui-test-page ui-suite-detail-page tp-surface ${suiteStyles.scope} ${shellStyles.scope}`}>
      <div className="api-automation-content">
        <section className="workbench-panel workbench-panel-flat workbench-board-panel tp-board ui-suite-detail-board">
          <UiSuiteCaseWorkspace page={page} />
          {suiteQuery.data?.description ? <Text className="ui-wb-board-note">{suiteQuery.data.description}</Text> : null}
        </section>
      </div>
      <UiSuiteCaseOverlays page={page} />
    </div>
  </ProjectAccessScope>
}
