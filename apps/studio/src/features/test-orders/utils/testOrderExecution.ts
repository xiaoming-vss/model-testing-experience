export const TEST_ORDER_VERDICTS = [
  { value: 'passed', label: '通过', key: '1', tone: 'green' },
  { value: 'failed', label: '失败', key: '2', tone: 'red' },
  { value: 'blocked', label: '阻塞', key: '3', tone: 'amber' },
  { value: 'skipped', label: '跳过', key: '4', tone: 'slate' },
] as const

export function isTestOrderEntryLocked(assigneeUserId: string | undefined, currentUserId: string | undefined, isOwner: boolean) {
  return Boolean(assigneeUserId) && assigneeUserId !== currentUserId && !isOwner
}
