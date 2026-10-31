import { ExclamationCircleFilled } from '@ant-design/icons'

export function PendingQuestionsLabel({ count }: { count: number }) {
  return <span className="requirement-pending-questions-label">
    <ExclamationCircleFilled aria-hidden />
    <span>待确认问题</span>
    <span className="requirement-pending-questions-count">{count}</span>
  </span>
}
