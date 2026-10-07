import { CopyOutlined } from '@ant-design/icons'
import { Button, Tooltip, Typography } from 'antd'
import { priorityTone } from '@/shared/utils/priorityTone'
import { message } from '@/shared/utils/feedback'
import { formatTime } from '@/utils/format'
import type { TestOrderEntry } from '../types'
import { getTestOrderEntryStatusMeta, getTestOrderEntryStatusTone } from '../utils/testOrderStatus'

const { Text } = Typography

type Props = {
  entry: TestOrderEntry
  assigneeName: string
  executorName: string
  lockedByAssignee: boolean
}

export function TestOrderCaseSummary({ entry, assigneeName, executorName, lockedByAssignee }: Props) {
  const entryStatusMeta = getTestOrderEntryStatusMeta(entry.status)
  return (
    <div className="test-order-case-summary">
      <div className="test-order-editor-head">
        <Tooltip title={entry.caseId}>
          <Button
            size="small"
            icon={<CopyOutlined aria-hidden="true" />}
            iconPlacement="end"
            className="test-order-case-no"
            aria-label="复制用例 ID"
            disabled={!entry.caseId}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(entry.caseId ?? '')
                message.success('用例 ID 已复制')
              } catch {
                message.error('复制失败，请重试')
              }
            }}
          >
            <span>{entry.caseId}</span>
          </Button>
        </Tooltip>
        <Text strong className="test-order-case-title">
          {entry.caseTitle || entry.caseId}
        </Text>
        {lockedByAssignee ? (
          <Text type="secondary">该条已分配给其他执行人</Text>
        ) : null}
      </div>
      <div className="test-order-execution-meta">
        <span
          className={`test-order-meta-pill tone-${getTestOrderEntryStatusTone(entry.status)}`}
        >
          状态 <strong className="tp-tone-tag">{entryStatusMeta.label}</strong>
        </span>
        {entry.casePriority ? (
          <span className={`test-order-meta-pill tone-${priorityTone(entry.casePriority)}`}>
            优先级 <strong className="tp-tone-tag">{entry.casePriority}</strong>
          </span>
        ) : null}
        <span className="test-order-meta-pill">
          分配给 <strong className="tp-tone-tag">{assigneeName || '未分配'}</strong>
        </span>
        {entry.caseModule ? (
          <span className="test-order-meta-pill">
            所属模块 <strong className="tp-tone-tag">{entry.caseModule}</strong>
          </span>
        ) : null}
        <span className="test-order-meta-pill">
          实际执行 <strong className="tp-tone-tag">{executorName || '-'}</strong>
        </span>
        <span className="test-order-meta-pill">
          执行时间 <strong className="tp-tone-tag">{formatTime(entry.executedAt) || '-'}</strong>
        </span>
      </div>
    </div>
  )
}
