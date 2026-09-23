import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import type { UiTestCase } from '@/services/api'
import { normalizeUiTestCaseId } from '@/utils/format'
import {
  FolderOpenOutlined,
  LeftOutlined,
  PlusOutlined,
  RightOutlined,
  SlidersOutlined,
  SwapOutlined
} from '@ant-design/icons'
import { Button, Popover, Select, Tooltip } from 'antd'
import type { ReactNode } from 'react'

import { formatUiCaseSerial } from '../utils/detailRunView'
import { getUiTestCaseStepCount } from '../utils/uiTestCaseEditor'

/*
 * 控制条：左侧选用例（下拉 + 前后切换 + 新建 + 用例顺序弹层），右侧当前运行环境。
 *
 * 设计稿这里是一个原生 select；换成 antd 的 Select 是为了保住搜索（用例多时下拉滚动不够用），
 * 并在同一行补上「新建用例」——设计稿把新建入口放在别处，但那条路径没有画出来，
 * 而用例列表已经收进下拉，新建必须有个显式入口。
 * 「运行环境」设计稿写的是 `Chrome 122 (Headless)`，浏览器版本在前端拿不到（见 STRUCTURE.md），
 * 所以展示的是测试集里真实存在的执行模式、视口与步骤超时。样式见 styles/detail-workbench-v2.css。
 */

type Props = {
  cases: UiTestCase[]
  selectedCaseId: string
  caseCount: number
  runEnvText: string
  screenshotText: string
  createDisabled: boolean
  /** 用例顺序弹层的内容，由页面装配（它持有拖拽重排所需的状态）。 */
  orderPopoverContent: ReactNode
  onSelectCase: (caseId: string) => void
  onPrevCase: () => void
  onNextCase: () => void
  onCreateCase: () => void
}

export function UiCaseControlRibbon({
  cases,
  selectedCaseId,
  caseCount,
  runEnvText,
  screenshotText,
  createDisabled,
  orderPopoverContent,
  onSelectCase,
  onPrevCase,
  onNextCase,
  onCreateCase,
}: Props) {
  const selectedIndex = cases.findIndex((item) => normalizeUiTestCaseId(item) === selectedCaseId)
  const caseOptions = cases.map((item, index) => {
    const caseId = normalizeUiTestCaseId(item)
    const serial = formatUiCaseSerial(item.orderNo ?? index + 1) || `#${index + 1}`

    return {
      value: caseId,
      label: `${serial} ${item.name}（${getUiTestCaseStepCount(item)} 步）`,
    }
  })

  return (
    <div className="ui-wb-ribbon">
      <div className="ui-wb-ribbon-case">
        <FolderOpenOutlined className="ui-wb-ribbon-case-icon" aria-hidden="true" />
        <span className="ui-wb-ribbon-case-label">选择用例</span>
        <Select
          className="ui-wb-ribbon-case-select"
          value={selectedCaseId || undefined}
          placeholder="请选择 UI测试用例"
          options={caseOptions}
          showSearch
          optionFilterProp="label"
          disabled={cases.length === 0}
          onChange={(value: string) => onSelectCase(value)}
        />
        <span className="ui-wb-ribbon-count">{caseCount} 个用例</span>
        <Tooltip title="前一个用例">
          <Button
            type="text"
            className="ui-wb-ribbon-step"
            icon={<LeftOutlined />}
            aria-label="前一个用例"
            disabled={selectedIndex <= 0}
            onClick={onPrevCase}
          />
        </Tooltip>
        <Tooltip title="后一个用例">
          <Button
            type="text"
            className="ui-wb-ribbon-step"
            icon={<RightOutlined />}
            aria-label="后一个用例"
            disabled={selectedIndex < 0 || selectedIndex >= cases.length - 1}
            onClick={onNextCase}
          />
        </Tooltip>
        <Popover trigger="click" placement="bottomLeft" overlayClassName="ui-wb-order-overlay" content={orderPopoverContent}>
          <Button type="text" className="ui-wb-ribbon-order" icon={<SwapOutlined />}>
            用例顺序
          </Button>
        </Popover>
        <ProjectActionButton
          action="write"
          type="text"
          className="ui-wb-ribbon-create action-btn-create"
          operation="create"
          icon={<PlusOutlined />}
          aria-label="新建 UI测试用例"
          disabled={createDisabled}
          onClick={onCreateCase}
        >
          新建用例
        </ProjectActionButton>
      </div>

      <div className="ui-wb-ribbon-workspace">
        <Tooltip title={`截图策略：${screenshotText}`}>
          <span className="ui-wb-ribbon-env">
            <SlidersOutlined aria-hidden="true" />
            运行环境：{runEnvText}
          </span>
        </Tooltip>
      </div>
    </div>
  )
}
