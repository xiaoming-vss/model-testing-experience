import { FolderOpenOutlined, SlidersOutlined } from '@ant-design/icons'
import { Button, Tooltip } from 'antd'

/*
 * 步骤画布标题：返回测试集流程 + 当前用例路径，右侧是当前运行环境。
 * 用例的新建、切换、排序、删除都回到流程画布的卡片上操作，这里不再承载用例管理弹层。
 * 样式见 styles/detail-workbench-v2.css。
 */

type Props = {
  compact?: boolean
  caseSerial?: string
  caseName?: string
  runEnvText: string
  screenshotText: string
  onOverview: () => void
}

export function UiCaseControlRibbon({ compact, caseSerial, caseName, runEnvText, screenshotText, onOverview }: Props) {
  return (
    <div className={`ui-wb-ribbon${compact ? ' is-compact' : ''}`}>
      <div className="ui-wb-flow-breadcrumb">
        <Button type="text" size="small" icon={<FolderOpenOutlined />} onClick={onOverview}>测试集流程</Button>
        {caseName ? <span className="ui-wb-flow-breadcrumb-current"> / {caseSerial ? `${caseSerial} ` : ''}{caseName} / 步骤流程</span> : null}
      </div>

      {compact ? <Tooltip title={`运行环境：${runEnvText} · 截图策略：${screenshotText}`}>
        <Button type="text" size="small" icon={<SlidersOutlined />} aria-label="查看运行环境" />
      </Tooltip> : <div className="ui-wb-ribbon-workspace">
        <Tooltip title={`截图策略：${screenshotText}`}>
          <span className="ui-wb-ribbon-env">
            <SlidersOutlined aria-hidden="true" />
            运行环境：{runEnvText}
          </span>
        </Tooltip>
      </div>}
    </div>
  )
}
