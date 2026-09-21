import {
  getExecutionStatusMeta
} from '@/features/ui-automation/utils/runHelpers'
import {
  formatOptionalValue
} from '@/features/ui-automation/utils/uiTestCaseEditor'
import {
  type UiTestCaseRunStepResult
} from '@/services/api'
import {
  formatTime
} from '@/utils/format'
import { Empty, Image, Tag } from 'antd'

export function renderUiRunStepResult(stepResult: UiTestCaseRunStepResult, index: number) {
  const stepStatus = getExecutionStatusMeta(stepResult.status)

  return (
    <div key={`${stepResult.orderNo ?? index}-${stepResult.stepName ?? index}`} className={`api-case-run-result-row${stepResult.success === false ? ' failed' : ''}`}>
      <div className="api-case-run-result-row-title">
        <strong>{stepResult.stepName?.trim() || `步骤 ${stepResult.orderNo ?? index + 1}`}</strong>
        <Tag color={stepStatus.color}>{stepStatus.label}</Tag>
        {typeof stepResult.success === 'boolean' ? (
          <Tag color={stepResult.success ? 'success' : 'error'}>{stepResult.success ? '通过' : '失败'}</Tag>
        ) : null}
      </div>
      <div className="api-case-run-result-row-meta">
        <span className="api-case-run-result-meta-item">
          <strong>顺序</strong>
          <span>{formatOptionalValue(stepResult.orderNo)}</span>
        </span>
        <span className="api-case-run-result-meta-item">
          <strong>关键字</strong>
          <span>{formatOptionalValue(stepResult.keyword)}</span>
        </span>
        <span className="api-case-run-result-meta-item">
          <strong>开始</strong>
          <span>{formatTime(stepResult.startedAt)}</span>
        </span>
        <span className="api-case-run-result-meta-item">
          <strong>结束</strong>
          <span>{formatTime(stepResult.finishedAt)}</span>
        </span>
        <span className="api-case-run-result-meta-item">
          <strong>耗时</strong>
          <span>{formatOptionalValue(stepResult.durationMs ? `${stepResult.durationMs} ms` : stepResult.durationMs)}</span>
        </span>
        <span className="api-case-run-result-meta-item">
          <strong>实际值</strong>
          <span>{formatOptionalValue(stepResult.actualValue)}</span>
        </span>
      </div>
      {stepResult.screenshotPath ? (
        <div className="ui-test-run-step-screenshot">
          <strong>截图</strong>
          <Image
            src={stepResult.screenshotPath}
            alt={`${stepResult.stepName?.trim() || `步骤 ${stepResult.orderNo ?? index + 1}`}截图`}
            preview
          />
        </div>
      ) : null}
    </div>
  )
}

export function renderUiRunStepResultList(stepResults: UiTestCaseRunStepResult[], emptyDescription: string) {
  const orderedStepResults = [...stepResults].sort(
    (left, right) => (left.orderNo ?? Number.MAX_SAFE_INTEGER) - (right.orderNo ?? Number.MAX_SAFE_INTEGER),
  )

  if (orderedStepResults.length === 0) {
    return <Empty description={emptyDescription} image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  return <div className="api-case-run-result-list">{orderedStepResults.map(renderUiRunStepResult)}</div>
}
