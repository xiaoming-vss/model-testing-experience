import type { UiTestCaseRunStepResult } from '@/services/api'
import { Tooltip } from 'antd'

import { formatUiStepResultBadge, getUiRunTone } from '../utils/detailRunView'

/*
 * 步骤行上的运行结论徽标（PASS / FAIL / SKIP …）。数据来自最近一次调试运行里同一 orderNo 的步骤结果，
 * 所以徽标本身要能说清出处；没有结果的步骤由调用方决定显示什么（未设置关键字的显示「草稿」，
 * 其余什么都不显示，而不是编造一个结论）。
 */

export function UiStepResultBadge({ stepResult }: { stepResult: UiTestCaseRunStepResult }) {
  return (
    <Tooltip title="来自最近一次调试运行">
      <span className={`ui-wb-step-status tone-${getUiRunTone(stepResult.status)}`}>
        {formatUiStepResultBadge(stepResult.status, stepResult.success)}
        {typeof stepResult.durationMs === 'number' ? ` (${stepResult.durationMs}ms)` : ''}
      </span>
    </Tooltip>
  )
}
