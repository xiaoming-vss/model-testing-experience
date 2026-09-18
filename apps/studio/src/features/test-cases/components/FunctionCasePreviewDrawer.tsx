import { Button, Drawer, Space, Tag, Tooltip, Typography } from 'antd'
import type { FunctionCaseLibraryItem } from '../types'
import { priorityColor } from '../utils/casePriority'

const { Text } = Typography

type Props = {
  open: boolean
  item?: FunctionCaseLibraryItem | null
  onClose: () => void
  onOpenSuite: (suiteId: string) => void
}

export function FunctionCasePreviewDrawer({ open, item, onClose, onOpenSuite }: Props) {
  const preconditions = item?.content?.preconditions ?? []
  const steps = item?.content?.steps ?? []
  const scopeText = [item?.sprintName, item?.requirementName, item?.suiteName].filter(Boolean).join(' / ')
  const suiteId = item?.suiteId

  return (
    <Drawer
      title="用例详情"
      open={open}
      onClose={onClose}
      size={520}
      extra={
        <Space size={8}>
          <Tooltip title="测试单功能尚未开放">
            <span>
              <Button disabled>加入测试单</Button>
            </span>
          </Tooltip>
          <Button disabled={!suiteId} onClick={() => suiteId && onOpenSuite(suiteId)}>
            在所属测试集中打开
          </Button>
        </Space>
      }
    >
      <div className="case-library-preview">
        <Space orientation="vertical" size={8}>
          <Text strong className="case-library-preview-title">
            {item?.title || '-'}
          </Text>
          <Space size={6} wrap>
            {item?.priority ? <Tag color={priorityColor(item.priority)}>{item.priority}</Tag> : null}
            {item?.caseType ? <Tag color="geekblue">{item.caseType}</Tag> : null}
            {item?.module ? <Tag>{item.module}</Tag> : null}
          </Space>
        </Space>

        <div className="case-library-preview-section">
          <Text type="secondary">所属</Text>
          <Text>{scopeText || '-'}</Text>
        </div>

        <div className="case-library-preview-section">
          <Text type="secondary">前置条件</Text>
          {preconditions.length === 0 ? (
            <Text type="secondary">暂无前置条件</Text>
          ) : (
            <ol className="case-library-preview-list">
              {preconditions.map((entry, index) => (
                <li key={index}>{entry}</li>
              ))}
            </ol>
          )}
        </div>

        <div className="case-library-preview-section">
          <Text type="secondary">步骤与预期</Text>
          {steps.length === 0 ? (
            <Text type="secondary">暂无步骤</Text>
          ) : (
            <ol className="case-library-preview-list">
              {steps.map((step, index) => (
                <li key={index}>
                  <div>{step.action}</div>
                  <div className="case-library-preview-expected">预期：{step.expected}</div>
                </li>
              ))}
            </ol>
          )}
        </div>

        <Text type="secondary" className="case-library-preview-note">
          用例库不提供编辑，编辑在所属测试集中进行。
        </Text>
      </div>
    </Drawer>
  )
}
