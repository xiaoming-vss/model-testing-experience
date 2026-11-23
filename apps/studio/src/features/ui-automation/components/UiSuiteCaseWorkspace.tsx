import { Form } from 'antd'
import { CaseInvalidationModal } from '@/shared/components/CaseInvalidationModal'
import { message } from '@/shared/utils/feedback'
import { buildUiTestCaseUpdatePayload } from '@/utils/updatePayload'
import { normalizeUiTestCaseId } from '@/utils/format'
import { formatViewportText } from '../utils/uiTestCaseEditor'
import { serializeSteps, type UiTestCaseFormValues } from '../utils/uiTestCaseEditor'
import { UiRunInspector } from './UiRunInspector'
import { UiSuiteCaseAlerts } from './UiSuiteCaseAlerts'
import { UiSuiteCaseFlowPanel } from './UiSuiteCaseFlowPanel'
import { UiSuiteCaseToolbar } from './UiSuiteCaseToolbar'
import type { UiTestSuiteCasePageModel } from '../hooks/useUiTestSuiteCasePage'

export function UiSuiteCaseWorkspace({ page }: { page: UiTestSuiteCasePageModel }) {
  const {
    caseForm,
    setCaseDirty,
    isCreatingCase,
    setDraftCaseValues,
    setFlowLevel,
    setStepConfigTab,
    setSelectedStepIndex,
    setExpandedStepIndexes,
    getCompleteCaseFormValues,
    createCaseMutation,
    editingCase,
    activeCaseId,
    updateCaseMutation,
    showEditorForm,
    flowLevel,
    currentRun,
    can,
    suiteQuery,
    screenshotText,
    uiTestCaseRunQuery,
    handleRefreshUiRunDetail,
    setStepConfigHost,
    caseStatusOpen,
    setCaseStatusOpen,
    batchInvalidateCasesMutation,
    uiTestCases,
  } = page

  return <>
    <UiSuiteCaseAlerts page={page} />
    <Form<UiTestCaseFormValues>
      form={caseForm}
      layout="vertical"
      requiredMark={false}
      className="ui-suite-detail-form flex-auto flex min-h-0 flex-col gap-3"
      onValuesChange={(_changedValues, allValues) => {
        setCaseDirty(true)
        if (isCreatingCase) {
          setDraftCaseValues(allValues as UiTestCaseFormValues)
        }
      }}
      onFinishFailed={({ errorFields }) => {
        setFlowLevel('steps')
        const path = errorFields.find((field) => field.name[0] === 'steps' && typeof field.name[1] === 'number')?.name
        if (path && typeof path[1] === 'number') {
          setStepConfigTab(path.includes('saveTo') ? 'extract' : 'basic')
          setSelectedStepIndex(path[1])
          setExpandedStepIndexes([path[1]])
        }
      }}
      onFinish={(values) => {
        const completeValues = {
          ...getCompleteCaseFormValues(),
          ...values,
          steps: getCompleteCaseFormValues().steps,
        } satisfies UiTestCaseFormValues

        if (isCreatingCase) {
          createCaseMutation.mutate(completeValues)
          return
        }

        if (!editingCase || normalizeUiTestCaseId(editingCase) !== activeCaseId) {
          message.warning('用例详情加载中，请稍后再试')
          return
        }

        const payload = buildUiTestCaseUpdatePayload(editingCase, {
          name: completeValues.name,
          enabled: completeValues.enabled,
          orderNo: editingCase.orderNo,
          stepsJson: serializeSteps(completeValues.steps),
        })

        if (Object.keys(payload).length === 0) {
          setCaseDirty(false)
          message.info('当前没有需要保存的修改')
          return
        }

        updateCaseMutation.mutate(completeValues)
      }}
    >
      <UiSuiteCaseToolbar page={page} />

      <div className="ui-wb-cols grid min-h-[min(520px,calc(100vh-320px))] flex-auto grid-cols-[minmax(0,7fr)_minmax(0,5fr)] items-stretch gap-3 min-[1100px]:grid-cols-[minmax(0,7fr)_minmax(0,3fr)] max-[1180.01px]:min-h-0 max-[1180.01px]:flex-none max-[1180.01px]:grid-cols-1 max-[1180.01px]:grid-rows-[auto_auto]">
        <UiSuiteCaseFlowPanel page={page} />
        <UiRunInspector
          showStepConfig={flowLevel === 'steps' && showEditorForm}
          stepConfigHostRef={setStepConfigHost}
          canStop={can('execute')}
          run={currentRun}
          viewportText={formatViewportText(suiteQuery.data?.viewportWidth, suiteQuery.data?.viewportHeight)}
          viewportWidth={suiteQuery.data?.viewportWidth}
          viewportHeight={suiteQuery.data?.viewportHeight}
          screenshotText={screenshotText}
          refreshing={uiTestCaseRunQuery.isFetching}
          onRefreshRun={handleRefreshUiRunDetail}
        />
      </div>
    </Form>
    <CaseInvalidationModal
      open={caseStatusOpen}
      scopeLabel={`${suiteQuery.data?.name ?? '当前 UI 测试集'} · ${uiTestCases.length} 条用例`}
      cases={uiTestCases.map((item) => ({
        id: normalizeUiTestCaseId(item),
        name: item.name,
        invalidatedAt: item.invalidatedAt,
      }))}
      canWrite={can('write')}
      pending={batchInvalidateCasesMutation.isPending}
      onClose={() => setCaseStatusOpen(false)}
      onSubmit={(caseIds, invalidated) =>
        batchInvalidateCasesMutation.mutate({ caseIds, invalidated })
      }
    />
  </>
}
