import { Alert, Button } from 'antd'
import { getRunPollingInterval } from '@/domain/runs/polling'
import { getErrorMessage } from '@/utils/format'
import type { UiTestSuiteCasePageModel } from '../hooks/useUiTestSuiteCasePage'

export function UiSuiteCaseAlerts({ page }: { page: UiTestSuiteCasePageModel }) {
  const {
    suiteQuery,
    casesQuery,
    selectedCaseDetailQuery,
    requirementQuery,
    sprintQuery,
    uiTestCaseRunQuery,
    currentRun,
    liveUiRunId,
    environmentsQuery,
    uiEnvironments,
    setEnvironmentDrawerOpen,
  } = page

  return <>
    {suiteQuery.error ? <Alert showIcon type="error" title={getErrorMessage(suiteQuery.error)} /> : null}
    {casesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(casesQuery.error)} /> : null}
    {selectedCaseDetailQuery.error ? <Alert showIcon type="error" title={getErrorMessage(selectedCaseDetailQuery.error)} /> : null}
    {requirementQuery.error ? <Alert showIcon type="error" title={getErrorMessage(requirementQuery.error)} /> : null}
    {sprintQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintQuery.error)} /> : null}
    {uiTestCaseRunQuery.error && !currentRun ? <Alert showIcon type="error" title={getErrorMessage(uiTestCaseRunQuery.error)} /> : null}
    {liveUiRunId && currentRun?.status && getRunPollingInterval(currentRun.status) === false ? (
      <Alert showIcon type="info" title="执行已结束，正在接收截图等临时产物" />
    ) : null}
    {environmentsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(environmentsQuery.error)} /> : null}
    {environmentsQuery.isSuccess && uiEnvironments.length === 0 ? (
      <Alert
        showIcon
        type="info"
        title="当前项目还没有 UI 测试环境，请先在“环境”中创建并选择环境后再运行。"
        action={
          <Button size="small" onClick={() => setEnvironmentDrawerOpen(true)}>
            去创建
          </Button>
        }
      />
    ) : null}
  </>
}
