import { CopyOutlined } from '@ant-design/icons'
import { Button, Tooltip, Typography } from 'antd'
import { priorityTone } from '@/shared/utils/priorityTone'
import { UserDisplayName } from '@/shared/components/UserReference/UserReference'
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
    <div className="test-order-case-summary flex-none border-b border-[var(--srf-card-border)] p-5 max-narrow:p-3">
      <div className="test-order-editor-head flex flex-wrap items-center gap-3 pb-1">
        <Tooltip title={entry.caseId}>
          <Button
            size="small"
            icon={<CopyOutlined aria-hidden="true" />}
            iconPlacement="end"
            className="test-order-case-no max-w-[300px] min-w-0 flex-[0_1_auto] text-[11px] font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace] focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--srf-accent)] [&_.ant-btn-content]:overflow-hidden [&_.ant-btn-content]:text-ellipsis [&_.ant-btn-content]:whitespace-nowrap"
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
        <Text strong className="test-order-case-title flex-[1_1_320px] min-w-0 text-[15px] font-semibold leading-6 text-[var(--srf-text)] [overflow-wrap:anywhere]">
          {entry.caseTitle || entry.caseId}
        </Text>
        {lockedByAssignee ? (
          <Text type="secondary">该条已分配给其他执行人</Text>
        ) : null}
      </div>
      <div className="test-order-execution-meta flex flex-wrap gap-x-4 gap-y-2 pt-3">
        <span
          className={`test-order-meta-pill inline-flex items-center gap-1.5 text-[11px] leading-4 text-[var(--srf-text-secondary)] tone-${getTestOrderEntryStatusTone(entry.status)}`}
        >
          状态 <strong className="tp-tone-tag font-medium [overflow-wrap:anywhere]">{entryStatusMeta.label}</strong>
        </span>
        {entry.casePriority ? (
          <span className={`test-order-meta-pill inline-flex items-center gap-1.5 text-[11px] leading-4 text-[var(--srf-text-secondary)] tone-${priorityTone(entry.casePriority)}`}>
            优先级 <strong className="tp-tone-tag font-medium [overflow-wrap:anywhere]">{entry.casePriority}</strong>
          </span>
        ) : null}
        <span className="test-order-meta-pill inline-flex items-center gap-1.5 text-[11px] leading-4 text-[var(--srf-text-secondary)]">
          分配给 <strong className="tp-tone-tag font-medium [overflow-wrap:anywhere]">{assigneeName ? <UserDisplayName name={assigneeName} /> : '未分配'}</strong>
        </span>
        {entry.caseModule ? (
          <span className="test-order-meta-pill inline-flex items-center gap-1.5 text-[11px] leading-4 text-[var(--srf-text-secondary)]">
            所属模块 <strong className="tp-tone-tag font-medium [overflow-wrap:anywhere]">{entry.caseModule}</strong>
          </span>
        ) : null}
        <span className="test-order-meta-pill inline-flex items-center gap-1.5 text-[11px] leading-4 text-[var(--srf-text-secondary)]">
          实际执行 <strong className="tp-tone-tag border-0 bg-transparent p-0 font-medium text-[var(--srf-text-secondary)] [overflow-wrap:anywhere]">{executorName ? <UserDisplayName name={executorName} /> : '-'}</strong>
        </span>
        <span className="test-order-meta-pill inline-flex items-center gap-1.5 text-[11px] leading-4 text-[var(--srf-text-secondary)]">
          执行时间 <strong className="tp-tone-tag border-0 bg-transparent p-0 font-medium text-[var(--srf-text-secondary)] [overflow-wrap:anywhere]">{formatTime(entry.executedAt) || '-'}</strong>
        </span>
      </div>
    </div>
  )
}
