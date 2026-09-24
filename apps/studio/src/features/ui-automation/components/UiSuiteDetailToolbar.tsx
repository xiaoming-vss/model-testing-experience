import { ActionButton } from '@/shared/components/ActionButton'
import {
  ArrowLeftOutlined,
  BugOutlined,
  HistoryOutlined,
  SaveOutlined
} from '@ant-design/icons'
import { Button, Tooltip } from 'antd'

import type { UiSuiteReadiness } from '../utils/detailRunView'

/*
 * UI测试集详情页顶栏：返回 / 标题 + 测试集 / 需求 / 迭代 / 就绪结论 / 上次运行 + 四个动作。
 *
 * 设计稿的「单步调试 (F10)」是逐步单步执行，平台没有这个模式，这里保留同位置的「调试运行」
 * （对当前用例发起一次真实调试运行）。样式见 styles/detail-workbench-v2.css。
 */

type Props = {
  suiteName: string
  requirementName: string
  sprintName: string
  readiness: UiSuiteReadiness
  /** 最近一次运行距今多久，没有运行记录时为空。 */
  lastRunText: string
  runHistoryCount: number
  runningSuite: boolean
  debugging: boolean
  saving: boolean
  canRun: boolean
  canDebug: boolean
  canSave: boolean
  onBack: () => void
  onOpenRunHistory: () => void
  onDebugRun: () => void
  onRunSuite: () => void
  onSave: () => void
}

export function UiSuiteDetailToolbar({
  suiteName,
  requirementName,
  sprintName,
  readiness,
  lastRunText,
  runHistoryCount,
  runningSuite,
  debugging,
  saving,
  canRun,
  canDebug,
  canSave,
  onBack,
  onOpenRunHistory,
  onDebugRun,
  onRunSuite,
  onSave,
}: Props) {
  return (
    <div className="ui-wb-toolbar">
      <div className="ui-wb-toolbar-main">
        <Button
          type="text"
          className="ui-wb-toolbar-back"
          icon={<ArrowLeftOutlined />}
          aria-label="返回UI测试集列表"
          title="返回UI测试集列表"
          onClick={onBack}
        />
        <h1 className="ui-wb-toolbar-title">
          <span className="ui-wb-toolbar-name">UI测试集详情</span>
          <span className="ui-wb-toolbar-sep" aria-hidden="true">/</span>
          <span className="ui-wb-toolbar-suite" title={suiteName}>
            {suiteName}
          </span>
          <span className="ui-wb-toolbar-path" title={`${requirementName} / ${sprintName}`}>
            / {requirementName} / {sprintName}
          </span>
        </h1>

        <Tooltip title={readiness.hint}>
          <span className={`ui-wb-readiness tone-${readiness.tone}`}>
            <span className="ui-wb-readiness-dot" aria-hidden="true" />
            {readiness.label}
          </span>
        </Tooltip>

        <span className="ui-wb-toolbar-last-run">
          {lastRunText ? `上次运行 ${lastRunText}` : '还没有运行记录'}
        </span>
      </div>

      <div className="ui-wb-toolbar-actions">
        <Button className="ui-wb-toolbar-history" icon={<HistoryOutlined />} onClick={onOpenRunHistory}>
          运行记录{runHistoryCount > 0 ? ` (${runHistoryCount})` : ''}
        </Button>
        <Button
          className="ui-wb-toolbar-debug"
          icon={<BugOutlined />}
          loading={debugging}
          disabled={!canDebug}
          onClick={onDebugRun}
        >
          调试运行
        </Button>
        <ActionButton
          type="primary"
          className="ui-wb-toolbar-run"
          operation="run"
          loading={runningSuite}
          disabled={!canRun}
          onClick={onRunSuite}
        >
          运行测试集
        </ActionButton>
        <Button className="ui-wb-toolbar-save" icon={<SaveOutlined />} loading={saving} disabled={!canSave} onClick={onSave}>
          保存
        </Button>
      </div>
    </div>
  )
}
